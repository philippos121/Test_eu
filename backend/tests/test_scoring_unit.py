"""Unit tests for scoring engine v3."""
import math
import pytest
from unittest.mock import MagicMock

from app.services.scoring import (
    score_evidence,
    score_willingness,
    bayes_update,
    count_events,
    compute_drivers,
    evidence_to_prob,
    blend,
    merge_facts_monotonic,
    EvidenceResult,
    BayesPosterior,
    _beta_quantile,
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
# C) Blend function
# =====================================================================

class TestBlend:
    def test_full_individual_weight(self):
        """weight=1.0 → return individual_p unchanged"""
        assert blend(0.7, 0.3, 1.0) == pytest.approx(0.7, abs=0.001)

    def test_full_stat_weight(self):
        """weight=0.0 → return stat_p unchanged"""
        assert blend(0.7, 0.3, 0.0) == pytest.approx(0.3, abs=0.001)

    def test_equal_weights_average(self):
        assert blend(0.6, 0.4, 0.5) == pytest.approx(0.5, abs=0.001)

    def test_asymmetric_weights(self):
        result = blend(0.8, 0.4, 0.70)
        expected = 0.70 * 0.8 + 0.30 * 0.4
        assert result == pytest.approx(expected, abs=0.001)


# =====================================================================
# D) BayesUpdater
# =====================================================================

class TestBayesUpdater:
    def test_no_observations(self):
        post = bayes_update(7.0, 3.0, 0, 0)
        assert post.alpha_post == 7.0
        assert post.beta_post == 3.0
        assert post.mean == pytest.approx(0.7, abs=0.001)

    def test_with_successes(self):
        post = bayes_update(7.0, 3.0, 3, 4)
        assert post.alpha_post == 10.0
        assert post.beta_post == 4.0
        assert post.mean == pytest.approx(10.0 / 14.0, abs=0.001)

    def test_all_failures(self):
        post = bayes_update(2.0, 2.0, 0, 5)
        assert post.alpha_post == 2.0
        assert post.beta_post == 7.0
        assert post.mean == pytest.approx(2.0 / 9.0, abs=0.001)

    def test_smoothing_prevents_extremes(self):
        post = bayes_update(2.0, 8.0, 10, 10)
        assert post.mean < 1.0
        assert post.mean > 0.5

    def test_credible_interval_exists(self):
        post = bayes_update(7.0, 3.0, 0, 0)
        assert post.ci_low < post.mean
        assert post.ci_high > post.mean
        assert 0.0 <= post.ci_low <= 1.0
        assert 0.0 <= post.ci_high <= 1.0

    def test_more_data_narrows_ci(self):
        post_few = bayes_update(5.0, 5.0, 3, 5)
        post_many = bayes_update(5.0, 5.0, 30, 50)
        assert (post_many.ci_high - post_many.ci_low) < (post_few.ci_high - post_few.ci_low)


# =====================================================================
# D2) Beta quantile helper
# =====================================================================

class TestBetaQuantile:
    def test_symmetric_prior(self):
        q05 = _beta_quantile(5.0, 5.0, 0.05)
        q95 = _beta_quantile(5.0, 5.0, 0.95)
        assert q05 < 0.5
        assert q95 > 0.5

    def test_invalid_params(self):
        assert _beta_quantile(0.0, 0.0, 0.5) == 0.5
        assert _beta_quantile(-1.0, 5.0, 0.5) == 0.5


# =====================================================================
# E) count_events  (v3 rate names)
# =====================================================================

class TestCountEvents:
    def _mock_event(self, event_type):
        ev = MagicMock()
        ev.event_type = event_type
        return ev

    def test_valid_rate_counts_judgment_win(self):
        events = [
            self._mock_event(CaseEventType.JUDGMENT_WIN),
            self._mock_event(CaseEventType.JUDGMENT_WIN),
            self._mock_event(CaseEventType.JUDGMENT_LOSS),
        ]
        s, n = count_events(events, "valid")
        assert s == 2
        assert n == 3

    def test_valid_rate_counts_default_and_settled(self):
        events = [
            self._mock_event(CaseEventType.DEFAULT),
            self._mock_event(CaseEventType.SETTLED),
            self._mock_event(CaseEventType.JUDGMENT_LOSS),
        ]
        s, n = count_events(events, "valid")
        assert s == 2
        assert n == 3

    def test_provable_rate_only_adversarial(self):
        """DEFAULT events do NOT count for provability (no evidence test)."""
        events = [
            self._mock_event(CaseEventType.JUDGMENT_WIN),
            self._mock_event(CaseEventType.DEFAULT),   # not counted for provable
            self._mock_event(CaseEventType.JUDGMENT_LOSS),
        ]
        s, n = count_events(events, "provable")
        assert s == 1    # only JUDGMENT_WIN
        assert n == 2    # JUDGMENT_WIN + JUDGMENT_LOSS

    def test_payment_rate(self):
        events = [
            self._mock_event(CaseEventType.PAYMENT_RECEIVED),
            self._mock_event(CaseEventType.COLLECTION_FAILED),
            self._mock_event(CaseEventType.COLLECTION_FAILED),
        ]
        s, n = count_events(events, "payment")
        assert s == 1
        assert n == 3

    def test_no_events(self):
        s, n = count_events([], "valid")
        assert s == 0
        assert n == 0


# =====================================================================
# F) Drivers v3
# =====================================================================

class TestDrivers:
    def _make_posteriors(self):
        return {
            "valid":    BayesPosterior(6, 2, 0, 0, 6, 2, 0.75),
            "provable": BayesPosterior(4, 6, 0, 0, 4, 6, 0.40),
            "payment":  BayesPosterior(5, 5, 0, 0, 5, 5, 0.50),
        }

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
        drivers = compute_drivers(ev, legal, ability, 0.3, self._make_posteriors())
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
        drivers = compute_drivers(ev, legal, ability, 0.70, self._make_posteriors())
        positive = [d for d in drivers if d["direction"] == "positive"]
        assert len(positive) >= 1

    def test_negative_legal_signals(self):
        ev = EvidenceResult(total=50, missing=[])
        legal = LegalValidityResult(
            p_entstanden=0.3,
            p_entstanden_reasoning="Anspruchsgrundlage unklar",
            p_not_untergegangen=0.85,
            p_durchsetzbar=0.4,
            p_durchsetzbar_reasoning="Zuständigkeit fraglich",
            p_claim_valid_llm=0.10,
        )
        ability = PaymentAbilityResult(ability_score=60, insolvency_risk="unknown")
        drivers = compute_drivers(ev, legal, ability, 0.5, self._make_posteriors())
        factors = [d["factor"] for d in drivers]
        assert any("Anspruchsentstehung" in f or "Durchsetzbarkeit" in f for f in factors)

    def test_high_willingness_driver(self):
        ev = EvidenceResult(total=60, missing=[])
        legal = LegalValidityResult(p_claim_valid_llm=0.6)
        ability = PaymentAbilityResult(ability_score=70, insolvency_risk="low")
        drivers = compute_drivers(ev, legal, ability, 0.70, self._make_posteriors())
        willingness_drivers = [d for d in drivers if "Zahlungswilligkeit" in d["factor"]]
        assert len(willingness_drivers) == 1
        assert willingness_drivers[0]["direction"] == "positive"


# =====================================================================
# G) Monotonic fact merging
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
# H) Final probability formula  p_cash = p_valid × p_provable × p_payment
# =====================================================================

class TestFinalFormula:
    def test_all_ones(self):
        assert 1.0 * 1.0 * 1.0 == pytest.approx(1.0)

    def test_any_zero_kills_result(self):
        assert 0.0 * 0.8 * 0.7 == 0.0

    def test_typical_case(self):
        p_valid    = blend(0.72, 0.75, 0.70)   # ~0.729
        p_provable = blend(0.69, 0.40, 0.40)   # ~0.516
        p_payment  = blend(0.60, 0.50, 0.65)   # ~0.565
        p_cash = p_valid * p_provable * p_payment
        assert 0.0 < p_cash < 1.0
        assert p_cash == pytest.approx(p_valid * p_provable * p_payment, abs=0.001)
