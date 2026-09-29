"""
app/main.py — CareCost FastAPI application.
"""
from __future__ import annotations

import math
import os
from pathlib import Path
from typing import Optional

import pandas as pd
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.estimator import build_cost_range, get_city_tier, predict_range
from app.geo import haversine_km
from app.schemes import compute_scheme_coverage, validate_quote

# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
STATIC_DIR = BASE_DIR / "static"

# --------------------------------------------------------------------------- #
# Load data at startup
# --------------------------------------------------------------------------- #
procedures_df = pd.read_csv(DATA_DIR / "procedures.csv")
prices_df = pd.read_csv(DATA_DIR / "prices.csv")
schemes_df = pd.read_csv(DATA_DIR / "schemes.csv")
hospitals_df = pd.read_csv(DATA_DIR / "hospitals.csv")

# Convert scheme_ids string to list
hospitals_df["scheme_ids_list"] = hospitals_df["scheme_ids"].fillna("").apply(
    lambda x: [s.strip() for s in x.split(",") if s.strip()]
)

# --------------------------------------------------------------------------- #
# App
# --------------------------------------------------------------------------- #
app = FastAPI(title="CareCost API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static files
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", include_in_schema=False)
async def serve_index():
    return FileResponse(str(STATIC_DIR / "index.html"))


# --------------------------------------------------------------------------- #
# /api/procedures
# --------------------------------------------------------------------------- #
@app.get("/api/procedures")
async def get_procedures(q: Optional[str] = Query(None, description="Fuzzy search")):
    """List all procedures; optionally filter by fuzzy name/keyword match."""
    df = procedures_df.copy()

    if q:
        q_lower = q.lower()
        mask = df.apply(
            lambda row: q_lower in row["name"].lower()
            or any(q_lower in kw.strip().lower() for kw in str(row["keywords"]).split(",")),
            axis=1,
        )
        df = df[mask]

    return df[["procedure_id", "name", "category", "keywords", "source"]].to_dict(orient="records")


# --------------------------------------------------------------------------- #
# /api/estimate
# --------------------------------------------------------------------------- #
class EstimateRequest(BaseModel):
    procedure_id: str
    city: str
    has_scheme_card: bool = False
    insurance_cover_left: float = 0.0
    user_lat: Optional[float] = None
    user_lng: Optional[float] = None


@app.post("/api/estimate")
async def estimate(req: EstimateRequest):
    proc = procedures_df[procedures_df["procedure_id"] == req.procedure_id]
    if proc.empty:
        return {"error": "Procedure not found"}

    # City centre fallback coordinates
    city_centres = {
        "hyderabad": (17.3850, 78.4867),
        "warangal": (17.9784, 79.5941),
    }
    centre = city_centres.get(req.city.lower(), (17.3850, 78.4867))
    user_lat = req.user_lat if req.user_lat is not None else centre[0]
    user_lng = req.user_lng if req.user_lng is not None else centre[1]

    # Overall cost range
    cost_range = build_cost_range(prices_df, procedure_id=req.procedure_id, city=req.city)
    city_tier = get_city_tier(req.city)

    # Filter hospitals to this city
    city_hospitals = hospitals_df[hospitals_df["city"].str.lower() == req.city.lower()].copy()

    hospital_results = []

    for _, hosp in city_hospitals.iterrows():
        h_scheme_ids: set[str] = set(hosp["scheme_ids_list"])
        cashless: bool = bool(hosp["cashless_insurance"])

        # Price for this hospital type
        price_data = predict_range(
            prices_df,
            procedure_id=req.procedure_id,
            city=req.city,
            hospital_type=hosp["type"],
        )
        if not price_data:
            continue

        price_mid = price_data["mid"]

        # Scheme coverage
        scheme_covered, scheme_name, applicable_schemes = compute_scheme_coverage(
            schemes_df,
            procedure_id=req.procedure_id,
            hospital_scheme_ids=h_scheme_ids,
            has_scheme_card=req.has_scheme_card,
            city=req.city,
            price=price_mid,
        )

        # Insurance coverage (only at cashless hospitals, on remainder)
        after_scheme = max(0.0, price_mid - scheme_covered)
        insurance_covered = 0.0
        if cashless and req.insurance_cover_left > 0:
            insurance_covered = min(after_scheme, req.insurance_cover_left)

        out_of_pocket = max(0.0, price_mid - scheme_covered - insurance_covered)

        distance_km = haversine_km(user_lat, user_lng, float(hosp["lat"]), float(hosp["lng"]))

        tags = []
        if applicable_schemes and req.has_scheme_card:
            tags.append("scheme_hospital")
        if cashless:
            tags.append("cashless")
        if bool(hosp["nabh"]):
            tags.append("nabh")
        tags.append(f"~{distance_km:.1f} km")

        hospital_results.append(
            {
                "hospital_id": hosp["hospital_id"],
                "name": hosp["name"],
                "type": hosp["type"],
                "lat": float(hosp["lat"]),
                "lng": float(hosp["lng"]),
                "nabh": bool(hosp["nabh"]),
                "cashless_insurance": cashless,
                "estimated_price": price_mid,
                "price_low": price_data["low"],
                "price_high": price_data["high"],
                "scheme_covered": round(scheme_covered, 2),
                "scheme_name": scheme_name,
                "applicable_schemes": applicable_schemes,
                "insurance_covered": round(insurance_covered, 2),
                "out_of_pocket": round(out_of_pocket, 2),
                "distance_km": round(distance_km, 2),
                "tags": tags,
                "is_demo": str(hosp["source"]) == "demo",
            }
        )

    # Sort by out_of_pocket then distance
    hospital_results.sort(key=lambda h: (h["out_of_pocket"], h["distance_km"]))

    best = hospital_results[0] if hospital_results else None
    worst_oop = max((h["out_of_pocket"] for h in hospital_results), default=0)
    savings_vs_expensive = round(worst_oop - best["out_of_pocket"], 2) if best else 0

    assumptions = [
        f"City tier {city_tier} pricing for '{req.city}'",
        f"Has scheme card: {req.has_scheme_card}",
        f"Insurance cover remaining: ₹{req.insurance_cover_left:,.0f}",
        "Mid-range price used for hospital comparison",
        "Insurance applies only at cashless empanelled hospitals",
        "Scheme covers min(price, package_rate, remaining family cover)",
    ]

    return {
        "procedure": proc.iloc[0].to_dict(),
        "cost_range": cost_range,
        "hospitals": hospital_results,
        "best_option": best,
        "savings_vs_expensive": savings_vs_expensive,
        "assumptions": assumptions,
        "is_demo": cost_range.get("is_demo", True),
    }


# --------------------------------------------------------------------------- #
# /api/validate-quote
# --------------------------------------------------------------------------- #
class ValidateQuoteRequest(BaseModel):
    procedure_id: str
    city: str
    quote_amount: float


@app.post("/api/validate-quote")
async def validate_quote_endpoint(req: ValidateQuoteRequest):
    proc = procedures_df[procedures_df["procedure_id"] == req.procedure_id]
    if proc.empty:
        return {"error": "Procedure not found"}

    city_tier = get_city_tier(req.city)
    result = validate_quote(
        prices_df,
        procedure_id=req.procedure_id,
        city_tier=city_tier,
        quote_amount=req.quote_amount,
    )
    return result
