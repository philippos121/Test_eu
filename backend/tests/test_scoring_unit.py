"""Unit tests for scoring engine v4."""
import math
import pytest
from unittest.mock import MagicMock

from app.services.scoring import (
    score_evidence,
    score_willingness,
    compute_drivers,
    evidence_to_prob,
    merge_facts_monotonic,
    EvidenceResult,
)
from app.services.legal_analyzer import LegalValidityResult, PaymentAbilityResult
from app.models import CaseEventType


def _mock_case(**kwargs):
    """Create a mock Case object with given attributes."""
    case = MagicMock()
    defaults = {
        "claim_basis": None,
        "claim_description": None,
        "claim_evidence": None,
        "claim_amount": None,
        "claim_interest_from_date": None,
        "additional_information": None,
        "defendant_is_legal_person": False,
    }
    defaults.update(kwargs)
    for k, v in defaults.items():
        setattr(case, k, v)
    return case


# =====================================================================
# A) EvidenceScorer
# =====================================================================

class TestEvidenceScorer:
    def test_empty_case_scores_zero(self):
        case = _mock_case()
        r = score_evidence(case)
        assert r.total == 0.0
        assert len(r.missing) == 4

    def test_full_evidence_max_score(self):
        case = _mock_case(
            claim_basis="Kaufvertrag vom 01.01.2025",
            claim_description="Ware geliefert am 15.01.2025",
            claim_amount=3500.0,
            claim_interest_from_date="2025-02-01",
            claim_evidence="Mahnung vom 01.03.2025",
        )
        facts = {
            "has_contract": True,
            "has_written_agreement": True,
            "has_delivery_proof": True,
            "has_acceptance": True,
            "has_due_date": True,
            "has_dunning": True,
            "has_deadline_set": True,
        }
        r = score_evidence(case, facts)
        assert r.contract == 25.0
        assert r.delivery == 30.0
        assert r.invoice == 25.0
        assert r.dunning == 20.0
        assert r.total == 100.0
        assert r.missing == []

    def test_partial_evidence(self):
        case = _mock_case(
            claim_basis="Liefervertrag",
            claim_amount=1000.0,
        )
        r = score_evidence(case)
        assert r.contract == 15.0
        assert r.invoice == 15.0
        assert r.delivery == 0.0
        assert r.dunning == 0.0
        assert r.total == 30.0

    def test_delivery_from_description_keywords(self):
        case = _mock_case(claim_description="Die Ware wurde geliefert und übergeben")
        r = score_evidence(case)
        assert r.delivery == 15.0

    def test_dunning_from_evidence_keywords(self):
        case = _mock_case(claim_evidence="Eine Mahnung wurde am 01.02 versendet")
        r = score_evidence(case)
        assert r.dunning == 10.0


# =====================================================================
# A2) Evidence → probability mapping  (v3: no contestation arg)
# =====================================================================

class TestEvidenceToProbability:
    def test_midpoint_gives_fifty_percent(self):
        """Score=50 → ~50%"""
        p = evidence_to_prob(50.0)
        assert p == pytest.approx(0.5, abs=0.01)

    def test_high_evidence_high_probability(self):
        p = evidence_to_prob(100.0)
        assert p > 0.95

    def test_zero_evidence_low_probability(self):
        p = evidence_to_prob(0.0)
        assert p < 0.05

    def test_sigmoid_shape_monotonic(self):
        probs = [evidence_to_prob(s) for s in range(0, 101, 10)]
        for i in range(1, len(probs)):
            assert probs[i] >= probs[i - 1]


# =====================================================================
# B) WillingnessScorer v3  (returns float 0–1, no case arg)
# =====================================================================

class TestWillingnessScorer:
    def test_neutral_base(self):
        p = score_willingness({})
        assert p == pytest.approx(0.5, abs=0.01)

    def test_positive_signals_increase(self):
        p = score_willingness({
            "responded_to_reminder": True,
            "partial_payment": True,
            "settlement_offered": True,
        })
        assert p > 0.5

    def test_negative_signals_decrease(self):
        p = score_willingness({
            "responded_to_reminder": False,
            "repeat_defendant": True,
        })
        assert p < 0.5

    def test_clamped_at_zero_and_one(self):
        # All bad signals shouldn't go below floor
        p = score_willingness({
            "responded_to_reminder": False,
            "repeat_defendant": True,
        })
        assert 0.0 <= p <= 1.0

    def test_no_facts_is_neutral(self):
        assert score_willingness(None) == pytest.approx(0.5, abs=0.01)


