"""Unit tests for EvidenceScorer, BayesUpdater, and p_cash_success formula."""
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
    EvidenceResult,
    AbilityResult,
    WillingnessResult,
    BayesPosterior,
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
        # contract=15 (basis set, no written_agreement fact), invoice=15 (amount but no due date)
        assert r.contract == 15.0
        assert r.invoice == 15.0
        assert r.delivery == 0.0
        assert r.dunning == 0.0
        assert r.total == 30.0

    def test_delivery_from_description_keywords(self):
        case = _mock_case(claim_description="Die Ware wurde geliefert und übergeben")
        r = score_evidence(case)
        assert r.delivery == 15.0  # keyword match, no proof fact

    def test_dunning_from_evidence_keywords(self):
        case = _mock_case(claim_evidence="Eine Mahnung wurde am 01.02 versendet")
        r = score_evidence(case)
        assert r.dunning == 10.0  # keyword match, no dunning fact


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
        assert risk == 0.5  # 0.3 + 0.2

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
        assert r.score == 15.0  # 75 - 60
        assert r.insolvency_flag is True

    def test_inactive_company(self):
        case = _mock_case()
        r = score_ability(case, {"company_active": False})
        assert r.score == 45.0  # 75 - 30

    def test_legal_person_bonus(self):
        case = _mock_case(defendant_is_legal_person=True)
        r = score_ability(case)
        assert r.score == 80.0  # 75 + 5

    def test_all_negative_flags_floor_at_zero(self):
        case = _mock_case()
        r = score_ability(case, {"insolvency_flag": True, "company_active": False, "vat_valid": False})
        assert r.score == 0.0  # 75 - 60 - 30 - 10 → clamped to 0


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
        assert r.score == 85.0  # 50 + 10 + 15 + 10

    def test_negative_signals(self):
        case = _mock_case()
        r = score_willingness(case, {"responded_to_reminder": False, "repeat_defendant": True})
        assert r.score == 15.0  # 50 - 15 - 20

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
        post = bayes_update(8.0, 2.0, 0, 0)
        assert post.alpha_post == 8.0
        assert post.beta_post == 2.0
        assert post.mean == pytest.approx(0.8, abs=0.001)

    def test_with_successes(self):
        # Prior: Beta(8,2), observed 3 successes out of 4 trials
        post = bayes_update(8.0, 2.0, 3, 4)
        assert post.alpha_post == 11.0  # 8 + 3
        assert post.beta_post == 3.0    # 2 + 1
        assert post.mean == pytest.approx(11.0 / 14.0, abs=0.001)

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
        # Even 10/10 successes with Beta(2,8) prior don't give 100%
        post = bayes_update(2.0, 8.0, 10, 10)
        assert post.mean < 1.0
        assert post.mean > 0.5


# =====================================================================
# F) p_cash_success formula
# =====================================================================

class TestPCashSuccess:
    def test_all_ones(self):
        """All probabilities at 1.0 → p_cash_success = 1.0"""
        result = compute_p_cash_success(1.0, 1.0, 1.0, 1.0, 1.0)
        assert result == pytest.approx(1.0, abs=0.001)

    def test_all_zeros(self):
        result = compute_p_cash_success(0.0, 0.0, 0.0, 0.0, 0.0)
        assert result == 0.0

    def test_typical_case(self):
        # p_served=0.8, p_default=0.5, p_win_contested=0.7, p_settle=0.2, p_collect=0.6
        # p_win = 0.2 + 0.8*(0.5 + 0.5*0.7) = 0.2 + 0.8*0.85 = 0.2 + 0.68 = 0.88
        # p_cash = 0.8 * 0.88 * 0.6 = 0.4224
        result = compute_p_cash_success(0.8, 0.5, 0.7, 0.2, 0.6)
        assert result == pytest.approx(0.4224, abs=0.001)

    def test_no_service(self):
        """If service fails (p_served=0), everything is 0."""
        result = compute_p_cash_success(0.0, 0.8, 0.9, 0.3, 0.7)
        assert result == 0.0

    def test_no_collection(self):
        """High win probability but no collection → 0."""
        result = compute_p_cash_success(1.0, 1.0, 1.0, 1.0, 0.0)
        assert result == 0.0

    def test_formula_components(self):
        """Verify the settle+default+contested formula."""
        p_settle = 0.3
        p_default = 0.4
        p_win_contested = 0.6
        # p_win = 0.3 + 0.7 * (0.4 + 0.6*0.6) = 0.3 + 0.7*0.76 = 0.3 + 0.532 = 0.832
        p_win = p_settle + (1 - p_settle) * (p_default + (1 - p_default) * p_win_contested)
        assert p_win == pytest.approx(0.832, abs=0.001)

        result = compute_p_cash_success(0.9, p_default, p_win_contested, p_settle, 0.7)
        expected = 0.9 * p_win * 0.7
        assert result == pytest.approx(expected, abs=0.001)


# =====================================================================
# G) count_events
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


# =====================================================================
# H) Drivers
# =====================================================================

class TestDrivers:
    def test_produces_max_five(self):
        ev = EvidenceResult(total=20, missing=["A", "B", "C"])
        ab = AbilityResult(insolvency_flag=True, score=15)
        wi = WillingnessResult(score=30, partial_payment=False)
        posteriors = {
            "served": BayesPosterior(8, 2, 0, 0, 8, 2, 0.8),
            "default": BayesPosterior(5, 5, 0, 0, 5, 5, 0.2),
            "settle": BayesPosterior(2, 8, 0, 0, 2, 8, 0.2),
            "collect": BayesPosterior(6, 4, 0, 0, 6, 4, 0.25),
        }
        drivers = compute_drivers(ev, ab, wi, 0.6, posteriors)
        assert len(drivers) <= 5

    def test_strong_case_gets_positive_drivers(self):
        ev = EvidenceResult(total=90, missing=[])
        ab = AbilityResult(score=80)
        wi = WillingnessResult(score=70, partial_payment=True)
        posteriors = {
            "served": BayesPosterior(8, 2, 0, 0, 8, 2, 0.8),
            "default": BayesPosterior(5, 5, 0, 0, 5, 5, 0.5),
            "settle": BayesPosterior(2, 8, 0, 0, 2, 8, 0.2),
            "collect": BayesPosterior(6, 4, 0, 0, 6, 4, 0.6),
        }
        drivers = compute_drivers(ev, ab, wi, 0.1, posteriors)
        positive = [d for d in drivers if d["direction"] == "positive"]
        assert len(positive) >= 2
