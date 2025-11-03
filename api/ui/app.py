import os, requests, pandas as pd, streamlit as st

st.set_page_config(page_title="AURORA Grid — MVP", layout="wide")
api_base = os.environ.get("AURORA_API", "").rstrip("/")
st.title("AURORA Grid — Energy Autopilot (MVP)")

def api_ok():
    try:
        r = requests.get(f"{api_base}/health", timeout=10)
        return r.ok
    except Exception:
        return False

with st.sidebar:
    st.subheader("1) Connect data")
    st.write("API:", api_base or "❌ not set")
    if not api_ok():
        st.error("Cannot reach API. Set AURORA_API env var when deploying.")
    price = st.file_uploader("price.csv (ts,price_per_mwh,zone)", type="csv")
    demand = st.file_uploader("demand.csv (optional)", type="csv")
    weather = st.file_uploader("weather.csv (optional)", type="csv")
    if st.button("Ingest →"):
        for name,file in [("price",price),("demand",demand),("weather",weather)]:
            if file:
                files={"file":(file.name, file.getvalue(), "text/csv")}
                r=requests.post(f"{api_base}/ingest/{name}", files=files, timeout=60)
                if r.ok: st.success(f"{name}: {r.json()['rows']} rows")
                else: st.error(f"{name}: {r.text}")

st.markdown("### 2) Forecast prices")
if st.button("Run Forecast"):
    r = requests.get(f"{api_base}/forecast/price?horizon=96&zone=Z1", timeout=30)
    if r.ok:
        pts = r.json()["points"]
        df = pd.DataFrame(pts)
        df["ts"] = pd.to_datetime(df["ts"])
        st.line_chart(df.set_index("ts")[["p10","p50","p90"]])
    else:
        st.error(r.text)

st.markdown("### 3) Optimise battery actions")
col = st.columns(6)
cap  = col[0].number_input("Capacity MWh", 0.1, 100.0, 2.0)
pmax = col[1].number_input("Max power MW", 0.1, 50.0, 1.0)
minS = col[2].number_input("Min SOC %", 0.0, 100.0, 10.0)/100
maxS = col[3].number_input("Max SOC %", 0.0, 100.0, 90.0)/100
etaI = col[4].number_input("Charge eff.", 0.5, 1.0, 0.95)
etaO = col[5].number_input("Discharge eff.", 0.5, 1.0, 0.95)

if st.button("Get Top Actions"):
    payload = {"capacity_mwh":cap,"power_mw":pmax,"min_soc":minS,"max_soc":maxS,
               "eta_in":etaI,"eta_out":etaO,"horizon":96,"zone":"Z1"}
    r = requests.post(f"{api_base}/optimize/storage", json=payload, timeout=60)
    if r.ok:
        data = r.json()
        st.metric("Estimated profit (rough)", f"£{data['expected_pnl_gbp']}")
        for a in data["actions"]:
            st.write(f"**{a['type'].upper()}**  {a['start']} → {a['end']}  @ ~{a['avg_mw']} MW")
    else:
        st.error(r.text)
