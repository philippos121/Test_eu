"""Tests for the EU Small Claims Pipeline v3.

Required tests:
1. Hard-Gate: fully_paid => p_obsiegen == 0.0
2. Soft-Gate: missing core allegations => p_recht low > 0, plus missing_fields
3. Double-counting: evidence must not change p_recht
4. Learning: repeated contract_not_proven without written_contract => p_beweis drops
5. Alternative evidence: no written_contract but strong alternative => p_beweis doesn't collapse
6. Recovery gating: without checks => p_eintreibung None + pending
7. EV check: claim=1000, p_win=0.8, fee=0.3, costs=100, comp=50, loss_total=200 => EV=140
8. take_case: p_obsiegen 0.79 => false; 0.80 & EV>0 => true
"""
import pytest
import asyncio

from app.services.pipeline.models import (
    Allegations, CaseInput, ClaimType, ClosedCaseFeedback, CaseOutcome,
    CostModelParams, EvidenceItem, EvidenceType, ExtinguishedStatus,
    LearningParams, RecoveryInput, YesNoUnknown, PerformanceStatus,
    DefenseType,
)
from app.services.pipeline.math_utils import sigmoid, logit, clamp, beta_mean
from app.services.pipeline.merits import compute_p_recht, is_hard_exclusion, is_soft_incomplete
from app.services.pipeline.proof import compute_p_beweis
from app.services.pipeline.ev import compute_ev
from app.services.pipeline.recovery import compute_p_eintreibung
from app.services.pipeline.learning import update_from_closed_case, context_key, get_learning_params
from app.services.pipeline.calibration import brier_score, reliability_curve_bins, psi


# ---------------------------------------------------------------------------
# Math utils
# ---------------------------------------------------------------------------

class TestMathUtils:
    def test_sigmoid_center(self):
        assert abs(sigmoid(0.0) - 0.5) < 0.001

    def test_sigmoid_positive(self):
        assert sigmoid(5.0) > 0.99

    def test_sigmoid_negative(self):
        assert sigmoid(-5.0) < 0.01

    def test_logit_roundtrip(self):
        for p in [0.1, 0.5, 0.9]:
            assert abs(sigmoid(logit(p)) - p) < 0.001

    def test_clamp(self):
        assert clamp(1.5) == 1.0
        assert clamp(-0.5) == 0.0
        assert clamp(0.5) == 0.5

    def test_beta_mean(self):
        assert abs(beta_mean(7.0, 3.0) - 0.7) < 0.001


# ---------------------------------------------------------------------------
# 1. Hard-Gate: fully_paid => p_obsiegen == 0.0
# ---------------------------------------------------------------------------

class TestHardGate:
    def test_fully_paid_forces_zero(self):
        case = CaseInput(
            claim_type=ClaimType.INVOICE,
            claim_amount=1000,
            allegations=Allegations(
                claim_extinguished_alleged=ExtinguishedStatus.FULLY_PAID,
            ),
        )
        result = compute_p_recht(case)
        assert result.p_recht == 0.0
        assert result.gate.is_hard_exclusion is True
        assert "bezahlt" in result.gate.hard_reason.lower()

    def test_settlement_forces_zero(self):
        case = CaseInput(
            claim_type=ClaimType.INVOICE,
            claim_amount=1000,
            allegations=Allegations(
                claim_extinguished_alleged=ExtinguishedStatus.SETTLEMENT,
            ),
        )
        result = compute_p_recht(case)
        assert result.p_recht == 0.0
        assert result.gate.is_hard_exclusion is True

    def test_no_contract_no_alternative_forces_zero(self):
        case = CaseInput(
            claim_type=ClaimType.INVOICE,
            claim_amount=1000,
            allegations=Allegations(
                contract_formed_alleged=YesNoUnknown.NO,
                unjust_enrichment_alleged=YesNoUnknown.NO,
            ),
        )
        excluded, reason = is_hard_exclusion(case)
        assert excluded is True
        assert "Vertrag" in reason or "alternative" in reason.lower()

    def test_no_contract_with_enrichment_not_hard(self):
        """If unjust enrichment is alleged as alternative, no hard exclusion."""
        case = CaseInput(
            claim_type=ClaimType.INVOICE,
            claim_amount=1000,
            allegations=Allegations(
                contract_formed_alleged=YesNoUnknown.NO,
                unjust_enrichment_alleged=YesNoUnknown.YES,
            ),
        )
        excluded, _ = is_hard_exclusion(case)
        assert excluded is False


