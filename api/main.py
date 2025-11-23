from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Aurora API")

@app.get("/health")
def health():
    return {"ok": True}

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/analyze_day")
def analyze_day():
    # Dummy demand pattern for now (24 hours)
    demand = [30, 28, 27, 26, 25, 25, 28, 35, 45, 55, 60, 62,
              65, 70, 75, 80, 85, 88, 80, 70, 60, 50, 40, 35]

    peak_value = max(demand)
    peak_hour = demand.index(peak_value)

    recommendation = f"Peak demand occurs at hour {peak_hour} with {peak_value} kW. Shift flexible loads away from this hour."

    return {
        "demand_forecast": demand,
        "peak_hour": peak_hour,
        "peak_value_kw": peak_value,
        "recommendation": recommendation,
        "explanation": "This is a basic forecast. Aurora will get smarter as you feed it real data."
    }

