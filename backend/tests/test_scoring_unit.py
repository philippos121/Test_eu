"""Unit tests for scoring engine v2."""
import math
import pytest
from unittest.mock import MagicMock

from app.services.scoring import (
    score_evidence,
    contestation_risk,
    score_ability,
    score_willingness,
    bayes_update,
    compute_p_cash_success,
    count_events,
    compute_drivers,
    evidence_to_probability,
    adjust_settle_by_willingness,
    adjust_collect_by_ability,
    adjust_collect_by_willingness,
    merge_facts_monotonic,
    EvidenceResult,
    AbilityResult,
    WillingnessResult,
    BayesPosterior,
    _logit,
    _sigmoid,
    _beta_quantile,
)
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
# A2) Logistic evidence→probability mapping
# =====================================================================

class TestEvidenceToProbability:
    def test_midpoint_no_contestation(self):
        """Score=50 with cr=0 → ~50%"""
        p = evidence_to_probability(50.0, 0.0)
        assert p == pytest.approx(0.5, abs=0.01)

    def test_high_evidence_high_probability(self):
        """Score=100 with cr=0 → should be well above 50%"""
        p = evidence_to_probability(100.0, 0.0)
        assert p > 0.95

    def test_zero_evidence_low_probability(self):
        """Score=0 with cr=0 → should be well below 50%"""
        p = evidence_to_probability(0.0, 0.0)
        assert p < 0.05

    def test_contestation_reduces_probability(self):
        """Same evidence score, higher contestation → lower probability"""
        p_low_cr = evidence_to_probability(70.0, 0.0)
        p_high_cr = evidence_to_probability(70.0, 0.8)
        assert p_high_cr < p_low_cr

    def test_full_contestation_with_strong_evidence(self):
        """Even with max contestation, strong evidence still has some probability"""
        p = evidence_to_probability(100.0, 1.0)
        assert p > 0.3  # not driven to zero

    def test_sigmoid_shape_monotonic(self):
        """Probability increases monotonically with evidence"""
        probs = [evidence_to_probability(s, 0.2) for s in range(0, 101, 10)]
        for i in range(1, len(probs)):
            assert probs[i] >= probs[i - 1]


# =====================================================================
# B) ContestationRisk
# =====================================================================

class TestContestationRisk:
    def test_no_dispute_signals(self):
        case = _mock_case()
        assert contestation_risk(case) == 0.0

    def test_dispute_keywords_raise_risk(self):
        case = _mock_case(claim_description="Ware mangelhaft, Reklamation eingereicht")
        risk = contestation_risk(case)
        assert risk > 0.0

    def test_facts_raise_risk(self):
        case = _mock_case()
        risk = contestation_risk(case, {"defendant_disputes": True, "quality_issue": True})
        assert risk == 0.5

    def test_capped_at_1(self):
        case = _mock_case(
            claim_description="nicht geliefert mangelhaft chargeback rücksendung reklamation widerspruch dispute",
            claim_evidence="not delivered defective refund",
        )
        risk = contestation_risk(case, {"defendant_disputes": True, "quality_issue": True})
        assert risk <= 1.0


# =====================================================================
# C) AbilityScorer
# =====================================================================

class TestAbilityScorer:
    def test_default_ability(self):
        case = _mock_case()
        r = score_ability(case)
        assert r.score == 75.0

    def test_insolvency_lowers_score(self):
        case = _mock_case()
        r = score_ability(case, {"insolvency_flag": True})
        assert r.score == 15.0

    def test_inactive_company(self):
        case = _mock_case()
        r = score_ability(case, {"company_active": False})
        assert r.score == 45.0

    def test_legal_person_bonus(self):
        case = _mock_case(defendant_is_legal_person=True)
        r = score_ability(case)
        assert r.score == 80.0

    def test_all_negative_flags_floor_at_zero(self):
        case = _mock_case()
        r = score_ability(case, {"insolvency_flag": True, "company_active": False, "vat_valid": False})
        assert r.score == 0.0


# =====================================================================
# D) WillingnessScorer
# =====================================================================

class TestWillingnessScorer:
    def test_default_willingness(self):
        case = _mock_case()
        r = score_willingness(case)
        assert r.score == 50.0

    def test_positive_signals(self):
        case = _mock_case()
        r = score_willingness(case, {"responded_to_reminder": True, "partial_payment": True, "settlement_offered": True})
        assert r.score == 85.0

    def test_negative_signals(self):
        case = _mock_case()
        r = score_willingness(case, {"responded_to_reminder": False, "repeat_defendant": True})
        assert r.score == 15.0

    def test_capped_at_100(self):
        case = _mock_case()
        r = score_willingness(case, {
            "responded_to_reminder": True,
            "partial_payment": True,
            "settlement_offered": True,
        })
        assert r.score <= 100.0