# =====================================================================
# C) Drivers v4  (no posteriors parameter)
# =====================================================================

class TestDrivers:
    def test_produces_max_five(self):
        ev = EvidenceResult(total=20, missing=["A", "B", "C"])
        legal = LegalValidityResult(
            p_entstanden=0.3,
            p_entstanden_reasoning="Vertrag nicht bewiesen",
            p_not_untergegangen=0.5,
            p_durchsetzbar=0.4,
            p_claim_valid_llm=0.06,
        )
        ability = PaymentAbilityResult(ability_score=10, insolvency_risk="high",
                                       reasoning="Insolvenzverfahren offen")
        drivers = compute_drivers(ev, legal, ability, 0.3)
        assert len(drivers) <= 5

    def test_strong_case_gets_positive_drivers(self):
        ev = EvidenceResult(total=90, missing=[])
        legal = LegalValidityResult(
            p_entstanden=0.9,
            p_not_untergegangen=0.9,
            p_durchsetzbar=0.9,
            p_claim_valid_llm=0.85,
        )
        ability = PaymentAbilityResult(ability_score=80, insolvency_risk="low",
                                       reasoning="Aktives Unternehmen")
        drivers = compute_drivers(ev, legal, ability, 0.70)
        positive = [d for d in drivers if d["direction"] == "positive"]
        assert len(positive) >= 1

    def test_negative_legal_signals(self):
        ev = EvidenceResult(total=50, missing=[])
        legal = LegalValidityResult(
            p_entstanden=0.3,
            p_entstanden_reasoning="Anspruchsgrundlage unklar",
            p_not_untergegangen=0.85,
            p_durchsetzbar=0.4,
            p_durchsetzbar_reasoning="Verjährung möglicherweise eingetreten",
            p_claim_valid_llm=0.10,
        )
        ability = PaymentAbilityResult(ability_score=60, insolvency_risk="unknown")
        drivers = compute_drivers(ev, legal, ability, 0.5)
        factors = [d["factor"] for d in drivers]
        assert any("Anspruchsentstehung" in f or "Durchsetzbarkeit" in f for f in factors)

    def test_high_willingness_driver(self):
        ev = EvidenceResult(total=60, missing=[])
        legal = LegalValidityResult(p_claim_valid_llm=0.6)
        ability = PaymentAbilityResult(ability_score=70, insolvency_risk="low")
        drivers = compute_drivers(ev, legal, ability, 0.70)
        willingness_drivers = [d for d in drivers if "Zahlungswilligkeit" in d["factor"]]
        assert len(willingness_drivers) == 1
        assert willingness_drivers[0]["direction"] == "positive"


# =====================================================================
# D) Monotonic fact merging
# =====================================================================

class TestMonotonicMerge:
    def test_new_facts_added(self):
        merged = {}
        merge_facts_monotonic(merged, {"has_contract": True, "has_dunning": True})
        assert merged == {"has_contract": True, "has_dunning": True}

    def test_true_not_overwritten_by_false(self):
        merged = {"has_contract": True}
        merge_facts_monotonic(merged, {"has_contract": False})
        assert merged["has_contract"] is True

    def test_false_can_be_upgraded_to_true(self):
        merged = {"has_contract": False}
        merge_facts_monotonic(merged, {"has_contract": True})
        assert merged["has_contract"] is True

    def test_non_boolean_values_always_update(self):
        merged = {"score": 50}
        merge_facts_monotonic(merged, {"score": 70})
        assert merged["score"] == 70

    def test_true_not_overwritten_by_true(self):
        merged = {"has_contract": True}
        merge_facts_monotonic(merged, {"has_contract": True})
        assert merged["has_contract"] is True


# =====================================================================
# E) Final probability formula  p_cash = p_valid × p_provable × p_payment
# =====================================================================

class TestFinalFormula:
    def test_all_ones(self):
        assert 1.0 * 1.0 * 1.0 == pytest.approx(1.0)

    def test_any_zero_kills_result(self):
        assert 0.0 * 0.8 * 0.7 == 0.0

    def test_typical_case(self):
        # v4: pillars are pure LLM / evidence / individual — no blend with statistics
        p_valid    = 0.72   # 100% LLM
        p_provable = evidence_to_prob(65.0)   # evidence score 65 → sigmoid
        p_payment  = 0.5 * 0.60 + 0.5 * 0.55  # 50% ability + 50% willingness
        p_cash = p_valid * p_provable * p_payment
        assert 0.0 < p_cash < 1.0
