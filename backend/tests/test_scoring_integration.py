"""
Integration tests: 5 fixture cases exercising the full scoring pipeline.
Tests run without a DB by mocking the async session.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.models import Case, CaseEvent, CaseEventType, CaseLLMTrace, CaseStatus
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
)


def _make_case(**kwargs):
    """Create a real-ish Case mock with sensible defaults."""
    case = MagicMock(spec=Case)
    defaults = {
        "id": uuid4(),
        "claim_basis": None,
        "claim_description": None,
        "claim_evidence": None,
        "claim_amount": None,
        "claim_currency": "EUR",
        "claim_interest_from_date": None,
        "additional_information": None,
        "defendant_is_legal_person": False,
        "defendant_domicile_country": None,
        "defendant_country": None,
        "status": CaseStatus.EVIDENCE_COLLECTION,
    }
    defaults.update(kwargs)
    for k, v in defaults.items():
        setattr(case, k, v)
    return case


def _make_event(event_type):
    ev = MagicMock(spec=CaseEvent)
    ev.event_type = event_type
    return ev


# =====================================================================
# Case 1: Strong case — invoice + delivery + contract + dunning
# =====================================================================

class TestCase1_StrongCase:
    """Full evidence, no disputes, active company, responsive debtor."""

    def setup_method(self):
        self.case = _make_case(
            claim_basis="Kaufvertrag vom 10.01.2025, schriftlich",
            claim_description="Ware am 20.01.2025 geliefert und vom Kunden abgenommen",
            claim_evidence="Rechnung Nr. 2025-042, Mahnung mit Fristsetzung vom 15.02.2025",
            claim_amount=2500.0,
            claim_interest_from_date="2025-02-01",
            defendant_is_legal_person=True,
            defendant_country="DE",
        )
        self.facts = {
            "has_contract": True,
            "has_written_agreement": True,
            "has_delivery_proof": True,
            "has_acceptance": True,
            "has_due_date": True,
            "has_dunning": True,
            "has_deadline_set": True,
            "responded_to_reminder": True,
            "partial_payment": True,
        }
        self.events = [
            _make_event(CaseEventType.FILED),
            _make_event(CaseEventType.SERVICE_OK),
            _make_event(CaseEventType.SERVICE_OK),
        ]

    def test_evidence_score_is_100(self):
        r = score_evidence(self.case, self.facts)
        assert r.total == 100.0
        assert r.missing == []

    def test_low_contestation_risk(self):
        risk = contestation_risk(self.case, self.facts)
        assert risk < 0.15

    def test_high_ability(self):
        r = score_ability(self.case, self.facts)
        assert r.score >= 75

    def test_high_willingness(self):
        r = score_willingness(self.case, self.facts)
        assert r.score >= 70

    def test_high_p_cash_success(self):
        ev = score_evidence(self.case, self.facts)
        cr = contestation_risk(self.case, self.facts)
        ab = score_ability(self.case, self.facts)

        # Bayes: 2 service successes
        s_served, n_served = count_events(self.events, "served")
        post_served = bayes_update(8, 2, s_served, n_served)

        p_win_contested = (ev.total / 100) * (1 - cr * 0.5)
        p_collect = post_served.mean * (ab.score / 100)  # simplified

        p_cash = compute_p_cash_success(
            post_served.mean, 0.5, p_win_contested, 0.2, p_collect,
        )
        assert p_cash > 0.3  # strong case should have decent probability


# =====================================================================
# Case 2: Weak case — minimal evidence
# =====================================================================

class TestCase2_WeakCase:
    """No contract proof, no delivery proof, no dunning."""

    def setup_method(self):
        self.case = _make_case(
            claim_description="Mündliche Vereinbarung über Dienstleistung",
            claim_amount=800.0,
        )
        self.facts = {}

    def test_low_evidence_score(self):
        r = score_evidence(self.case, self.facts)
        assert r.total <= 40
        assert len(r.missing) >= 2

    def test_moderate_contestation(self):
        risk = contestation_risk(self.case, self.facts)
        assert risk == 0.0  # no dispute keywords

    def test_p_cash_with_weak_evidence(self):
        ev = score_evidence(self.case, self.facts)
        p_win_contested = ev.total / 100  # very low
        p_cash = compute_p_cash_success(0.8, 0.5, p_win_contested, 0.2, 0.6)
        assert p_cash < 0.4  # weak case


# =====================================================================
# Case 3: Disputed case — defendant contests
# =====================================================================

class TestCase3_DisputedCase:
    """Good evidence but defendant disputes quality."""

    def setup_method(self):
        self.case = _make_case(
            claim_basis="Werkvertrag",
            claim_description="Leistung erbracht, Beklagter behauptet mangelhaft",
            claim_evidence="Rechnung, Mahnung, Reklamation des Beklagten",
            claim_amount=3000.0,
            claim_interest_from_date="2025-03-01",
        )
        self.facts = {
            "has_contract": True,
            "has_delivery_proof": True,
            "has_due_date": True,
            "has_dunning": True,
            "defendant_disputes": True,
            "quality_issue": True,
        }
        self.events = [
            _make_event(CaseEventType.FILED),
            _make_event(CaseEventType.SERVICE_OK),
            _make_event(CaseEventType.DEFENDANT_RESPONDED),
        ]

    def test_high_contestation_risk(self):
        risk = contestation_risk(self.case, self.facts)
        assert risk >= 0.4

    def test_evidence_still_decent(self):
        r = score_evidence(self.case, self.facts)
        assert r.total >= 50

    def test_win_contested_reduced_by_dispute(self):
        ev = score_evidence(self.case, self.facts)
        cr = contestation_risk(self.case, self.facts)
        p_win_contested = (ev.total / 100) * (1 - cr * 0.5)
        # Should be noticeably lower than evidence alone
        assert p_win_contested < ev.total / 100

    def test_defendant_responded_affects_default_rate(self):
        s, n = count_events(self.events, "default")
        assert s == 0  # no default
        assert n == 1  # 1 responded trial
        post = bayes_update(5, 5, s, n)
        assert post.mean < 0.5  # lower than prior


# =====================================================================
# Case 4: Insolvency case — defendant insolvent
# =====================================================================

class TestCase4_InsolvencyCase:
    """Strong evidence but defendant is insolvent."""

    def setup_method(self):
        self.case = _make_case(
            claim_basis="Kaufvertrag",
            claim_description="Ware geliefert",
            claim_evidence="Rechnung, Mahnung",
            claim_amount=4500.0,
            claim_interest_from_date="2025-01-15",
            defendant_is_legal_person=True,
        )
        self.facts = {
            "has_contract": True,
            "has_written_agreement": True,
            "has_delivery_proof": True,
            "has_due_date": True,
            "has_dunning": True,
            "insolvency_flag": True,
            "company_active": False,
        }

    def test_ability_very_low(self):
        r = score_ability(self.case, self.facts)
        assert r.score <= 10  # 75 + 5 - 60 - 30 = -10 → clamped to 0

    def test_insolvency_driver_present(self):
        ev = score_evidence(self.case, self.facts)
        ab = score_ability(self.case, self.facts)
        wi = score_willingness(self.case, self.facts)
        cr = contestation_risk(self.case, self.facts)
        posteriors = {
            "served": bayes_update(8, 2, 0, 0),
            "default": bayes_update(5, 5, 0, 0),
            "settle": bayes_update(2, 8, 0, 0),
            "collect": bayes_update(6, 4, 0, 0),
        }
        drivers = compute_drivers(ev, ab, wi, cr, posteriors)
        insolvency_drivers = [d for d in drivers if "Insolvenz" in d["factor"]]
        assert len(insolvency_drivers) == 1

    def test_p_collect_crushed_by_insolvency(self):
        ab = score_ability(self.case, self.facts)
        p_collect_base = 0.6  # from default prior
        p_collect = p_collect_base * (ab.score / 100)
        assert p_collect < 0.1  # very low collection probability


# =====================================================================
# Case 5: Repeat defendant — willingness signal
# =====================================================================

class TestCase5_RepeatDefendant:
    """Moderate evidence, repeat defendant who never pays."""

    def setup_method(self):
        self.case = _make_case(
            claim_basis="Dienstleistungsvertrag",
            claim_description="Leistung erbracht am 01.02.2025",
            claim_evidence="Rechnung vom 15.02.2025",
            claim_amount=1200.0,
        )
        self.facts = {
            "has_contract": True,
            "has_delivery_proof": True,
            "repeat_defendant": True,
            "responded_to_reminder": False,
        }
        # Events: service ok but defendant defaulted, then no payment
        self.events = [
            _make_event(CaseEventType.FILED),
            _make_event(CaseEventType.SERVICE_OK),
            _make_event(CaseEventType.DEFAULT),
            _make_event(CaseEventType.JUDGMENT_WIN),
        ]

    def test_low_willingness(self):
        r = score_willingness(self.case, self.facts)
        assert r.score <= 20  # 50 - 15 - 20 = 15

    def test_default_rate_high(self):
        s, n = count_events(self.events, "default")
        assert s == 1
        assert n == 1  # 1 default out of 1 trial
        post = bayes_update(5, 5, s, n)
        assert post.mean > 0.5  # higher than prior

    def test_collect_rate_low_no_payment(self):
        s, n = count_events(self.events, "collect")
        assert s == 0
        assert n == 0  # no collect events yet
        post = bayes_update(6, 4, s, n)
        assert post.mean == pytest.approx(0.6, abs=0.01)

    def test_end_to_end_score_moderate(self):
        ev = score_evidence(self.case, self.facts)
        cr = contestation_risk(self.case, self.facts)
        ab = score_ability(self.case, self.facts)
        wi = score_willingness(self.case, self.facts)

        # Build posteriors from events
        served_post = bayes_update(8, 2, *count_events(self.events, "served"))
        default_post = bayes_update(5, 5, *count_events(self.events, "default"))
        settle_post = bayes_update(2, 8, *count_events(self.events, "settle"))
        collect_post = bayes_update(6, 4, *count_events(self.events, "collect"))

        p_win_contested = (ev.total / 100) * (1 - cr * 0.5)
        p_collect = collect_post.mean * (ab.score / 100)

        p_cash = compute_p_cash_success(
            served_post.mean, default_post.mean, p_win_contested,
            settle_post.mean, p_collect,
        )
        # Should be moderate — decent service/default but low willingness
        assert 0.1 < p_cash < 0.7

    def test_negative_drivers(self):
        ev = score_evidence(self.case, self.facts)
        ab = score_ability(self.case, self.facts)
        wi = score_willingness(self.case, self.facts)
        cr = contestation_risk(self.case, self.facts)
        posteriors = {
            "served": bayes_update(8, 2, 1, 1),
            "default": bayes_update(5, 5, 1, 1),
            "settle": bayes_update(2, 8, 0, 0),
            "collect": bayes_update(6, 4, 0, 0),
        }
        drivers = compute_drivers(ev, ab, wi, cr, posteriors)
        willingness_neg = [d for d in drivers if "Zahlungswilligkeit" in d.get("factor", "")]
        assert len(willingness_neg) >= 1