# =====================================================================
# E) BayesUpdater
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

    def test_single_trial_success(self):
        post = bayes_update(5.0, 5.0, 1, 1)
        assert post.alpha_post == 6.0
        assert post.beta_post == 5.0
        assert post.mean == pytest.approx(6.0 / 11.0, abs=0.001)

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
        """More observations should narrow the credible interval."""
        post_few = bayes_update(5.0, 5.0, 3, 5)
        post_many = bayes_update(5.0, 5.0, 30, 50)
        ci_width_few = post_few.ci_high - post_few.ci_low
        ci_width_many = post_many.ci_high - post_many.ci_low
        assert ci_width_many < ci_width_few


# =====================================================================
# E2) Beta quantile helper
# =====================================================================

class TestBetaQuantile:
    def test_symmetric_prior(self):
        """Beta(5,5) quantiles should be symmetric around 0.5."""
        q05 = _beta_quantile(5.0, 5.0, 0.05)
        q95 = _beta_quantile(5.0, 5.0, 0.95)
        assert q05 < 0.5
        assert q95 > 0.5
        assert abs((q05 + q95) / 2 - 0.5) < 0.05

    def test_invalid_params(self):
        assert _beta_quantile(0.0, 0.0, 0.5) == 0.5
        assert _beta_quantile(-1.0, 5.0, 0.5) == 0.5


# =====================================================================
# F) Willingness-adjusted probabilities
# =====================================================================

class TestWillingnessAdjustments:
    def test_neutral_willingness_no_change_settle(self):
        """Willingness=50 (neutral) should barely change p_settle."""
        p = adjust_settle_by_willingness(0.3, 50.0)
        assert p == pytest.approx(0.3, abs=0.01)

    def test_high_willingness_increases_settle(self):
        p_neutral = adjust_settle_by_willingness(0.3, 50.0)
        p_high = adjust_settle_by_willingness(0.3, 85.0)
        assert p_high > p_neutral

    def test_low_willingness_decreases_settle(self):
        p_neutral = adjust_settle_by_willingness(0.3, 50.0)
        p_low = adjust_settle_by_willingness(0.3, 15.0)
        assert p_low < p_neutral

    def test_neutral_ability_no_change_collect(self):
        """Ability=75 (neutral baseline) should barely change p_collect."""
        p = adjust_collect_by_ability(0.6, 75.0)
        assert p == pytest.approx(0.6, abs=0.01)

    def test_low_ability_decreases_collect(self):
        p_neutral = adjust_collect_by_ability(0.6, 75.0)
        p_low = adjust_collect_by_ability(0.6, 15.0)
        assert p_low < p_neutral

    def test_low_ability_does_not_zero_collect(self):
        """Even ability=0, p_collect should not be driven to zero."""
        p = adjust_collect_by_ability(0.6, 0.0)
        assert p > 0.05  # floor is not zero

    def test_willingness_collect_adjustment(self):
        p_neutral = adjust_collect_by_willingness(0.5, 50.0)
        p_high = adjust_collect_by_willingness(0.5, 85.0)
        assert p_high > p_neutral


# =====================================================================
# F2) Logit/Sigmoid helpers
# =====================================================================

class TestLogitSigmoid:
    def test_sigmoid_of_zero(self):
        assert _sigmoid(0.0) == pytest.approx(0.5, abs=0.001)

    def test_logit_of_half(self):
        assert _logit(0.5) == pytest.approx(0.0, abs=0.001)

    def test_roundtrip(self):
        for p in [0.1, 0.3, 0.5, 0.7, 0.9]:
            assert _sigmoid(_logit(p)) == pytest.approx(p, abs=0.001)

    def test_logit_clamped(self):
        """Should not throw for extreme values."""
        assert math.isfinite(_logit(0.0))
        assert math.isfinite(_logit(1.0))


# =====================================================================
# G) p_cash_success formula
# =====================================================================

class TestPCashSuccess:
    def test_all_ones(self):
        result = compute_p_cash_success(1.0, 1.0, 1.0, 1.0, 1.0)
        assert result == pytest.approx(1.0, abs=0.001)

    def test_all_zeros(self):
        result = compute_p_cash_success(0.0, 0.0, 0.0, 0.0, 0.0)
        assert result == 0.0

    def test_typical_case(self):
        # p_served=0.7, p_default=0.5, p_win_contested=0.6, p_settle=0.3, p_collect=0.5
        # p_win = 0.3 + 0.7*(0.5 + 0.5*0.6) = 0.3 + 0.7*0.8 = 0.3 + 0.56 = 0.86
        # p_cash = 0.7 * 0.86 * 0.5 = 0.301
        result = compute_p_cash_success(0.7, 0.5, 0.6, 0.3, 0.5)
        assert result == pytest.approx(0.301, abs=0.001)

    def test_no_service(self):
        result = compute_p_cash_success(0.0, 0.8, 0.9, 0.3, 0.7)
        assert result == 0.0

    def test_no_collection(self):
        result = compute_p_cash_success(1.0, 1.0, 1.0, 1.0, 0.0)
        assert result == 0.0

    def test_formula_components(self):
        p_settle = 0.3
        p_default = 0.4
        p_win_contested = 0.6
        p_win = p_settle + (1 - p_settle) * (p_default + (1 - p_default) * p_win_contested)
        assert p_win == pytest.approx(0.832, abs=0.001)

        result = compute_p_cash_success(0.9, p_default, p_win_contested, p_settle, 0.7)
        expected = 0.9 * p_win * 0.7
        assert result == pytest.approx(expected, abs=0.001)


