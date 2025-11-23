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

from pydantic import BaseModel

class BuildingData(BaseModel):
    hourly_usage: list   # list of 24 numbers
    max_capacity_kw: float

@app.post("/analyze_building")
def analyze_building(data: BuildingData):
    usage = data.hourly_usage

    peak_value = max(usage)
    peak_hour = usage.index(peak_value)

    recommendation = (
        f"Peak usage is at hour {peak_hour} with {peak_value} kW. "
        "Try to shift flexible loads away from this hour to reduce demand charges."
    )

    return {
        "peak_hour": peak_hour,
        "peak_value_kw": peak_value,
        "recommendation": recommendation,
        "explanation": "Aurora analyzed the building’s daily usage pattern."
    }


@app.get("/simulate_demo_building")
def simulate_demo_building():
    """
    Demo: simulate one day for a typical office building,
    then show how Aurora would optimise it.
    """

    # 24 hours, simple baseline demand in kW
    hours = list(range(24))
    baseline_demand = [
        30, 28, 27, 26, 25, 25,   # 0–5  night
        30, 40, 45, 55, 60, 62,   # 6–11 morning ramp
        70, 75, 80, 85,           # 12–15 daytime
        90, 95, 88, 80,           # 16–19 evening peak
        70, 60, 50, 40            # 20–23 late evening
    ]

    # Simple tariff in £/kWh
    def price_per_kwh(hour: int) -> float:
        if hour < 6:
            return 0.08   # cheap night
        elif hour < 16:
            return 0.15   # normal
        elif hour < 21:
            return 0.30   # expensive peak
        else:
            return 0.12   # late evening

    # Cost with no optimisation
    baseline_cost = 0.0
    for h, demand in enumerate(baseline_demand):
        baseline_cost += demand * price_per_kwh(h)

    # Copy demand for optimisation
    optimised_demand = baseline_demand.copy()

    # Aurora "moves" 20% of load from expensive peak hours
    # into cheaper night hours
    peak_hours = [16, 17, 18, 19, 20]
    night_targets = [0, 1, 2, 3, 4]  # where we shift to

    for peak_h, night_h in zip(peak_hours, night_targets):
        original = optimised_demand[peak_h]
        shift_amount = int(original * 0.2)  # move 20%
        optimised_demand[peak_h] -= shift_amount
        optimised_demand[night_h] += shift_amount

    # Cost after optimisation
    optimised_cost = 0.0
    for h, demand in enumerate(optimised_demand):
        optimised_cost += demand * price_per_kwh(h)

    cost_saving = round(baseline_cost - optimised_cost, 2)
    peak_before = max(baseline_demand)
    peak_after = max(optimised_demand)

    # Rough CO2 saving estimate: assume 0.25 kg per £ saved
    co2_saving_kg = round(max(cost_saving, 0) * 0.25, 1)

    return {
        "building_name": "Demo Office Tower",
        "hours": hours,
        "baseline_demand_kw": baseline_demand,
        "optimised_demand_kw": optimised_demand,
        "baseline_cost_gbp": round(baseline_cost, 2),
        "optimised_cost_gbp": round(optimised_cost, 2),
        "cost_saving_gbp": cost_saving,
        "peak_kw_before": peak_before,
        "peak_kw_after": peak_after,
        "co2_saving_kg": co2_saving_kg,
    }

