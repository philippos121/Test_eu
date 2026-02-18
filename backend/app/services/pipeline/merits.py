"""p_recht computation — legal merit assessment.

Three sub-probabilities:
  p_entstanden:          Claim arose (elements fulfilled from allegations)
  p_nicht_untergegangen: Claim not extinguished
  p_durchsetzbar:        Claim enforceable (standing, jurisdiction, limitation)

p_recht = p_entstanden * p_nicht_untergegangen * p_durchsetzbar

IMPORTANT: p_recht must NOT be computed without prior legal research.
Evidence items are NOT used here (prevents double-counting with p_beweis).
"""
from __future__ import annotations

from .math_utils import clamp
from .models import (
    Allegations,
    CaseInput,
    ClaimType,
    DefenseType,
    ExtinguishedStatus,
    GateResult,
    LegalResearchResult,
    MeritsResult,
    YesNoUnknown,
)


def is_hard_exclusion(case: CaseInput) -> tuple[bool, str]:
    """Check for hard gates where p_obsiegen must be exactly 0.0.

    Only triggers on unambiguous exclusions:
    - claim_extinguished == fully_paid / settlement / release
    - No contract alleged AND claim_type requires contract AND no alternative basis
    - Confirmed wrong defendant / no standing
    """
    a = case.allegations

    # Hard gate: claim fully extinguished
    if a.claim_extinguished_alleged == ExtinguishedStatus.FULLY_PAID:
        return True, "Forderung als vollständig bezahlt angegeben."
    if a.claim_extinguished_alleged == ExtinguishedStatus.SETTLEMENT:
        return True, "Forderung durch Vergleich erledigt."
    if a.claim_extinguished_alleged == ExtinguishedStatus.RELEASE:
        return True, "Forderung durch Erlass erloschen."

    # Hard gate: no contract AND claim requires contract AND no alternative
    contract_required = case.claim_type in (
        ClaimType.INVOICE, ClaimType.WERKLOHN,
    )
    if (contract_required
        and a.contract_formed_alleged == YesNoUnknown.NO
        and a.unjust_enrichment_alleged != YesNoUnknown.YES):
        return True, (
            "Kein Vertragsschluss behauptet und keine alternative Rechtsgrundlage "
            "(z.B. Bereicherung) geltend gemacht."
        )

    # Hard gate: confirmed wrong defendant
    if a.wrong_defendant_risk == YesNoUnknown.YES and a.standing_risk == YesNoUnknown.YES:
        return True, "Falscher Beklagter / fehlende Aktivlegitimation bestätigt."

    return False, ""


def is_soft_incomplete(case: CaseInput) -> tuple[bool, list[str]]:
    """Check for soft gates where core data is missing/inconsistent.

    Returns (is_incomplete, list_of_missing_fields).
    When triggered: p_recht is capped low (0.05–0.20) but NOT 0.0.
    """
    a = case.allegations
    missing: list[str] = []

    if a.contract_formed_alleged == YesNoUnknown.UNKNOWN:
        missing.append("Vertragsschluss unklar (contract_formed_alleged)")
    if a.performance_done_alleged.value == "unknown":
        missing.append("Leistungserbringung unklar (performance_done_alleged)")
    if a.amount_due_alleged == YesNoUnknown.UNKNOWN:
        missing.append("Forderungshöhe unklar (amount_due_alleged)")
    if a.non_payment_alleged == YesNoUnknown.UNKNOWN:
        missing.append("Nichtzahlung unklar (non_payment_alleged)")

    if case.claim_amount <= 0:
        missing.append("Keine Forderungshöhe angegeben (claim_amount)")
    if case.claim_amount > 5000:
        missing.append("Forderung über 5.000 EUR — nicht ESCP-fähig")

    return (len(missing) > 0, missing)


def compute_p_recht(
    case: CaseInput,
    legal_research: LegalResearchResult | None = None,
) -> MeritsResult:
    """Compute p_recht from allegations and legal research.

    Must be called AFTER legal research is performed.
    Does NOT consider evidence items (that's p_beweis).
    """
    reasoning: list[str] = []

    # ── Hard gate check ──
    hard_excluded, hard_reason = is_hard_exclusion(case)
    if hard_excluded:
        return MeritsResult(
            p_entstanden=0.0,
            p_nicht_untergegangen=0.0,
            p_durchsetzbar=0.0,
            p_recht=0.0,
            confidence=0.95,
            gate=GateResult(is_hard_exclusion=True, hard_reason=hard_reason),
            legal_research=legal_research,
            reasoning=[f"Hard-Gate: {hard_reason}"],
        )

    # ── Soft gate check ──
    soft_incomplete, missing_fields = is_soft_incomplete(case)
    soft_cap = None
    if soft_incomplete:
        soft_cap = 0.20 if len(missing_fields) <= 2 else 0.10
        reasoning.append(
            f"Soft-Gate: {len(missing_fields)} Kerndaten fehlen/unklar → "
            f"p_recht gedeckelt auf {soft_cap:.0%}."
        )

    # ── p_entstanden: claim arose ──
    p_entstanden = _compute_p_entstanden(case, legal_research, reasoning)

    # ── p_nicht_untergegangen: claim not extinguished ──
    p_nicht_untergegangen = _compute_p_nicht_untergegangen(case, reasoning)

    # ── p_durchsetzbar: enforceable ──
    p_durchsetzbar = _compute_p_durchsetzbar(case, reasoning)

    # ── Combine ──
    p_recht = p_entstanden * p_nicht_untergegangen * p_durchsetzbar

    # Apply soft cap
    if soft_cap is not None and p_recht > soft_cap:
        p_recht = soft_cap

    # Research quality adjustment
    confidence = 0.7
    if legal_research:
        if legal_research.research_status == "complete":
            confidence = 0.85
        elif legal_research.research_status == "partial":
            confidence = 0.65
        else:  # insufficient
            confidence = 0.45
            p_recht *= 0.8  # Reduce slightly when research insufficient

    p_recht = clamp(p_recht, 0.0, 1.0)

    return MeritsResult(
        p_entstanden=round(p_entstanden, 4),
        p_nicht_untergegangen=round(p_nicht_untergegangen, 4),
        p_durchsetzbar=round(p_durchsetzbar, 4),
        p_recht=round(p_recht, 4),
        confidence=round(confidence, 2),
        gate=GateResult(
            is_soft_incomplete=soft_incomplete,
            missing_fields=missing_fields,
            soft_cap=soft_cap,
        ),
        legal_research=legal_research,
        reasoning=reasoning,
    )