# =====================================================================
# H) count_events
# =====================================================================

class TestCountEvents:
    def _mock_event(self, event_type):
        ev = MagicMock()
        ev.event_type = event_type
        return ev

    def test_served_counts(self):
        events = [
            self._mock_event(CaseEventType.SERVICE_OK),
            self._mock_event(CaseEventType.SERVICE_OK),
            self._mock_event(CaseEventType.SERVICE_FAIL),
        ]
        s, n = count_events(events, "served")
        assert s == 2
        assert n == 3

    def test_default_counts(self):
        events = [
            self._mock_event(CaseEventType.DEFAULT),
            self._mock_event(CaseEventType.DEFENDANT_RESPONDED),
        ]
        s, n = count_events(events, "default")
        assert s == 1
        assert n == 2

    def test_no_events(self):
        s, n = count_events([], "served")
        assert s == 0
        assert n == 0

    def test_collect_with_failure(self):
        """Collection rate now has COLLECTION_FAILED as failure event."""
        events = [
            self._mock_event(CaseEventType.PAYMENT_RECEIVED),
            self._mock_event(CaseEventType.COLLECTION_FAILED),
            self._mock_event(CaseEventType.COLLECTION_FAILED),
        ]
        s, n = count_events(events, "collect")
        assert s == 1
        assert n == 3  # 1 success + 2 failures


# =====================================================================
# I) Drivers
# =====================================================================

class TestDrivers:
    def test_produces_max_five(self):
        ev = EvidenceResult(total=20, missing=["A", "B", "C"])
        ab = AbilityResult(insolvency_flag=True, score=15)
        wi = WillingnessResult(score=30, partial_payment=False)
        posteriors = {
            "served": BayesPosterior(7, 3, 0, 0, 7, 3, 0.7),
            "default": BayesPosterior(5, 5, 0, 0, 5, 5, 0.2),
            "settle": BayesPosterior(3, 7, 0, 0, 3, 7, 0.3),
            "collect": BayesPosterior(6, 4, 0, 0, 6, 4, 0.25),
        }
        drivers = compute_drivers(ev, ab, wi, 0.6, posteriors)
        assert len(drivers) <= 5

    def test_strong_case_gets_positive_drivers(self):
        ev = EvidenceResult(total=90, missing=[])
        ab = AbilityResult(score=80)
        wi = WillingnessResult(score=70, partial_payment=True)
        posteriors = {
            "served": BayesPosterior(7, 3, 0, 0, 7, 3, 0.7),
            "default": BayesPosterior(5, 5, 0, 0, 5, 5, 0.5),
            "settle": BayesPosterior(3, 7, 0, 0, 3, 7, 0.3),
            "collect": BayesPosterior(6, 4, 0, 0, 6, 4, 0.6),
        }
        drivers = compute_drivers(ev, ab, wi, 0.1, posteriors)
        positive = [d for d in drivers if d["direction"] == "positive"]
        assert len(positive) >= 2

    def test_willingness_driver_positive(self):
        """High willingness should produce a positive driver."""
        ev = EvidenceResult(total=60, missing=[])
        ab = AbilityResult(score=75)
        wi = WillingnessResult(score=70)
        posteriors = {
            "served": BayesPosterior(7, 3, 0, 0, 7, 3, 0.7),
            "default": BayesPosterior(5, 5, 0, 0, 5, 5, 0.5),
            "settle": BayesPosterior(3, 7, 0, 0, 3, 7, 0.3),
            "collect": BayesPosterior(6, 4, 0, 0, 6, 4, 0.6),
        }
        drivers = compute_drivers(ev, ab, wi, 0.1, posteriors)
        willingness_drivers = [d for d in drivers if "Zahlungswilligkeit" in d["factor"]]
        assert len(willingness_drivers) == 1
        assert willingness_drivers[0]["direction"] == "positive"


# =====================================================================
# J) Monotonic fact merging
# =====================================================================

class TestMonotonicMerge:
    def test_new_facts_added(self):
        merged = {}
        merge_facts_monotonic(merged, {"has_contract": True, "has_dunning": True})
        assert merged == {"has_contract": True, "has_dunning": True}

    def test_true_not_overwritten_by_false(self):
        merged = {"has_contract": True}
        merge_facts_monotonic(merged, {"has_contract": False})
        assert merged["has_contract"] is True  # not reverted!

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
