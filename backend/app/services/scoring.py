"""
Process-score engine v3: 3-pillar architecture.

The three pillars — and their weighting logic:

  1. p_claim_valid    = P(Anspruch entstanden AND nicht untergegangen AND durchsetzbar)
       70 % LLM legal analysis (GPT-4o + optional web search, jurisdiction-specific)
       30 % Bayesian statistics from comparable past cases

  2. p_claim_provable = P(Anspruch beweisbar | valid)
       40 % rule-based evidence score (contract, delivery proof, invoice, dunning)
       60 % Bayesian statistics (stronger statistical weight, as user specified)

  3. p_payment        = P(Zahlung tatsächlich erfolgt | judgment won)
       65 % individual case (50 % ability from LLM web search, 50 % willingness
             from debtor history) — strongly weighted to the individual
       35 % Bayesian statistics from comparable past cases

Final:
  p_cash_success = p_claim_valid × p_claim_provable × p_payment

v3 changes vs v2:
  - Replaced p_served / p_default / p_win_contested / p_settle / p_collect
    with three clean pillars (claim_valid, claim_provable, payment)
  - LLM legal analysis (legal_analyzer.py) drives p_claim_valid
  - Defendant ability via LLM + optional Tavily web-search (insolvency register)
  - Willingness from debtor behavioural facts (no LLM needed)
  - Bayesian rates renamed: valid / provable / payment
  - Evidence score unchanged (rule-based + LLM-extracted facts)
  - All weights explicit and documented
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import (
    Case,
    CaseEvent,
    CaseEventType,
    CaseLLMTrace,
    CaseProcessScore,
    PriorsConfig,
)
from .legal_analyzer import (
    LegalValidityResult,
    PaymentAbilityResult,
    analyze_legal_validity,
    analyze_payment_ability,
)


# ---------------------------------------------------------------------------
# Weights (explicit constants — easy to tune)
# ---------------------------------------------------------------------------

LEGAL_LLM_WEIGHT   = 0.70   # weight of LLM legal analysis in p_claim_valid
LEGAL_STAT_WEIGHT  = 0.30

PROVABLE_EV_WEIGHT  = 0.40   # weight of evidence score in p_claim_provable
PROVABLE_STAT_WEIGHT = 0.60  # statistics more strongly weighted here

PAYMENT_IND_WEIGHT  = 0.65   # weight of individual (ability+willingness) in p_payment
PAYMENT_STAT_WEIGHT = 0.35


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
# C) Bayesian updater  (Beta-Binomial)
# ---------------------------------------------------------------------------

# Priors for the three new rates
DEFAULT_PRIORS: dict[str, tuple[float, float]] = {
    "valid":    (6.0, 2.0),   # ~75 % — most filed claims are legally valid
    "provable": (4.0, 6.0),   # ~40 % — evidence is often weak in cross-border ESCP
    "payment":  (5.0, 5.0),   # ~50 % — uncertain base rate for actual payment
}

# Which event types count as success / trial for each rate
RATE_EVENT_MAP: dict[str, dict] = {
    "valid": {
        # A judgment win, default judgment, or settlement means the claim was valid
        "success": {
            CaseEventType.JUDGMENT_WIN,
            CaseEventType.DEFAULT,
            CaseEventType.SETTLED,
        },
        "failure": {CaseEventType.JUDGMENT_LOSS},
    },
    "provable": {
        # Only an adversarial judgment tells us whether the claim was provable
        # (default judgments don't test evidence)
        "success": {CaseEventType.JUDGMENT_WIN},
        "failure": {CaseEventType.JUDGMENT_LOSS},
    },
    "payment": {
        "success": {CaseEventType.PAYMENT_RECEIVED},
        "failure": {CaseEventType.COLLECTION_FAILED},
    },
}


@dataclass
class BayesPosterior:
    alpha_prior: float
    beta_prior: float
    successes: int
    trials: int
    alpha_post: float
    beta_post: float
    mean: float
    ci_low: float = 0.0
    ci_high: float = 1.0


def _beta_quantile(alpha: float, beta_param: float, p: float) -> float:
    """Normal approximation to Beta quantile (avoids scipy dependency)."""
    if alpha <= 0 or beta_param <= 0:
        return 0.5
    mean = alpha / (alpha + beta_param)
    var = (alpha * beta_param) / ((alpha + beta_param) ** 2 * (alpha + beta_param + 1))
    std = math.sqrt(var) if var > 0 else 0
    z = -1.645 if p < 0.5 else 1.645
    return max(0.0, min(1.0, mean + z * std))


def bayes_update(alpha: float, beta_param: float, successes: int, trials: int) -> BayesPosterior:
    """Beta-Binomial posterior update with 90 % credible interval."""
    failures = trials - successes
    a_post = alpha + successes
    b_post = beta_param + failures
    mean = a_post / (a_post + b_post) if (a_post + b_post) > 0 else 0.5
    return BayesPosterior(
        alpha_prior=alpha,
        beta_prior=beta_param,
        successes=successes,
        trials=trials,
        alpha_post=a_post,
        beta_post=b_post,
        mean=mean,
        ci_low=round(_beta_quantile(a_post, b_post, 0.05), 4),
        ci_high=round(_beta_quantile(a_post, b_post, 0.95), 4),
    )


async def get_priors(
    db: AsyncSession,
    rate_name: str,
    claim_subtype: str = "general",
    country: str = "*",
) -> tuple[float, float]:
    """Look up (alpha, beta) from priors_config; fallback to defaults."""
    for c in [country, "*"]:
        result = await db.execute(
            select(PriorsConfig).where(
                PriorsConfig.rate_name == rate_name,
                PriorsConfig.claim_subtype == claim_subtype,
                PriorsConfig.country == c,
            )
        )
        row = result.scalar_one_or_none()
        if row:
            return (max(0.01, row.alpha), max(0.01, row.beta))
    if claim_subtype != "general":
        return await get_priors(db, rate_name, "general", country)
    return DEFAULT_PRIORS.get(rate_name, (2.0, 2.0))


def count_events(events: list[CaseEvent], rate_name: str) -> tuple[int, int]:
    """Count (successes, trials) for a rate from the case event log."""
    mapping = RATE_EVENT_MAP.get(rate_name, {})
    success_types = mapping.get("success", set())
    failure_types = mapping.get("failure", set())
    s = sum(1 for e in events if e.event_type in success_types)
    f = sum(1 for e in events if e.event_type in failure_types)
    return s, s + f


# ---------------------------------------------------------------------------
# D) Blending: weighted combination of LLM/evidence and statistics
# ---------------------------------------------------------------------------

def blend(individual_p: float, stat_p: float, individual_weight: float) -> float:
    """Linear blend of an individual signal and a statistical prior."""
    stat_weight = 1.0 - individual_weight
    return individual_weight * individual_p + stat_weight * stat_p


# ---------------------------------------------------------------------------
# E) Evidence → probability mapping  (logistic sigmoid)
# ---------------------------------------------------------------------------

def evidence_to_prob(score: float, midpoint: float = 50.0, steepness: float = 0.08) -> float:
    """Map evidence score (0–100) to probability (0–1) via sigmoid."""
    return 1.0 / (1.0 + math.exp(-steepness * (score - midpoint)))


# ---------------------------------------------------------------------------
# F) Monotonic fact merging  (True flags never revert to False)
# ---------------------------------------------------------------------------

def merge_facts_monotonic(merged: dict, new_facts: dict) -> dict:
    for key, value in new_facts.items():
        if key in merged and merged[key] is True and isinstance(value, bool):
            continue
        merged[key] = value
    return merged


# ---------------------------------------------------------------------------
# G) Drivers  (Top-5 human-readable reasons)
# ---------------------------------------------------------------------------

def compute_drivers(
    evidence: EvidenceResult,
    legal: LegalValidityResult,
    ability: PaymentAbilityResult,
    p_willingness: float,
    posteriors: dict[str, BayesPosterior],
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

    # Statistical priors — low posterior means
    for rate_name, post in posteriors.items():
        if post.mean < 0.3:
            labels = {"valid": "Anspruchs-Gültigkeit", "provable": "Beweisbarkeit", "payment": "Zahlung"}
            drivers.append({
                "direction": "negative",
                "factor": f"Geringe historische {labels.get(rate_name, rate_name)}-Rate",
                "detail": f"Posterior: {post.mean:.1%} ({post.successes}/{post.trials} vergleichbare Fälle)",
            })

    # Sort: negatives first, limit to 5
    drivers.sort(key=lambda d: (d["direction"] == "positive", -len(d["detail"])))
    return drivers[:5]


# ---------------------------------------------------------------------------
# H) Top-level estimate()
# ---------------------------------------------------------------------------

async def estimate(case_id: UUID, db: AsyncSession) -> CaseProcessScore:
    """
    Compute v3 process score for a case.

    Flow:
      A) Merge LLM-extracted facts (monotonic)
      B) score_evidence  → evidence score 0–100
      C) score_willingness → behavioural p_willingness 0–1
      D) analyze_legal_validity (LLM + optional web search)
      E) analyze_payment_ability (LLM + optional web search)
      F) Bayesian posteriors for "valid", "provable", "payment"
      G) Blend all components
      H) Compute drivers and persist
    """
    # Load case
    case = (await db.execute(select(Case).where(Case.id == case_id))).scalar_one()

    # Load events
    events = list(
        (await db.execute(
            select(CaseEvent)
            .where(CaseEvent.case_id == case_id)
            .order_by(CaseEvent.created_at)
        )).scalars().all()
    )

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

    country      = case.defendant_domicile_country or case.defendant_country or "*"
    claim_subtype = "general"  # extend per claim type later

    # B) Evidence score (rule-based)
    ev = score_evidence(case, merged_facts)

    # C) Willingness from behavioural facts (no LLM needed)
    p_willingness = score_willingness(merged_facts)

    # D) Legal validity: LLM + optional web search
    legal = await analyze_legal_validity(case, merged_facts)

    # E) Payment ability: LLM + optional web search (insolvency register etc.)
    ability = await analyze_payment_ability(case, merged_facts)

    # F) Bayesian posteriors for 3 rates
    posteriors: dict[str, BayesPosterior] = {}
    priors_data: dict = {}
    obs_data: dict = {}
    post_data: dict = {}

    for rate_name in ["valid", "provable", "payment"]:
        alpha, beta_param = await get_priors(db, rate_name, claim_subtype, country)
        s, n = count_events(events, rate_name)
        post = bayes_update(alpha, beta_param, s, n)
        posteriors[rate_name] = post
        priors_data[rate_name] = {"alpha": alpha, "beta": beta_param}
        obs_data[rate_name]    = {"successes": s, "trials": n}
        post_data[rate_name]   = {
            "alpha": post.alpha_post,
            "beta": post.beta_post,
            "mean": round(post.mean, 4),
            "ci_low": post.ci_low,
            "ci_high": post.ci_high,
        }

    # G) Blend each pillar
    # ---- Pillar 1: p_claim_valid ----
    #   70% LLM legal analysis + 30% statistics
    stat_valid   = posteriors["valid"].mean
    p_claim_valid = blend(legal.p_claim_valid_llm, stat_valid, LEGAL_LLM_WEIGHT)
    p_claim_valid = max(0.0, min(1.0, p_claim_valid))

    # ---- Pillar 2: p_claim_provable ----
    #   40% evidence score (→ sigmoid probability) + 60% statistics
    p_evidence    = evidence_to_prob(ev.total)
    stat_provable = posteriors["provable"].mean
    p_claim_provable = blend(p_evidence, stat_provable, PROVABLE_EV_WEIGHT)
    p_claim_provable = max(0.0, min(1.0, p_claim_provable))

    # ---- Pillar 3: p_payment ----
    #   Individual component = 50% ability + 50% willingness
    #   65% individual + 35% statistics
    p_ability_ind  = ability.ability_score / 100.0
    p_individual   = 0.5 * p_ability_ind + 0.5 * p_willingness
    stat_payment   = posteriors["payment"].mean
    p_payment      = blend(p_individual, stat_payment, PAYMENT_IND_WEIGHT)
    p_payment      = max(0.0, min(1.0, p_payment))

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

    # H) Drivers
    drivers = compute_drivers(ev, legal, ability, p_willingness, posteriors)

    # Build detailed breakdowns for storage
    legal_validity_json = {
        "p_entstanden":             legal.p_entstanden,
        "p_entstanden_reasoning":   legal.p_entstanden_reasoning,
        "p_not_untergegangen":      legal.p_not_untergegangen,
        "p_not_untergegangen_reasoning": legal.p_not_untergegangen_reasoning,
        "p_durchsetzbar":           legal.p_durchsetzbar,
        "p_durchsetzbar_reasoning": legal.p_durchsetzbar_reasoning,
        "p_claim_valid_llm":        legal.p_claim_valid_llm,
        "applicable_law":           legal.applicable_law,
        "key_legal_issues":         legal.key_legal_issues,
        "searches_performed":       legal.searches_performed,
        "stat_valid":               round(stat_valid, 4),
        "llm_weight":               LEGAL_LLM_WEIGHT,
        "stat_weight":              LEGAL_STAT_WEIGHT,
        "p_claim_valid":            round(p_claim_valid, 4),
    }
    if legal.error:
        legal_validity_json["error"] = legal.error

    provability_json = {
        "evidence_score":       round(ev.total, 2),
        "evidence_breakdown":   {
            "contract": ev.contract,
            "delivery": ev.delivery,
            "invoice":  ev.invoice,
            "dunning":  ev.dunning,
            "missing":  ev.missing,
        },
        "p_evidence_sigmoid":   round(p_evidence, 4),
        "stat_provable":        round(stat_provable, 4),
        "ev_weight":            PROVABLE_EV_WEIGHT,
        "stat_weight":          PROVABLE_STAT_WEIGHT,
        "p_claim_provable":     round(p_claim_provable, 4),
    }

    payment_json = {
        "ability_score":        ability.ability_score,
        "insolvency_risk":      ability.insolvency_risk,
        "ability_reasoning":    ability.reasoning,
        "ability_searches":     ability.searches_performed,
        "p_ability":            round(p_ability_ind, 4),
        "p_willingness":        round(p_willingness, 4),
        "p_individual":         round(p_individual, 4),
        "stat_payment":         round(stat_payment, 4),
        "ind_weight":           PAYMENT_IND_WEIGHT,
        "stat_weight":          PAYMENT_STAT_WEIGHT,
        "p_payment":            round(p_payment, 4),
    }
    if ability.error:
        payment_json["ability_error"] = ability.error

    # Persist
    score = CaseProcessScore(
        case_id=case_id,
        # New v3 pillars
        p_claim_valid=round(p_claim_valid, 4),
        p_claim_provable=round(p_claim_provable, 4),
        p_payment=round(p_payment, 4),
        legal_validity_json=legal_validity_json,
        provability_json=provability_json,
        payment_analysis_json=payment_json,
        # Legacy fields (kept for backward compat, populated from v3 equivalents)
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
            "ability_score": ability.ability_score,
            "insolvency_risk": ability.insolvency_risk,
        },
        willingness_score=round(p_willingness * 100, 1),
        willingness_components={"p_willingness": p_willingness},
        p_cash_success=round(p_cash, 4),
        p_nn_prediction=round(p_nn_raw, 4) if p_nn_raw is not None else None,
        nn_prediction_json=nn_pred_json,
        priors_json=priors_data,
        posteriors_json=post_data,
        observations_json=obs_data,
        drivers_json=drivers,
        model_version="v3",
    )
    db.add(score)
    await db.flush()
    await db.refresh(score)
    return score
