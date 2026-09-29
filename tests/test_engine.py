"""
Unit tests for scheme eligibility engine and quote validator.
Run with: pytest tests/test_engine.py -v
"""
import pandas as pd
import pytest
import sys
import os

# Ensure project root is on the path so `app` is importable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.schemes import check_eligibility, compute_scheme_coverage, validate_quote


# ─────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────

@pytest.fixture
def sample_schemes_df():
    return pd.DataFrame([
        {
            "scheme_id": "SCH001",
            "name": "PM-JAY (Ayushman Bharat)",
            "procedure_id": "P001",
            "package_rate": 8000,
            "max_cover_per_family": 500000,
            "eligibility_rule": "has_scheme_card AND hospital_empanelled",
            "source": "demo",
        },
        {
            "scheme_id": "SCH006",
            "name": "Telangana Aarogyasri",
            "procedure_id": "P001",
            "package_rate": 9500,
            "max_cover_per_family": 200000,
            "eligibility_rule": "has_scheme_card AND hospital_empanelled AND city_in_telangana",
            "source": "demo",
        },
    ])


@pytest.fixture
def sample_prices_df():
    return pd.DataFrame([
        {"procedure_id": "P001", "city_tier": 1, "hospital_type": "government",  "price_low": 5000,  "price_mid": 8000,  "price_high": 12000, "source": "demo"},
        {"procedure_id": "P001", "city_tier": 1, "hospital_type": "private",     "price_low": 15000, "price_mid": 25000, "price_high": 40000, "source": "demo"},
        {"procedure_id": "P001", "city_tier": 1, "hospital_type": "corporate",   "price_low": 30000, "price_mid": 45000, "price_high": 70000, "source": "demo"},
        {"procedure_id": "P001", "city_tier": 2, "hospital_type": "government",  "price_low": 4000,  "price_mid": 6000,  "price_high": 10000, "source": "demo"},
    ])


# ─────────────────────────────────────────────────────────────────
# Test 1 — Scheme eligibility: ineligible when no scheme card
# ─────────────────────────────────────────────────────────────────

class TestCheckEligibility:
    def test_no_scheme_card_means_ineligible(self):
        """
        A patient without a scheme card must never be covered,
        even if the hospital is empanelled.
        """
        eligible = check_eligibility(
            "has_scheme_card AND hospital_empanelled",
            has_scheme_card=False,
            hospital_scheme_ids={"SCH001"},
            scheme_id="SCH001",
            city="Hyderabad",
        )
        assert eligible is False

    def test_valid_card_and_empanelled_hospital_is_eligible(self):
        """
        Patient with card + hospital empanelled → eligible for PM-JAY.
        """
        eligible = check_eligibility(
            "has_scheme_card AND hospital_empanelled",
            has_scheme_card=True,
            hospital_scheme_ids={"SCH001"},
            scheme_id="SCH001",
            city="Hyderabad",
        )
        assert eligible is True

    def test_telangana_rule_fails_for_other_city(self):
        """
        Aarogyasri has the city_in_telangana clause; must fail for Mumbai.
        """
        eligible = check_eligibility(
            "has_scheme_card AND hospital_empanelled AND city_in_telangana",
            has_scheme_card=True,
            hospital_scheme_ids={"SCH006"},
            scheme_id="SCH006",
            city="Mumbai",
        )
        assert eligible is False

    def test_telangana_rule_passes_for_warangal(self):
        eligible = check_eligibility(
            "has_scheme_card AND hospital_empanelled AND city_in_telangana",
            has_scheme_card=True,
            hospital_scheme_ids={"SCH006"},
            scheme_id="SCH006",
            city="Warangal",
        )
        assert eligible is True


# ─────────────────────────────────────────────────────────────────
# Test 2 — Scheme coverage: amount capped correctly
# ─────────────────────────────────────────────────────────────────

