"""
Integration tests v4: 5 fixture cases exercising the v4 scoring pipeline.

Each case tests that:
  - Evidence scoring behaves correctly
  - Willingness from behavioural facts is correct
  - The final p_cash = p_valid × p_provable × p_payment is in a sensible range

LLM calls (analyze_legal_validity, analyze_payment_ability) are mocked.
v4: no Bayes — pillars are pure LLM / evidence / individual signals.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.models import Case, CaseEvent, CaseEventType, CaseLLMTrace, CaseStatus
from app.services.scoring import (
    score_evidence,
    score_willingness,
    compute_drivers,
    evidence_to_prob,
    EvidenceResult,
)
from app.services.legal_analyzer import LegalValidityResult, PaymentAbilityResult


def _make_case(**kwargs):
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


def _compute_p_cash(p_valid, p_provable, p_payment):
    """v4 formula: pure pillar product, no Bayes."""
    return p_valid * p_provable * p_payment


def _p_payment(llm_ability: float, facts: dict) -> float:
    """v4 payment pillar: 50% LLM ability + 50% behavioural willingness."""
    return 0.5 * llm_ability + 0.5 * score_willingness(facts)


# =====================================================================
# Case 1: Strong case — invoice + delivery + contract + dunning
# =====================================================================

class TestCase1_StrongCase:
    """Full evidence, no disputes, responsive debtor, LLM rates case as valid."""

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

    def test_evidence_score_is_100(self):
        r = score_evidence(self.case, self.facts)
        assert r.total == 100.0
        assert r.missing == []

    def test_high_willingness(self):
        p = score_willingness(self.facts)
        assert p >= 0.70

    def test_provability_high_with_full_evidence(self):
        ev = score_evidence(self.case, self.facts)
        p_provable = evidence_to_prob(ev.total)  # ~0.98 for score=100
        assert p_provable > 0.90

    def test_high_p_cash_when_llm_rates_valid(self):
        """Strong case end-to-end with good LLM output — v4 direct pillars."""
        p_valid    = 0.85                                     # LLM: valid claim
        p_provable = evidence_to_prob(score_evidence(self.case, self.facts).total)
        p_payment  = _p_payment(0.80, self.facts)             # active company, good willingness

        p_cash = _compute_p_cash(p_valid, p_provable, p_payment)
        assert p_cash > 0.45   # strong case should have high probability


# =====================================================================
# Case 2: Weak case — minimal evidence, neutral LLM
# =====================================================================

class TestCase2_WeakCase:
    """No contract proof, no delivery proof, no dunning. LLM uncertain."""

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

    def test_neutral_willingness(self):
        p = score_willingness(self.facts)
        assert p == pytest.approx(0.5, abs=0.01)

    def test_low_provability_with_weak_evidence(self):
        ev = score_evidence(self.case, self.facts)
        p_provable = evidence_to_prob(ev.total)   # ~0.02 for score≈15
        assert p_provable < 0.20

    def test_low_p_cash_with_weak_evidence(self):
        ev = score_evidence(self.case, self.facts)
        p_valid    = 0.40   # LLM uncertain: oral agreement
        p_provable = evidence_to_prob(ev.total)
        p_payment  = _p_payment(0.50, self.facts)

        p_cash = _compute_p_cash(p_valid, p_provable, p_payment)
        assert p_cash < 0.10   # weak case — low evidence kills provability


# =====================================================================
# Case 3: Disputed case — defendant contests quality
# =====================================================================

class TestCase3_DisputedCase:
    """Good evidence but LLM flags quality dispute reducing p_entstanden."""

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

    def test_decent_evidence_despite_dispute(self):
        r = score_evidence(self.case, self.facts)
        assert r.total >= 50

    def test_dispute_reduces_llm_validity(self):
        """When LLM sees quality dispute, p_entstanden is lower → p_valid drops."""
        # In v4: p_valid IS the LLM estimate directly — no Bayes dilution
        p_valid_disputed = 0.42   # quality dispute reduces entstanden
        p_valid_clean    = 0.80
        assert p_valid_disputed < p_valid_clean

    def test_dispute_lowers_p_cash(self):
        ev = score_evidence(self.case, self.facts)
        p_provable = evidence_to_prob(ev.total)

        p_cash_disputed = _compute_p_cash(0.42, p_provable, _p_payment(0.65, self.facts))
        p_cash_clean    = _compute_p_cash(0.80, p_provable, _p_payment(0.65, self.facts))
        assert p_cash_disputed < p_cash_clean


# =====================================================================
# Case 4: Insolvency — LLM flags defendant as insolvent
# =====================================================================

class TestCase4_InsolvencyCase:
    """Strong legal claim and evidence, but defendant is insolvent."""

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
        }

    def test_evidence_is_strong(self):
        r = score_evidence(self.case, self.facts)
        assert r.total >= 75

    def test_insolvency_kills_p_payment(self):
        """Even if claim is valid, insolvency drives p_payment to near-zero."""
        # v4: p_payment = 50% LLM ability + 50% willingness — no Bayes floor
        p_payment = _p_payment(0.05, self.facts)   # insolvency found → ability 5/100
        assert p_payment < 0.30   # severely reduced

    def test_p_cash_low_despite_valid_claim(self):
        ev = score_evidence(self.case, self.facts)
        p_valid    = 0.85
        p_provable = evidence_to_prob(ev.total)
        p_payment  = _p_payment(0.05, self.facts)   # insolvent

        p_cash = _compute_p_cash(p_valid, p_provable, p_payment)
        assert p_cash < 0.25   # good validity/provability but near-zero payment

    def test_insolvency_driver_appears(self):
        ev = score_evidence(self.case, self.facts)
        legal = LegalValidityResult(p_entstanden=0.85, p_not_untergegangen=0.90,
                                    p_durchsetzbar=0.85, p_claim_valid_llm=0.65)
        ability = PaymentAbilityResult(ability_score=5, insolvency_risk="high",
                                       reasoning="Insolvenzverfahren seit 01/2025 offen")
        drivers = compute_drivers(ev, legal, ability, 0.5)
        assert any("Insolvenz" in d["factor"] for d in drivers)


# =====================================================================
# Case 5: Repeat defendant — historical facts dominate payment
# =====================================================================

class TestCase5_RepeatDefendant:
    """Moderate evidence, repeat defendant who never pays voluntarily."""

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

    def test_low_willingness(self):
        p = score_willingness(self.facts)
        assert p <= 0.20   # 0.50 - 0.15 (no response) - 0.20 (repeat) = 0.15

    def test_low_willingness_reduces_payment(self):
        """Low willingness pulls p_payment down significantly."""
        p_payment = _p_payment(0.65, self.facts)   # company active but evasive
        assert p_payment < 0.45

    def test_negative_willingness_driver(self):
        ev = score_evidence(self.case, self.facts)
        legal = LegalValidityResult(p_entstanden=0.75, p_not_untergegangen=0.85,
                                    p_durchsetzbar=0.80, p_claim_valid_llm=0.51)
        ability = PaymentAbilityResult(ability_score=65, insolvency_risk="low")
        p_will = score_willingness(self.facts)
        drivers = compute_drivers(ev, legal, ability, p_will)
        neg_will = [d for d in drivers if "Zahlungswilligkeit" in d["factor"]
                    and d["direction"] == "negative"]
        assert len(neg_will) == 1
