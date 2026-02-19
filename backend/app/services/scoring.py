"""
Process-score engine v4: 3-pillar architecture, no Bayes.

The three pillars:

  1. p_claim_valid    = P(Anspruch entstanden AND nicht untergegangen AND durchsetzbar)
       100 % LLM legal analysis (GPT-4o + optional web search, jurisdiction-specific)
       LLM estimates three independent components and returns their product.

  2. p_claim_provable = P(Anspruch beweisbar | valid)
       100 % rule-based evidence score (contract, delivery proof, invoice, dunning)
       mapped to [0,1] via sigmoid.

  3. p_payment        = P(Zahlung tatsächlich erfolgt | judgment won)
       50 % ability (LLM web search: insolvency register, company status)
       50 % willingness (debtor behavioural facts, rule-based)

Final:
  p_cash_success = p_claim_valid × p_claim_provable × p_payment

  NN end-blend (optional): weight grows automatically with labelled training data.
  p_cash_final = (1 - w_nn) × p_cash  +  w_nn × p_nn

v4 changes vs v3:
  - Bayesian posteriors removed from the scoring calculation entirely.
    Statistical correction is handled exclusively by the NN end-blend,
    which learns systematic LLM calibration errors from actual case outcomes.
  - LLM prompt for p_entstanden sharpened: evidence gaps must NOT lower this score.
  - LLM prompt for p_durchsetzbar scoped to Verjährung only (ESCP eligibility
    is confirmed at intake and must not be re-assessed here).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import (
    Case,
    CaseLLMTrace,
    CaseProcessScore,
)
from .legal_analyzer import (
    LegalValidityResult,
    PaymentAbilityResult,
    analyze_legal_validity,
    analyze_payment_ability,
)


# ---------------------------------------------------------------------------
# A) Evidence Scorer  (rule-based, 0–100)
# ---------------------------------------------------------------------------

@dataclass
class EvidenceResult:
    contract: float = 0.0   # 0–25
    delivery: float = 0.0   # 0–30
    invoice:  float = 0.0   # 0–25
    dunning:  float = 0.0   # 0–20
    total:    float = 0.0   # 0–100
    missing:  list  = field(default_factory=list)


def score_evidence(case: Case, facts: dict | None = None) -> EvidenceResult:
    """Rule-based evidence scorer from case fields + LLM-extracted facts."""
    facts = facts or {}
    r = EvidenceResult()

    # --- Contract / Order (0–25) ---
    has_contract = bool(case.claim_basis or facts.get("has_contract"))
    if has_contract:
        r.contract = 15.0
        if facts.get("has_written_agreement"):
            r.contract = 25.0
    else:
        r.missing.append("Vertrag/Auftragsbestätigung")

    # --- Delivery / Performance (0–30) ---
    desc = (case.claim_description or "").lower()
    delivery_keywords = [
        "geliefert", "erbracht", "delivered", "performed",
        "lieferung", "leistung", "übergabe",
    ]
    if facts.get("has_delivery_proof"):
        r.delivery = 25.0
        if facts.get("has_acceptance"):
            r.delivery = 30.0
    elif any(kw in desc for kw in delivery_keywords):
        r.delivery = 15.0
    else:
        r.missing.append("Liefer-/Leistungsnachweis")

    # --- Invoice / Due date (0–25) ---
    if case.claim_amount and case.claim_amount > 0:
        r.invoice = 15.0
        if case.claim_interest_from_date or facts.get("has_due_date"):
            r.invoice = 25.0
    else:
        r.missing.append("Rechnung mit Fälligkeitsdatum")

    # --- Dunning / Reminder (0–20) ---
    evidence_text = (case.claim_evidence or "").lower()
    dunning_keywords = [
        "mahnung", "fristsetzung", "zahlungserinnerung",
        "reminder", "notice", "demand letter",
    ]
    if facts.get("has_dunning") or facts.get("has_reminder"):
        r.dunning = 15.0
        if facts.get("has_deadline_set"):
            r.dunning = 20.0
    elif any(kw in evidence_text for kw in dunning_keywords):
        r.dunning = 10.0
    else:
        r.missing.append("Mahnung/Fristsetzung")

    r.total = r.contract + r.delivery + r.invoice + r.dunning
    return r


# ---------------------------------------------------------------------------
# B) Willingness scorer  (behavioural facts, 0–1)
# ---------------------------------------------------------------------------

def score_willingness(facts: dict | None = None) -> float:
    """
    Estimate debtor payment willingness from behavioural signals.
    Returns probability 0–1 (not a 0–100 score).
    """
    facts = facts or {}
    p = 0.50  # neutral base

    if facts.get("responded_to_reminder") is True:
        p += 0.10
    elif facts.get("responded_to_reminder") is False:
        p -= 0.15

    if facts.get("partial_payment"):
        p += 0.15
    if facts.get("settlement_offered"):
        p += 0.10
    if facts.get("repeat_defendant"):
        p -= 0.20

    return max(0.05, min(0.95, p))


# ---------------------------------------------------------------------------
# C) Evidence → probability mapping  (logistic sigmoid)
# ---------------------------------------------------------------------------

def evidence_to_prob(score: float, midpoint: float = 50.0, steepness: float = 0.08) -> float:
    """Map evidence score (0–100) to probability (0–1) via sigmoid."""
    return 1.0 / (1.0 + math.exp(-steepness * (score - midpoint)))


# ---------------------------------------------------------------------------
# D) Monotonic fact merging  (True flags never revert to False)
# ---------------------------------------------------------------------------

def merge_facts_monotonic(merged: dict, new_facts: dict) -> dict:
    for key, value in new_facts.items():
        if key in merged and merged[key] is True and isinstance(value, bool):
            continue
        merged[key] = value
    return merged


# ---------------------------------------------------------------------------
# E) Drivers  (Top-5 human-readable reasons)
# ---------------------------------------------------------------------------

def compute_drivers(
    evidence: EvidenceResult,
    legal: LegalValidityResult,
    ability: PaymentAbilityResult,
    p_willingness: float,
) -> list[dict]:
    drivers: list[dict] = []

    # Legal validity signals
    if legal.p_entstanden < 0.5:
        drivers.append({
            "direction": "negative",
            "factor": "Anspruchsentstehung fraglich",
            "detail": legal.p_entstanden_reasoning or f"p={legal.p_entstanden:.0%}",
        })
    if legal.p_not_untergegangen < 0.7:
        drivers.append({
            "direction": "negative",
            "factor": "Mögliches Erlöschen des Anspruchs",
            "detail": legal.p_not_untergegangen_reasoning or f"p={legal.p_not_untergegangen:.0%}",
        })
    if legal.p_durchsetzbar < 0.5:
        drivers.append({
            "direction": "negative",
            "factor": "Durchsetzbarkeit fraglich",
            "detail": legal.p_durchsetzbar_reasoning or f"p={legal.p_durchsetzbar:.0%}",
        })
    if legal.p_claim_valid_llm >= 0.70:
        drivers.append({
            "direction": "positive",
            "factor": "Rechtlich starker Anspruch",
            "detail": f"Rechtliche Bewertung: {legal.p_claim_valid_llm:.0%}",
        })

    # Evidence / provability signals
    if evidence.missing:
        drivers.append({
            "direction": "negative",
            "factor": "Beweislücken",
            "detail": "Fehlend: " + ", ".join(evidence.missing),
        })
    elif evidence.total >= 75:
        drivers.append({
            "direction": "positive",
            "factor": "Starke Beweislage",
            "detail": f"{evidence.total:.0f}/100 Punkte",
        })

    # Payment ability
    if ability.insolvency_risk == "high":
        drivers.append({
            "direction": "negative",
            "factor": "Hohes Insolvenzrisiko",
            "detail": ability.reasoning[:120] if ability.reasoning else "Insolvenz-Flag gesetzt",
        })
    elif ability.insolvency_risk == "low" and ability.ability_score >= 70:
        drivers.append({
            "direction": "positive",
            "factor": "Gute Zahlungsfähigkeit",
            "detail": f"Ability-Score {ability.ability_score:.0f}/100",
        })

    # Willingness
    if p_willingness < 0.35:
        drivers.append({
            "direction": "negative",
            "factor": "Geringe Zahlungswilligkeit",
            "detail": f"Verhaltensbasiert: {p_willingness:.0%}",
        })
    elif p_willingness >= 0.65:
        drivers.append({
            "direction": "positive",
            "factor": "Gute Zahlungswilligkeit",
            "detail": f"Verhaltensbasiert: {p_willingness:.0%}",
        })

    # Sort: negatives first, limit to 5
    drivers.sort(key=lambda d: (d["direction"] == "positive", -len(d["detail"])))
    return drivers[:5]


# ---------------------------------------------------------------------------
# F) Top-level estimate()
# ---------------------------------------------------------------------------

async def estimate(case_id: UUID, db: AsyncSession) -> CaseProcessScore:
    """
    Compute v4 process score for a case.

    Flow:
      A) Merge LLM-extracted facts (monotonic)
      B) score_evidence  → evidence score 0–100
      C) score_willingness → behavioural p_willingness 0–1
      D) analyze_legal_validity (LLM + optional web search)
      E) analyze_payment_ability (LLM + optional web search)
      F) Compute pillars directly, NN end-blend as sole statistical correction
      G) Compute drivers and persist
    """
    # Load case
    case = (await db.execute(select(Case).where(Case.id == case_id))).scalar_one()

    # A) Merge extracted LLM facts (monotonic: True flags never revert)
    traces = list(
        (await db.execute(
            select(CaseLLMTrace)
            .where(CaseLLMTrace.case_id == case_id)
            .order_by(CaseLLMTrace.created_at)
        )).scalars().all()
    )
    merged_facts: dict = {}
    for t in traces:
        if t.extracted_facts:
            merge_facts_monotonic(merged_facts, t.extracted_facts)

    # B) Evidence score (rule-based)
    ev = score_evidence(case, merged_facts)

    # C) Willingness from behavioural facts (no LLM needed)
    p_willingness = score_willingness(merged_facts)

    # D) Legal validity: LLM + optional web search
    legal = await analyze_legal_validity(case, merged_facts)

    # E) Payment ability: LLM + optional web search (insolvency register etc.)
    ability = await analyze_payment_ability(case, merged_facts)

    # F) Compute pillars — no Bayes, direct signals only
    # ---- Pillar 1: p_claim_valid ----
    #   100% LLM: entstanden × nicht_untergegangen × durchsetzbar
    p_claim_valid = max(0.0, min(1.0, legal.p_claim_valid_llm))

    # ---- Pillar 2: p_claim_provable ----
    #   100% rule-based evidence score → sigmoid probability
    p_evidence = evidence_to_prob(ev.total)
    p_claim_provable = max(0.0, min(1.0, p_evidence))

    # ---- Pillar 3: p_payment ----
    #   50% LLM ability + 50% behavioural willingness
    p_ability_ind = ability.ability_score / 100.0
    p_payment     = max(0.0, min(1.0, 0.5 * p_ability_ind + 0.5 * p_willingness))

    # Final combined probability (pillar product)
    p_cash = p_claim_valid * p_claim_provable * p_payment

    # NN blending — optional, non-blocking; weight grows with training-set size
    p_nn_raw: float | None = None
    nn_pred_json: dict | None = None
    try:
        from .nn_service import predict_for_case  # lazy import avoids circular dep
        p_nn_raw, nn_pred_json = await predict_for_case(case, db)
        if p_nn_raw is not None and nn_pred_json is not None:
            w = nn_pred_json["nn_weight"]
            if w > 0.0:
                p_cash = (1.0 - w) * p_cash + w * p_nn_raw
                p_cash = max(0.0, min(1.0, p_cash))
    except Exception:
        pass  # NN failure must never break scoring

    # G) Drivers
    drivers = compute_drivers(ev, legal, ability, p_willingness)

    # Build detailed breakdowns for storage
    legal_validity_json = {
        "p_entstanden":                  legal.p_entstanden,
        "p_entstanden_reasoning":        legal.p_entstanden_reasoning,
        "p_not_untergegangen":           legal.p_not_untergegangen,
        "p_not_untergegangen_reasoning": legal.p_not_untergegangen_reasoning,
        "p_durchsetzbar":                legal.p_durchsetzbar,
        "p_durchsetzbar_reasoning":      legal.p_durchsetzbar_reasoning,
        "p_claim_valid_llm":             legal.p_claim_valid_llm,
        "applicable_law":                legal.applicable_law,
        "key_legal_issues":              legal.key_legal_issues,
        "searches_performed":            legal.searches_performed,
        "p_claim_valid":                 round(p_claim_valid, 4),
    }
    if legal.error:
        legal_validity_json["error"] = legal.error

    provability_json = {
        "evidence_score":     round(ev.total, 2),
        "evidence_breakdown": {
            "contract": ev.contract,
            "delivery": ev.delivery,
            "invoice":  ev.invoice,
            "dunning":  ev.dunning,
            "missing":  ev.missing,
        },
        "p_evidence_sigmoid": round(p_evidence, 4),
        "p_claim_provable":   round(p_claim_provable, 4),
    }

    payment_json = {
        "ability_score":     ability.ability_score,
        "insolvency_risk":   ability.insolvency_risk,
        "ability_reasoning": ability.reasoning,
        "ability_searches":  ability.searches_performed,
        "p_ability":         round(p_ability_ind, 4),
        "p_willingness":     round(p_willingness, 4),
        "p_payment":         round(p_payment, 4),
    }
    if ability.error:
        payment_json["ability_error"] = ability.error

    # Persist
    score = CaseProcessScore(
        case_id=case_id,
        p_claim_valid=round(p_claim_valid, 4),
        p_claim_provable=round(p_claim_provable, 4),
        p_payment=round(p_payment, 4),
        legal_validity_json=legal_validity_json,
        provability_json=provability_json,
        payment_analysis_json=payment_json,
        # Legacy fields (kept for backward compat)
        evidence_score=ev.total,
        evidence_breakdown={
            "contract": ev.contract,
            "delivery": ev.delivery,
            "invoice":  ev.invoice,
            "dunning":  ev.dunning,
            "missing":  ev.missing,
        },
        ability_score=ability.ability_score,
        ability_components={
            "ability_score":   ability.ability_score,
            "insolvency_risk": ability.insolvency_risk,
        },
        willingness_score=round(p_willingness * 100, 1),
        willingness_components={"p_willingness": p_willingness},
        p_cash_success=round(p_cash, 4),
        p_nn_prediction=round(p_nn_raw, 4) if p_nn_raw is not None else None,
        nn_prediction_json=nn_pred_json,
        priors_json={},
        posteriors_json={},
        observations_json={},
        drivers_json=drivers,
        model_version="v4",
    )
    db.add(score)
    await db.flush()
    await db.refresh(score)
    return score