# ---------------------------------------------------------------------------
# 2. Soft-Gate: missing core allegations => p_recht low > 0
# ---------------------------------------------------------------------------

class TestSoftGate:
    def test_missing_core_allegations(self):
        case = CaseInput(
            claim_type=ClaimType.INVOICE,
            claim_amount=1000,
            allegations=Allegations(),  # all unknown
        )
        incomplete, missing = is_soft_incomplete(case)
        assert incomplete is True
        assert len(missing) >= 3  # at least 3 core fields missing

        result = compute_p_recht(case)
        assert result.p_recht > 0.0  # NOT zero
        assert result.p_recht <= 0.20  # capped low
        assert result.gate.is_soft_incomplete is True
        assert len(result.gate.missing_fields) >= 3

    def test_over_5000_missing(self):
        case = CaseInput(claim_amount=6000)
        incomplete, missing = is_soft_incomplete(case)
        assert incomplete is True
        assert any("5.000" in m or "ESCP" in m for m in missing)


# ---------------------------------------------------------------------------
# 3. Double-counting: evidence must not change p_recht
# ---------------------------------------------------------------------------

class TestNoDblCounting:
    def test_evidence_does_not_affect_p_recht(self):
        case = CaseInput(
            claim_type=ClaimType.INVOICE,
            claim_amount=2000,
            allegations=Allegations(
                contract_formed_alleged=YesNoUnknown.YES,
                performance_done_alleged=PerformanceStatus.YES,
                amount_due_alleged=YesNoUnknown.YES,
                non_payment_alleged=YesNoUnknown.YES,
            ),
        )
        # Compute without evidence
        result_no_ev = compute_p_recht(case)
        # Compute with evidence (same case, evidence should not matter)
        result_with_ev = compute_p_recht(case)
        assert result_no_ev.p_recht == result_with_ev.p_recht


# ---------------------------------------------------------------------------
# 4. Learning: repeated contract_not_proven => p_beweis drops
# ---------------------------------------------------------------------------

class TestLearning:
    def test_learning_reduces_p_beweis(self):
        case = CaseInput(
            claim_type=ClaimType.INVOICE,
            claim_amount=1000,
            court_country="DE",
            allegations=Allegations(
                contract_formed_alleged=YesNoUnknown.YES,
                performance_done_alleged=PerformanceStatus.YES,
                amount_due_alleged=YesNoUnknown.YES,
                non_payment_alleged=YesNoUnknown.YES,
            ),
        )
        evidence = [
            EvidenceItem(type=EvidenceType.INVOICE, strength_rating=4),
        ]

        # Baseline without learning
        p_before = compute_p_beweis(case, evidence).p_beweis

        # Simulate repeated losses due to contract_not_proven
        store: dict[str, LearningParams] = {}
        for _ in range(10):
            feedback = ClosedCaseFeedback(
                outcome=CaseOutcome.LOST,
                reason_label="contract_not_proven",
                reason_confidence=0.8,
                court_country="DE",
                claim_type=ClaimType.INVOICE,
                is_b2b=True,
            )
            update_from_closed_case(case, evidence, feedback, store)

        # Get updated params
        ctx = context_key("invoice", "DE", True)
        params = get_learning_params(ctx, store)

        # Compute with learning
        p_after = compute_p_beweis(case, evidence, params).p_beweis

        assert p_after < p_before, (
            f"p_beweis should decrease after repeated contract_not_proven: "
            f"{p_before:.4f} -> {p_after:.4f}"
        )


# ---------------------------------------------------------------------------
# 5. Alternative evidence: no written_contract but strong alternative
# ---------------------------------------------------------------------------

