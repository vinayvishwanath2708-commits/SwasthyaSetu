"""
app/schemes.py — Scheme eligibility engine.

Eligibility rules are expressed as plain strings in schemes.csv
(eligibility_rule column).  Each clause is checked here in one place so
non-technical staff can edit the CSV without touching Python code.

Supported clauses (AND-joined):
  has_scheme_card              — user presented a scheme card
  hospital_empanelled          — hospital's scheme_ids includes this scheme
  city_in_telangana            — city is Hyderabad or Warangal (demo list)

To add a new rule, define a new clause string in the CSV and add the
corresponding check in _evaluate_clause() below.
"""
from __future__ import annotations

import pandas as pd

# --------------------------------------------------------------------------- #
# Telangana cities recognised for Aarogyasri (extend as needed)
# --------------------------------------------------------------------------- #
TELANGANA_CITIES: set[str] = {
    "hyderabad",
    "warangal",
    "karimnagar",
    "nizamabad",
    "khammam",
    "rangareddy",
}


def _evaluate_clause(
    clause: str,
    *,
    has_scheme_card: bool,
    hospital_scheme_ids: set[str],
    scheme_id: str,
    city: str,
) -> bool:
    clause = clause.strip()
    if clause == "has_scheme_card":
        return has_scheme_card
    if clause == "hospital_empanelled":
        return scheme_id in hospital_scheme_ids
    if clause == "city_in_telangana":
        return city.lower() in TELANGANA_CITIES
    # Unknown clauses are treated as always-false (safe default)
    return False


def check_eligibility(
    eligibility_rule: str,
    *,
    has_scheme_card: bool,
    hospital_scheme_ids: set[str],
    scheme_id: str,
    city: str,
) -> bool:
    """
    Return True if ALL AND-joined clauses in eligibility_rule pass.
    """
    clauses = [c.strip() for c in eligibility_rule.split("AND")]
    return all(
        _evaluate_clause(
            c,
            has_scheme_card=has_scheme_card,
            hospital_scheme_ids=hospital_scheme_ids,
            scheme_id=scheme_id,
            city=city,
        )
        for c in clauses
    )


def compute_scheme_coverage(
    schemes_df: pd.DataFrame,
    *,
    procedure_id: str,
    hospital_scheme_ids: set[str],
    has_scheme_card: bool,
    city: str,
    price: float,
    cover_used: float = 0.0,
) -> tuple[float, str | None, list[dict]]:
    """
    Return (covered_amount, best_scheme_name, all_applicable_schemes).

    Picks the scheme that covers the most for the given procedure/hospital.
    covered_amount is capped at min(price, package_rate, remaining_cover).
    """
    relevant = schemes_df[schemes_df["procedure_id"] == procedure_id]
    applicable: list[dict] = []

    for _, row in relevant.iterrows():
        scheme_id = str(row["scheme_id"])
        if not check_eligibility(
            row["eligibility_rule"],
            has_scheme_card=has_scheme_card,
            hospital_scheme_ids=hospital_scheme_ids,
            scheme_id=scheme_id,
            city=city,
        ):
            continue

        remaining_cover = float(row["max_cover_per_family"]) - cover_used
        if remaining_cover <= 0:
            continue

        covered = min(price, float(row["package_rate"]), remaining_cover)
        applicable.append(
            {
                "scheme_id": scheme_id,
                "scheme_name": row["name"],
                "package_rate": float(row["package_rate"]),
                "covered": round(covered, 2),
                "max_cover_per_family": float(row["max_cover_per_family"]),
                "source": row["source"],
            }
        )

    if not applicable:
        return 0.0, None, []

    best = max(applicable, key=lambda x: x["covered"])
    return best["covered"], best["scheme_name"], applicable


def validate_quote(
    price_rows: pd.DataFrame,
    *,
    procedure_id: str,
    city_tier: int,
    quote_amount: float,
) -> dict:
    """
    Compare a quoted price against the price range and return a verdict.
    """
    rows = price_rows[price_rows["procedure_id"] == procedure_id]
    if rows.empty:
        return {"verdict": "unknown", "suggestion": "No price data found for this procedure."}

    tier_rows = rows[rows["city_tier"] == city_tier]
    if tier_rows.empty:
        tier_rows = rows  # fallback: use all tiers

    low = tier_rows["price_low"].min()
    high = tier_rows["price_high"].max()
    mid = tier_rows["price_mid"].median()

    if quote_amount < low * 0.9:
        verdict = "below_range"
        suggestion = (
            f"The quoted ₹{quote_amount:,.0f} is below the typical range "
            f"(₹{low:,.0f}–₹{high:,.0f}). Verify the quote includes all components "
            f"(implants, anaesthesia, stay). This may be a partial quote."
        )
    elif quote_amount <= high * 1.05:
        verdict = "fair"
        suggestion = (
            f"The quoted ₹{quote_amount:,.0f} is within the expected range "
            f"(₹{low:,.0f}–₹{high:,.0f}) for this procedure. Confirm final bill details."
        )
    elif quote_amount <= high * 1.5:
        verdict = "above_range"
        suggestion = (
            f"The quoted ₹{quote_amount:,.0f} is above the typical range "
            f"(₹{low:,.0f}–₹{high:,.0f}). Ask the hospital for an itemised breakdown "
            f"and check if a government or trust hospital can offer a lower rate."
        )
    else:
        verdict = "far_above"
        suggestion = (
            f"The quoted ₹{quote_amount:,.0f} is significantly above the typical range "
            f"(₹{low:,.0f}–₹{high:,.0f}). Strongly recommend getting a second opinion "
            f"and comparing with government / scheme hospitals."
        )

    return {
        "verdict": verdict,
        "quote_amount": quote_amount,
        "range_low": low,
        "range_mid": mid,
        "range_high": high,
        "suggestion": suggestion,
    }
