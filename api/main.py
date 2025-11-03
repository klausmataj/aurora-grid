import os, io, json
from datetime import timedelta
import pandas as pd
import numpy as np
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware

APP = FastAPI(title="AURORA API")
APP.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

WAREHOUSE = "warehouse"
os.makedirs(WAREHOUSE, exist_ok=True)

REQUIRED = {
    "price":   ["ts","price_per_mwh","zone"],
    "demand":  ["ts","mw","zone"],
    "weather": ["ts","temp_c","wind_ms","irradiance_wm2"],
}

def _read_csv(name):
    p = os.path.join(WAREHOUSE, f"{name}.csv")
    if not os.path.exists(p):
        raise HTTPException(400, f"{name}.csv not found. Upload & ingest first.")
    df = pd.read_csv(p)
    if "ts" in df.columns:
        df["ts"] = pd.to_datetime(df["ts"], utc=True)
    return df

@APP.get("/health")
def health():
    return {"status": "ok"}

@APP.post("/ingest/{name}")
async def ingest(name: str, file: UploadFile = File(...)):
    if name not in REQUIRED:
        raise HTTPException(400, f"invalid dataset: {name}")
    os.makedirs(WAREHOUSE, exist_ok=True)
    path = os.path.join(WAREHOUSE, f"{name}.csv")
    raw = await file.read()
    with open(path, "wb") as f:
        f.write(raw)
    try:
        df = pd.read_csv(io.BytesIO(raw))
    except Exception as e:
        raise HTTPException(400, f"CSV parse error: {e}")
    missing = [c for c in REQUIRED[name] if c not in df.columns]
    if missing:
        raise HTTPException(400, f"Missing columns {missing} for {name}. Required {REQUIRED[name]}")
    if "ts" in df.columns:
        try:
            pd.to_datetime(df["ts"], utc=True)
        except Exception:
            raise HTTPException(400, "Column 'ts' must be ISO timestamps like 2025-10-26T00:00:00Z")
    return {"status":"ok", "rows": int(len(df))}

@APP.get("/forecast/price")
def forecast_price(horizon: int = 96, zone: str = "Z1"):
    # read price history
    df = _read_csv("price")
    df = df[df["zone"] == zone].sort_values("ts")
    if len(df) < 32:
        raise HTTPException(400, "Not enough price rows (need at least 32).")
    # simple model: last-known price + drift ~ rolling mean
    last_ts = df["ts"].iloc[-1]
    step = (df["ts"].iloc[-1] - df["ts"].iloc[-2])
    if step == pd.Timedelta(0):
        step = pd.Timedelta(minutes=15)
    base = df["price_per_mwh"].rolling(96, min_periods=1).mean().iloc[-1]
    vol  = df["price_per_mwh"].rolling(96, min_periods=1).std(ddof=0).fillna(0).iloc[-1]
    future_ts = [last_ts + (i+1)*step for i in range(horizon)]
    rng = np.random.default_rng(42)
    noise = rng.normal(0, max(vol, 0.01), size=horizon)
    p50 = np.clip(base + noise, 0, None)
    p10 = np.clip(p50 - 0.7*max(vol, 1), 0, None)
    p90 = p50 + 0.7*max(vol, 1)
    out = [{"ts": t.isoformat(), "p10": float(a), "p50": float(b), "p90": float(c)}
           for t,a,b,c in zip(future_ts,p10,p50,p90)]
    return {"zone": zone, "points": out}

@APP.post("/optimize/storage")
async def optimize_storage(body: dict):
    """
    Greedy arbitrage: buy at low, sell at high later, within power/energy limits.
    Body expects: capacity_mwh, power_mw, min_soc, max_soc, eta_in, eta_out, horizon (int), zone (str)
    """
    cap   = float(body.get("capacity_mwh", 2.0))
    pmax  = float(body.get("power_mw", 1.0))
    min_s = float(body.get("min_soc", 0.1)) * cap
    max_s = float(body.get("max_soc", 0.9)) * cap
    eta_i = float(body.get("eta_in", 0.95))
    eta_o = float(body.get("eta_out", 0.95))
    zone  = body.get("zone", "Z1")
    horizon = int(body.get("horizon", 96))

    f = forecast_price(horizon=horizon, zone=zone)["points"]
    prices = np.array([pt["p50"] for pt in f])

    # simple top/bottom windowing
    n = len(prices)
    soc = min_s
    actions = []
    pnl = 0.0
    step_h = 0.25  # 15-minute steps

    for t in range(n):
        price = prices[t]
        # decide: charge if price in bottom 30%, discharge if in top 30%
        rank = (prices[t] - prices.min()) / (prices.ptp() + 1e-6)
        if rank < 0.3 and soc < max_s:
            power = min(pmax, (max_s - soc)/eta_i/step_h)
            e = power * step_h  # MWh in
            cost = e * price
            soc += e * eta_i
            actions.append({"t": t, "action": "charge", "mw": round(power,3), "price": round(price,2)})
            pnl -= cost
        elif rank > 0.7 and soc > min_s:
            power = min(pmax, (soc - min_s)/step_h)
            e = power * step_h  # MWh out
            revenue = e * price * eta_o
            soc -= e
            actions.append({"t": t, "action": "discharge", "mw": round(power,3), "price": round(price,2)})
            pnl += revenue

    # summarise into friendly "windows"
    points = [p["ts"] for p in f]
    def ts_of(i): return points[i]

    windows = []
    i = 0
    while i < len(actions):
        kind = actions[i]["action"]
        j = i
        mw_avg = 0.0; cnt = 0
        while j < len(actions) and actions[j]["action"] == kind:
            mw_avg += actions[j]["mw"]; cnt += 1; j += 1
        windows.append({
            "type": kind,
            "start": ts_of(actions[i]["t"]),
            "end": ts_of(actions[j-1]["t"]),
            "avg_mw": round(mw_avg/max(cnt,1),2)
        })
        i = j

    # pick Top 5 windows by magnitude
    top = windows[:5]
    return {"expected_pnl_gbp": round(pnl/1000, 2), "actions": top, "note": "Assumes £/MWh≈price/1000"}