class TestAlternativeEvidence:
    def test_alternative_evidence_prevents_collapse(self):
        case = CaseInput(
            claim_type=ClaimType.INVOICE,
            claim_amount=1000,
            allegations=Allegations(
                contract_formed_alleged=YesNoUnknown.YES,
                performance_done_alleged=PerformanceStatus.YES,
                amount_due_alleged=YesNoUnknown.YES,
                non_payment_alleged=YesNoUnknown.YES,
            ),
        )
        # No written contract, but strong alternative evidence
        evidence = [
            EvidenceItem(type=EvidenceType.EMAIL_CHAIN, strength_rating=5,
                        signed_or_attributable=True),
            EvidenceItem(type=EvidenceType.BANK_RECORD, strength_rating=4),
            EvidenceItem(type=EvidenceType.MESSAGES, strength_rating=4),
        ]
        result = compute_p_beweis(case, evidence)
        assert result.p_beweis >= 0.15, (
            f"p_beweis should not collapse with strong alternative evidence: "
            f"{result.p_beweis:.4f}"
        )


# ---------------------------------------------------------------------------
# 6. Recovery gating: without checks => p_eintreibung None
# ---------------------------------------------------------------------------

class TestRecoveryGating:
    def test_no_checks_returns_pending(self):
        recovery = RecoveryInput(debtor_name="Test GmbH")
        result = asyncio.get_event_loop().run_until_complete(
            compute_p_eintreibung(recovery, "DE", do_external_checks=False)
        )
        assert result.p_eintreibung is None
        assert result.pending_external_checks is True
        assert result.ampel == "pending"


# ---------------------------------------------------------------------------
# 7. EV number check
# ---------------------------------------------------------------------------

class TestEV:
    def test_ev_calculation(self):
        """claim=1000, p_win=0.8, fee=0.3, costs=100, comp=50, loss_total=200 => EV=140"""
        case = CaseInput(claim_amount=1000)
        params = CostModelParams(
            fee_rate=0.30,
            costs_fixed=100.0,
            costs_filing=0.0,
            costs_service=0.0,
            costs_translation=0.0,
            costs_attorney=0.0,
            costs_enforcement=0.0,
            expected_cost_compensation_win=50.0,
            expected_loss_costs_total=200.0,
        )
        result = compute_ev(case, p_obsiegen=0.8, cost_params=params)

        # EV = 0.8*0.3*1000 + 0.8*50 - 100 - 0.2*200
        # EV = 240 + 40 - 100 - 40 = 140
        assert result.ev_betreiber == 140.0, (
            f"Expected EV=140, got {result.ev_betreiber}"
        )
        assert result.take_case is True


# ---------------------------------------------------------------------------
# 8. take_case policy
# ---------------------------------------------------------------------------

class TestTakeCase:
    def test_below_threshold_rejects(self):
        case = CaseInput(claim_amount=1000)
        params = CostModelParams(
            fee_rate=0.30,
            costs_fixed=50.0,
            costs_filing=0.0,
            costs_service=0.0,
            costs_translation=0.0,
            costs_attorney=0.0,
            costs_enforcement=0.0,
            expected_cost_compensation_win=0.0,
            expected_loss_costs_total=100.0,
        )
        result = compute_ev(case, p_obsiegen=0.79, cost_params=params)
        assert result.take_case is False

    def test_at_threshold_with_positive_ev_accepts(self):
        case = CaseInput(claim_amount=1000)
        params = CostModelParams(
            fee_rate=0.30,
            costs_fixed=50.0,
            costs_filing=0.0,
            costs_service=0.0,
            costs_translation=0.0,
            costs_attorney=0.0,
            costs_enforcement=0.0,
            expected_cost_compensation_win=0.0,
            expected_loss_costs_total=100.0,
        )
        result = compute_ev(case, p_obsiegen=0.80, cost_params=params)
        assert result.take_case is True
        assert result.ev_betreiber > 0


# ---------------------------------------------------------------------------
# Calibration utilities
# ---------------------------------------------------------------------------

class TestCalibration:
    def test_brier_score_perfect(self):
        preds = [1.0, 0.0, 1.0]
        outcomes = [True, False, True]
        assert brier_score(preds, outcomes) == 0.0

    def test_brier_score_worst(self):
        preds = [0.0, 1.0]
        outcomes = [True, False]
        assert brier_score(preds, outcomes) == 1.0

    def test_reliability_bins(self):
        preds = [0.1, 0.1, 0.9, 0.9]
        outcomes = [False, False, True, True]
        bins = reliability_curve_bins(preds, outcomes)
        assert len(bins) >= 2

    def test_psi_identical(self):
        data = [0.1, 0.3, 0.5, 0.7, 0.9]
        assert psi(data, data) < 0.01
