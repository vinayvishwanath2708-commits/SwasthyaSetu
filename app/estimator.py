"""
app/estimator.py — Cost range estimation.

predict_range() is the single entry-point for price lookup.
The function is designed so that a quantile regression model can
replace the rule-based CSV lookup in the future without changing
anything else in the codebase.
"""
from __future__ import annotations

import pandas as pd

# City → tier mapping (extend as real data arrives)
CITY_TIER: dict[str, int] = {
    "hyderabad": 1,
    "bengaluru": 1,
    "chennai": 1,
    "mumbai": 1,
    "delhi": 1,
    "warangal": 2,
    "vijayawada": 2,
    "visakhapatnam": 2,
    "pune": 2,
    "nagpur": 2,
}


def get_city_tier(city: str) -> int:
    return CITY_TIER.get(city.lower(), 3)


def predict_range(
    prices_df: pd.DataFrame,
    *,
    procedure_id: str,
    city: str,
    hospital_type: str,
) -> dict | None:
    """
    Return {'low': int, 'mid': int, 'high': int, 'city_tier': int, 'source': str}
    or None if no matching row found.

    REPLACE THIS FUNCTION with a quantile regression model call when ready.
    The interface (inputs / output keys) must stay the same.
    """
    tier = get_city_tier(city)
    rows = prices_df[
        (prices_df["procedure_id"] == procedure_id)
        & (prices_df["city_tier"] == tier)
        & (prices_df["hospital_type"] == hospital_type)
    ]

    if rows.empty:
        # fallback: any tier for that hospital_type
        rows = prices_df[
            (prices_df["procedure_id"] == procedure_id)
            & (prices_df["hospital_type"] == hospital_type)
        ]

    if rows.empty:
        return None

    row = rows.iloc[0]
    return {
        "low": int(row["price_low"]),
        "mid": int(row["price_mid"]),
        "high": int(row["price_high"]),
        "city_tier": int(row["city_tier"]),
        "source": str(row["source"]),
    }


def build_cost_range(
    prices_df: pd.DataFrame,
    *,
    procedure_id: str,
    city: str,
) -> dict:
    """
    Aggregate across all hospital types to return overall low/high
    and per-type breakdown.
    """
    tier = get_city_tier(city)
    types = ["government", "trust", "private", "corporate"]
    breakdown: dict[str, dict] = {}
    sources: list[str] = []

    for ht in types:
        result = predict_range(prices_df, procedure_id=procedure_id, city=city, hospital_type=ht)
        if result:
            breakdown[ht] = result
            sources.append(result["source"])

    if not breakdown:
        return {}

    all_lows = [v["low"] for v in breakdown.values()]
    all_highs = [v["high"] for v in breakdown.values()]
    all_mids = [v["mid"] for v in breakdown.values()]
    has_demo = "demo" in sources

    return {
        "overall_low": min(all_lows),
        "overall_mid": int(sum(all_mids) / len(all_mids)),
        "overall_high": max(all_highs),
        "city_tier": tier,
        "by_hospital_type": breakdown,
        "is_demo": has_demo,
        "assumptions": [
            f"City tier {tier} pricing applied for '{city}'",
            "Range covers government to corporate hospitals",
            "Prices are estimates; confirm with the hospital",
        ],
    }