def _compute_p_entstanden(
    case: CaseInput,
    research: LegalResearchResult | None,
    reasoning: list[str],
) -> float:
    """How complete/consistent are the required elements from allegations?"""
    a = case.allegations
    scores: list[float] = []

    # Contract basis
    if a.contract_formed_alleged == YesNoUnknown.YES:
        scores.append(0.9)
        reasoning.append("Vertragsschluss behauptet → +0.9")
    elif a.contract_formed_alleged == YesNoUnknown.NO:
        if a.unjust_enrichment_alleged == YesNoUnknown.YES:
            scores.append(0.4)
            reasoning.append("Kein Vertrag, aber Bereicherungsanspruch behauptet → +0.4")
        else:
            scores.append(0.05)
            reasoning.append("Kein Vertrag behauptet, keine Alternative → +0.05")
    else:
        scores.append(0.3)
        reasoning.append("Vertragsschluss unklar → +0.3")

    # Performance
    if a.performance_done_alleged.value == "yes":
        scores.append(0.9)
    elif a.performance_done_alleged.value == "partial":
        scores.append(0.6)
    elif a.performance_done_alleged.value == "no":
        scores.append(0.1)
    else:
        scores.append(0.4)

    # Amount/due date
    if a.amount_due_alleged == YesNoUnknown.YES:
        scores.append(0.9)
    elif a.amount_due_alleged == YesNoUnknown.NO:
        scores.append(0.1)
    else:
        scores.append(0.4)

    # Non-payment
    if a.non_payment_alleged == YesNoUnknown.YES:
        scores.append(0.95)
    elif a.non_payment_alleged == YesNoUnknown.NO:
        scores.append(0.05)
    else:
        scores.append(0.5)

    # Use legal research match score to adjust
    if research and research.ranked_legal_bases:
        best_match = max(b.match_score for b in research.ranked_legal_bases)
        scores.append(best_match)
        reasoning.append(f"Rechtsrecherche match_score: {best_match:.2f}")

    if not scores:
        return 0.5
    return sum(scores) / len(scores)


def _compute_p_nicht_untergegangen(case: CaseInput, reasoning: list[str]) -> float:
    """Probability that the claim has not been extinguished."""
    a = case.allegations

    if a.claim_extinguished_alleged == ExtinguishedStatus.NO:
        return 0.95

    if a.claim_extinguished_alleged == ExtinguishedStatus.PARTLY_PAID:
        reasoning.append("Teilzahlung gemeldet — Forderung teilweise untergegangen.")
        return 0.7

    if a.claim_extinguished_alleged == ExtinguishedStatus.UNKNOWN:
        return 0.85  # Assume not extinguished unless claimed

    # fully_paid / settlement / release should be caught by hard gate
    return 0.0


def _compute_p_durchsetzbar(case: CaseInput, reasoning: list[str]) -> float:
    """Probability the claim is enforceable (standing, jurisdiction, limitation)."""
    a = case.allegations
    risk_factors: list[float] = []

    if a.standing_risk == YesNoUnknown.YES:
        risk_factors.append(0.3)
        reasoning.append("Aktivlegitimation-Risiko → Durchsetzbarkeit gesenkt.")
    if a.wrong_defendant_risk == YesNoUnknown.YES:
        risk_factors.append(0.3)
        reasoning.append("Falscher-Beklagter-Risiko → Durchsetzbarkeit gesenkt.")
    if a.limitation_risk == YesNoUnknown.YES:
        risk_factors.append(0.4)
        reasoning.append("Verjährungsrisiko → Durchsetzbarkeit gesenkt.")
    if a.jurisdiction_risk == YesNoUnknown.YES:
        risk_factors.append(0.4)
        reasoning.append("Zuständigkeitsrisiko → Durchsetzbarkeit gesenkt.")

    if not risk_factors:
        return 0.95

    # Product of (1 - risk) for each factor
    p = 1.0
    for rf in risk_factors:
        p *= (1.0 - rf)
    return max(0.05, p)