class TestComputeSchemeCoverage:
    def test_coverage_capped_at_package_rate(self, sample_schemes_df):
        """
        Price (15 000) > package_rate (8 000) → covered = 8 000.
        """
        covered, scheme_name, _ = compute_scheme_coverage(
            sample_schemes_df,
            procedure_id="P001",
            hospital_scheme_ids={"SCH001"},
            has_scheme_card=True,
            city="Hyderabad",
            price=15000,
        )
        assert covered == 8000
        assert "PM-JAY" in scheme_name

    def test_coverage_capped_at_price_when_price_lower_than_package(self, sample_schemes_df):
        """
        Price (5 000) < package_rate (8 000) → covered = 5 000 (can't pay more than the bill).
        """
        covered, _, _ = compute_scheme_coverage(
            sample_schemes_df,
            procedure_id="P001",
            hospital_scheme_ids={"SCH001"},
            has_scheme_card=True,
            city="Hyderabad",
            price=5000,
        )
        assert covered == 5000

    def test_no_coverage_when_not_empanelled(self, sample_schemes_df):
        """
        Hospital not in any scheme → zero coverage.
        """
        covered, scheme_name, applicable = compute_scheme_coverage(
            sample_schemes_df,
            procedure_id="P001",
            hospital_scheme_ids=set(),   # not empanelled for anything
            has_scheme_card=True,
            city="Hyderabad",
            price=20000,
        )
        assert covered == 0
        assert scheme_name is None

    def test_best_scheme_selected_when_multiple_applicable(self, sample_schemes_df):
        """
        When both PM-JAY (8 000) and Aarogyasri (9 500) apply,
        Aarogyasri should be selected as it covers more.
        """
        covered, scheme_name, _ = compute_scheme_coverage(
            sample_schemes_df,
            procedure_id="P001",
            hospital_scheme_ids={"SCH001", "SCH006"},
            has_scheme_card=True,
            city="Hyderabad",          # Hyderabad ∈ Telangana cities
            price=20000,
        )
        assert covered == 9500
        assert "Aarogyasri" in scheme_name


# ─────────────────────────────────────────────────────────────────
# Test 3 — Quote validator verdicts
# ─────────────────────────────────────────────────────────────────

class TestValidateQuote:
    def test_fair_quote_within_range(self, sample_prices_df):
        """
        A quote of ₹20 000 sits within the ₹5 000–₹70 000 range → 'fair'.
        """
        result = validate_quote(
            sample_prices_df,
            procedure_id="P001",
            city_tier=1,
            quote_amount=20000,
        )
        assert result["verdict"] == "fair"

    def test_far_above_range_verdict(self, sample_prices_df):
        """
        A quote of ₹200 000 is >150 % of the high (₹70 000) → 'far_above'.
        """
        result = validate_quote(
            sample_prices_df,
            procedure_id="P001",
            city_tier=1,
            quote_amount=200000,
        )
        assert result["verdict"] == "far_above"

    def test_below_range_verdict(self, sample_prices_df):
        """
        A quote of ₹1 000 is <90 % of low (₹4 000 tier-2 / ₹5 000 tier-1) → 'below_range'.
        """
        result = validate_quote(
            sample_prices_df,
            procedure_id="P001",
            city_tier=1,
            quote_amount=1000,
        )
        assert result["verdict"] == "below_range"

    def test_above_range_verdict(self, sample_prices_df):
        """
        A quote of ₹85 000 is > high (₹70 000) but ≤ 150 % → 'above_range'.
        """
        result = validate_quote(
            sample_prices_df,
            procedure_id="P001",
            city_tier=1,
            quote_amount=85000,
        )
        assert result["verdict"] == "above_range"

    def test_unknown_procedure_returns_unknown_verdict(self, sample_prices_df):
        result = validate_quote(
            sample_prices_df,
            procedure_id="P999",   # doesn't exist
            city_tier=1,
            quote_amount=50000,
        )
        assert result["verdict"] == "unknown"
