"""
Process-score engine v2: EvidenceScorer, BayesUpdater, AbilityScorer,
WillingnessScorer, and the top-level estimate() function.

v2 fixes:
- Logistic (sigmoid) evidence→probability mapping instead of linear
- Willingness score integrated into p_settle and p_collect
- Log-odds ability adjustment for p_collect (not raw multiplication)
- COLLECTION_FAILED event type for balanced Bayes collect rate
- Adjusted default priors for ESCP cross-border reality
- Prior validation (alpha/beta >= 0.01)
- Monotonic fact merging (True flags never revert to False)
- 90% credible interval stored alongside posterior mean
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, asdict
from typing import Optional
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


# ---------------------------------------------------------------------------
# A) Evidence Scorer  (rule-based, 0..100)
# ---------------------------------------------------------------------------

@dataclass
class EvidenceResult:
    contract: float = 0.0       # 0..25
    delivery: float = 0.0       # 0..30
    invoice: float = 0.0        # 0..25
    dunning: float = 0.0        # 0..20
    total: float = 0.0          # 0..100
    missing: list = field(default_factory=list)


def score_evidence(case: Case, facts: dict | None = None) -> EvidenceResult:
    """Rule-based evidence scorer from case fields + extracted LLM facts.

    If the LLM has flagged the claim as not derivable from the facts
    (claim_not_derivable=True), evidence score is forced to 0.
    """
    facts = facts or {}
    r = EvidenceResult()

    # Hard stop: if the claim is legally baseless (facts don't support relief),
    # no amount of documentation can produce a positive evidence score.
    if facts.get("claim_not_derivable"):
        r.missing.append("Kein ableitbarer Anspruch aus dem Vorbringen")
        return r

    # --- Contract / Order (0..25) ---
    has_contract = bool(case.claim_basis or facts.get("has_contract"))
    has_written_agreement = bool(facts.get("has_written_agreement"))
    if has_contract:
        r.contract = 15.0
        if has_written_agreement:
            r.contract = 25.0
    else:
        r.missing.append("Vertrag/Auftragsbestätigung")

    # --- Delivery / Performance proof (0..30) ---
    has_delivery_proof = bool(facts.get("has_delivery_proof"))
    has_acceptance = bool(facts.get("has_acceptance"))
    desc = (case.claim_description or "").lower()
    delivery_keywords = ["geliefert", "erbracht", "delivered", "performed",
                         "lieferung", "leistung", "übergabe"]
    desc_mentions_delivery = any(kw in desc for kw in delivery_keywords)
    if has_delivery_proof:
        r.delivery = 25.0
        if has_acceptance:
            r.delivery = 30.0
    elif desc_mentions_delivery:
        r.delivery = 15.0
    else:
        r.missing.append("Liefer-/Leistungsnachweis")

    # --- Invoice / Due date (0..25) ---
    has_invoice = bool(case.claim_amount and case.claim_amount > 0)
    has_due_date = bool(case.claim_interest_from_date or facts.get("has_due_date"))
    if has_invoice:
        r.invoice = 15.0
        if has_due_date:
            r.invoice = 25.0
    else:
        r.missing.append("Rechnung mit Fälligkeitsdatum")

    # --- Dunning / Reminder (0..20) ---
    has_dunning = bool(facts.get("has_dunning") or facts.get("has_reminder"))
    has_deadline = bool(facts.get("has_deadline_set"))
    evidence_text = (case.claim_evidence or "").lower()
    dunning_keywords = ["mahnung", "fristsetzung", "zahlungserinnerung",
                        "reminder", "notice", "demand letter"]
    text_mentions_dunning = any(kw in evidence_text for kw in dunning_keywords)
    if has_dunning:
        r.dunning = 15.0
        if has_deadline:
            r.dunning = 20.0
    elif text_mentions_dunning:
        r.dunning = 10.0
    else:
        r.missing.append("Mahnung/Fristsetzung")

    r.total = r.contract + r.delivery + r.invoice + r.dunning
    return r


# ---------------------------------------------------------------------------
# A2) Logistic evidence→probability mapping
# ---------------------------------------------------------------------------

def evidence_to_probability(score: float, contest_risk: float,
                            midpoint: float = 50.0,
                            steepness: float = 0.08,
                            cr_weight: float = 1.5) -> float:
    """
    Sigmoid mapping: evidence score (0-100) → win probability (0-1).

    Contestation risk shifts the curve leftward, meaning stronger evidence
    is needed to achieve the same win probability when contestation is high.
    This is more realistic than the old linear `score/100 * (1 - cr*0.5)`.

    midpoint=50: score of 50 without contestation → ~50% win probability
    steepness=0.08: controls how quickly probability rises with evidence
    cr_weight=1.5: how much contestation risk shifts the curve
    """
    logit = steepness * (score - midpoint) - cr_weight * contest_risk
    return 1.0 / (1.0 + math.exp(-logit))


# ---------------------------------------------------------------------------
# B) Contestation Risk  (0..1)
# ---------------------------------------------------------------------------

DISPUTE_KEYWORDS = [
    "nicht geliefert", "mangelhaft", "chargeback", "rücksendung",
    "support ticket", "reklamation", "widerspruch", "not delivered",
    "defective", "dispute", "refund", "warranty", "gewährleistung",
    "teillieferung", "fehlerhaft",
]


def contestation_risk(case: Case, facts: dict | None = None) -> float:
    """0..1 — higher means more likely the defendant will contest."""
    facts = facts or {}
    risk = 0.0

    text = " ".join([
        case.claim_description or "",
        case.claim_evidence or "",
        case.additional_information or "",
    ]).lower()

    hits = sum(1 for kw in DISPUTE_KEYWORDS if kw in text)
    risk += min(hits * 0.15, 0.6)

    if facts.get("defendant_disputes"):
        risk += 0.3
    if facts.get("quality_issue"):
        risk += 0.2

    return min(risk, 1.0)


# ---------------------------------------------------------------------------
# C) Ability Score  (0..100) = Zahlungsfähigkeit
# ---------------------------------------------------------------------------

@dataclass
class AbilityResult:
    insolvency_flag: bool = False
    company_active: bool = True
    vat_valid: bool = True
    score: float = 75.0
    components: dict = field(default_factory=dict)


def score_ability(case: Case, facts: dict | None = None) -> AbilityResult:
    """Ability score from register flags."""
    facts = facts or {}
    r = AbilityResult()

    r.insolvency_flag = bool(facts.get("insolvency_flag"))
    r.company_active = facts.get("company_active", True)
    r.vat_valid = facts.get("vat_valid", True)

    score = 75.0  # base

    if r.insolvency_flag:
        score -= 60.0
    if not r.company_active:
        score -= 30.0
    if not r.vat_valid:
        score -= 10.0

    # Defendant is a legal person → slight positive signal (assets)
    if case.defendant_is_legal_person:
        score += 5.0

    r.score = max(0.0, min(100.0, score))
    r.components = {
        "base": 75,
        "insolvency_flag": r.insolvency_flag,
        "company_active": r.company_active,
        "vat_valid": r.vat_valid,
        "is_legal_person": bool(case.defendant_is_legal_person),
    }
    return r


# ---------------------------------------------------------------------------
# D) Willingness Score  (0..100) = Zahlungswilligkeit
# ---------------------------------------------------------------------------

@dataclass
class WillingnessResult:
    responded_to_reminder: bool | None = None
    partial_payment: bool = False
    settlement_offered: bool = False
    repeat_defendant: bool = False
    score: float = 50.0
    components: dict = field(default_factory=dict)


def score_willingness(case: Case, facts: dict | None = None) -> WillingnessResult:
    """Willingness based on debtor behaviour signals."""
    facts = facts or {}
    r = WillingnessResult()

    r.responded_to_reminder = facts.get("responded_to_reminder")
    r.partial_payment = bool(facts.get("partial_payment"))
    r.settlement_offered = bool(facts.get("settlement_offered"))
    r.repeat_defendant = bool(facts.get("repeat_defendant"))

    score = 50.0  # neutral

    if r.responded_to_reminder is True:
        score += 10.0
    elif r.responded_to_reminder is False:
        score -= 15.0

    if r.partial_payment:
        score += 15.0
    if r.settlement_offered:
        score += 10.0
    if r.repeat_defendant:
        score -= 20.0

    r.score = max(0.0, min(100.0, score))
    r.components = {
        "base": 50,
        "responded_to_reminder": r.responded_to_reminder,
        "partial_payment": r.partial_payment,
        "settlement_offered": r.settlement_offered,
        "repeat_defendant": r.repeat_defendant,
    }
    return r


# ---------------------------------------------------------------------------
# E) Bayes Updater  (Beta-Binomial)
# ---------------------------------------------------------------------------

# Adjusted for ESCP cross-border reality:
# - served: 70% (was 80%) — cross-border service success is lower
# - settle: 30% (was 20%) — post-filing settlement rates are 25-40%
DEFAULT_PRIORS: dict[str, tuple[float, float]] = {
    "served":  (7.0, 3.0),   # ~70 % base service rate (cross-border ESCP)
    "default": (5.0, 5.0),   # ~50 % (reasonable variance)
    "settle":  (3.0, 7.0),   # ~30 % (post-filing settlement)
    "collect": (6.0, 4.0),   # ~60 %
}

# Which events count as success / trial for each rate
RATE_EVENT_MAP: dict[str, dict] = {
    "served": {
        "success": {CaseEventType.SERVICE_OK},
        "failure": {CaseEventType.SERVICE_FAIL},
    },
    "default": {
        "success": {CaseEventType.DEFAULT},
        "failure": {CaseEventType.DEFENDANT_RESPONDED},
    },
    "settle": {
        "success": {CaseEventType.SETTLED},
        "failure": {CaseEventType.JUDGMENT_WIN, CaseEventType.JUDGMENT_LOSS},
    },
    "collect": {
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
    mean: float  # posterior mean = α'/(α'+β')
    ci_low: float = 0.0   # 90% credible interval lower bound
    ci_high: float = 1.0  # 90% credible interval upper bound


def _beta_quantile(alpha: float, beta_param: float, p: float) -> float:
    """Approximate Beta quantile using the normal approximation.

    For production, scipy.stats.beta.ppf would be ideal, but we avoid
    the heavy dependency. The normal approximation is reasonable for
    alpha + beta >= 2.
    """
    if alpha <= 0 or beta_param <= 0:
        return 0.5
    mean = alpha / (alpha + beta_param)
    var = (alpha * beta_param) / ((alpha + beta_param) ** 2 * (alpha + beta_param + 1))
    std = math.sqrt(var) if var > 0 else 0
    # Normal quantile approximation for p=0.05 → z=-1.645, p=0.95 → z=1.645
    z = -1.645 if p < 0.5 else 1.645
    q = mean + z * std
    return max(0.0, min(1.0, q))


def bayes_update(
    alpha: float,
    beta_param: float,
    successes: int,
    trials: int,
) -> BayesPosterior:
    """Beta-Binomial posterior update with 90% credible interval."""
    failures = trials - successes
    a_post = alpha + successes
    b_post = beta_param + failures
    mean = a_post / (a_post + b_post) if (a_post + b_post) > 0 else 0.5
    ci_low = _beta_quantile(a_post, b_post, 0.05)
    ci_high = _beta_quantile(a_post, b_post, 0.95)
    return BayesPosterior(
        alpha_prior=alpha,
        beta_prior=beta_param,
        successes=successes,
        trials=trials,
        alpha_post=a_post,
        beta_post=b_post,
        mean=mean,
        ci_low=round(ci_low, 4),
        ci_high=round(ci_high, 4),
    )


async def get_priors(
    db: AsyncSession,
    rate_name: str,
    claim_subtype: str = "general",
    country: str = "*",
) -> tuple[float, float]:
    """Look up (alpha, beta) for a rate from priors_config, fallback to defaults."""
    # Try specific country first, then wildcard
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
            # Validate: priors must be positive to avoid undefined posteriors
            return (max(0.01, row.alpha), max(0.01, row.beta))

    # Try general subtype fallback
    if claim_subtype != "general":
        return await get_priors(db, rate_name, "general", country)

    return DEFAULT_PRIORS.get(rate_name, (2.0, 2.0))


def count_events(events: list[CaseEvent], rate_name: str) -> tuple[int, int]:
    """Count (successes, trials) for a rate from event log."""
    mapping = RATE_EVENT_MAP.get(rate_name, {})
    success_types = mapping.get("success", set())
    failure_types = mapping.get("failure", set())

    s = sum(1 for e in events if e.event_type in success_types)
    f = sum(1 for e in events if e.event_type in failure_types)
    return s, s + f


# ---------------------------------------------------------------------------
# F) Willingness-adjusted probabilities
# ---------------------------------------------------------------------------

def _logit(p: float) -> float:
    """Safe log-odds: clamp p to (0.001, 0.999) to avoid infinities."""
    p = max(0.001, min(0.999, p))
    return math.log(p / (1.0 - p))


def _sigmoid(x: float) -> float:
    """Numerically stable sigmoid."""
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    ex = math.exp(x)
    return ex / (1.0 + ex)


def adjust_settle_by_willingness(p_settle_base: float,
                                 willingness_score: float) -> float:
    """
    Higher willingness → higher settlement probability.
    Uses log-odds shift: willingness 50=neutral, >50 increases, <50 decreases.
    Strength factor 0.03 keeps the adjustment moderate.
    """
    shift = (willingness_score - 50.0) * 0.03
    return _sigmoid(_logit(p_settle_base) + shift)


def adjust_collect_by_ability(p_collect_base: float,
                              ability_score: float) -> float:
    """
    Log-odds adjustment instead of raw multiplication.
    Ability score 75=neutral baseline (no shift), lower reduces, higher increases.
    This prevents p_collect from being driven to zero by low ability
    and avoids double-counting vs Bayes posterior.
    """
    shift = (ability_score - 75.0) * 0.04
    return _sigmoid(_logit(p_collect_base) + shift)


def adjust_collect_by_willingness(p_collect: float,
                                  willingness_score: float) -> float:
    """
    Secondary willingness adjustment on collection:
    higher willingness signals voluntary compliance → better collection.
    Weaker effect than ability (factor 0.02).
    """
    shift = (willingness_score - 50.0) * 0.02
    return _sigmoid(_logit(p_collect) + shift)


# ---------------------------------------------------------------------------
# F2) p_cash_success formula  (unchanged algebraically)
# ---------------------------------------------------------------------------

def compute_p_cash_success(
    p_served: float,
    p_default: float,
    p_win_contested: float,
    p_settle: float,
    p_collect: float,
) -> float:
    """
    p_cash_success =
      p_served *
      ( p_settle + (1-p_settle) * ( p_default + (1-p_default)*p_win_contested ) ) *
      p_collect
    """
    p_win = p_settle + (1 - p_settle) * (p_default + (1 - p_default) * p_win_contested)
    return p_served * p_win * p_collect


# ---------------------------------------------------------------------------
# G) Drivers (Top-5 reasons)
# ---------------------------------------------------------------------------

def compute_drivers(
    evidence: EvidenceResult,
    ability: AbilityResult,
    willingness: WillingnessResult,
    contest_risk: float,
    posteriors: dict[str, BayesPosterior],
) -> list[dict]:
    """Compute Top-5 human-readable drivers."""
    drivers: list[dict] = []

    # Evidence gaps
    if evidence.total < 50:
        drivers.append({
            "direction": "negative",
            "factor": "Beweis-Score niedrig",
            "detail": f"Nur {evidence.total:.0f}/100. Fehlend: {', '.join(evidence.missing)}",
        })
    elif evidence.total >= 75:
        drivers.append({
            "direction": "positive",
            "factor": "Starke Beweislage",
            "detail": f"{evidence.total:.0f}/100 Punkte",
        })

    # Ability
    if ability.insolvency_flag:
        drivers.append({
            "direction": "negative",
            "factor": "Insolvenz-Flag",
            "detail": "Gegner möglicherweise insolvent",
        })
    if ability.score >= 70:
        drivers.append({
            "direction": "positive",
            "factor": "Zahlungsfähigkeit gut",
            "detail": f"Ability-Score {ability.score:.0f}/100",
        })

    # Willingness
    if willingness.score < 40:
        drivers.append({
            "direction": "negative",
            "factor": "Geringe Zahlungswilligkeit",
            "detail": f"Willingness-Score {willingness.score:.0f}/100",
        })
    elif willingness.score >= 65:
        drivers.append({
            "direction": "positive",
            "factor": "Gute Zahlungswilligkeit",
            "detail": f"Willingness-Score {willingness.score:.0f}/100",
        })
    if willingness.partial_payment:
        drivers.append({
            "direction": "positive",
            "factor": "Teilzahlung geleistet",
            "detail": "Signalisiert grundsätzliche Zahlungsbereitschaft",
        })

    # Contestation risk
    if contest_risk > 0.5:
        drivers.append({
            "direction": "negative",
            "factor": "Hohes Bestreitungsrisiko",
            "detail": f"Contestation Risk {contest_risk:.0%}",
        })

    # Bayes posteriors with low means
    for rate_name, post in posteriors.items():
        if post.mean < 0.3:
            labels = {
                "served": "Zustellung",
                "default": "Versäumnis",
                "settle": "Vergleich",
                "collect": "Inkasso",
            }
            drivers.append({
                "direction": "negative",
                "factor": f"Niedrige {labels.get(rate_name, rate_name)}-Rate",
                "detail": f"Posterior-Mittelwert {post.mean:.1%}",
            })

    # Sort: negatives first, then positives
    drivers.sort(key=lambda d: (d["direction"] == "positive", -len(d["detail"])))
    return drivers[:5]


# ---------------------------------------------------------------------------
# H) Monotonic fact merging
# ---------------------------------------------------------------------------

def merge_facts_monotonic(merged: dict, new_facts: dict) -> dict:
    """Merge extracted facts. Boolean True flags never revert to False.

    This prevents a later LLM trace from accidentally overriding an
    earlier confirmed fact (e.g. has_contract=True → not mentioned → False).
    """
    for key, value in new_facts.items():
        if key in merged and merged[key] is True and isinstance(value, bool):
            continue  # keep the True — don't let it revert
        merged[key] = value
    return merged


# ---------------------------------------------------------------------------
# I) Top-level estimate()
# ---------------------------------------------------------------------------

async def estimate(case_id: UUID, db: AsyncSession) -> CaseProcessScore:
    """Compute full process score for a case. Returns persisted CaseProcessScore."""
    # Load case
    result = await db.execute(select(Case).where(Case.id == case_id))
    case = result.scalar_one()

    # Load events
    ev_result = await db.execute(
        select(CaseEvent).where(CaseEvent.case_id == case_id).order_by(CaseEvent.created_at)
    )
    events = list(ev_result.scalars().all())

    # Gather extracted facts from LLM traces with monotonic merging
    trace_result = await db.execute(
        select(CaseLLMTrace).where(CaseLLMTrace.case_id == case_id).order_by(CaseLLMTrace.created_at)
    )
    traces = list(trace_result.scalars().all())
    merged_facts: dict = {}
    for t in traces:
        if t.extracted_facts:
            merge_facts_monotonic(merged_facts, t.extracted_facts)

    country = case.defendant_domicile_country or case.defendant_country or "*"
    claim_subtype = "general"  # extend later

    # A) Evidence
    ev = score_evidence(case, merged_facts)

    # B) Contestation risk
    cr = contestation_risk(case, merged_facts)

    # C) Ability
    ab = score_ability(case, merged_facts)

    # D) Willingness
    wi = score_willingness(case, merged_facts)

    # E) Bayes posteriors
    posteriors: dict[str, BayesPosterior] = {}
    priors_data: dict = {}
    obs_data: dict = {}
    post_data: dict = {}

    for rate_name in ["served", "default", "settle", "collect"]:
        alpha, beta_param = await get_priors(db, rate_name, claim_subtype, country)
        s, n = count_events(events, rate_name)
        post = bayes_update(alpha, beta_param, s, n)
        posteriors[rate_name] = post
        priors_data[rate_name] = {"alpha": alpha, "beta": beta_param}
        obs_data[rate_name] = {"successes": s, "trials": n}
        post_data[rate_name] = {
            "alpha": post.alpha_post,
            "beta": post.beta_post,
            "mean": round(post.mean, 4),
            "ci_low": post.ci_low,
            "ci_high": post.ci_high,
        }

    # F) Map scores → probabilities
    p_served = posteriors["served"].mean
    p_default = posteriors["default"].mean
    p_settle_base = posteriors["settle"].mean
    p_collect_base = posteriors["collect"].mean

    # Logistic evidence→probability mapping with contestation shift
    p_win_contested = evidence_to_probability(ev.total, cr)
    p_win_contested = max(0.0, min(1.0, p_win_contested))

    # Willingness modulates settlement probability
    p_settle = adjust_settle_by_willingness(p_settle_base, wi.score)

    # Ability adjusts collection via log-odds (not raw multiplication)
    p_collect = adjust_collect_by_ability(p_collect_base, ab.score)
    # Willingness also modulates collection (secondary effect)
    p_collect = adjust_collect_by_willingness(p_collect, wi.score)
    p_collect = max(0.0, min(1.0, p_collect))

    p_cash = compute_p_cash_success(p_served, p_default, p_win_contested, p_settle, p_collect)

    # F2) Hard override: if claim is not derivable from facts, force 0%
    claim_baseless = bool(merged_facts.get("claim_not_derivable"))
    if claim_baseless:
        p_win_contested = 0.0
        p_cash = 0.0

    # G) Drivers
    drivers = compute_drivers(ev, ab, wi, cr, posteriors)
    if claim_baseless:
        drivers.insert(0, {
            "direction": "negative",
            "factor": "Anspruch nicht ableitbar",
            "detail": "Das Vorbringen stützt das Begehren rechtlich nicht — 0% Obsiegenswahrscheinlichkeit",
        })

    # Persist
    score = CaseProcessScore(
        case_id=case_id,
        evidence_score=ev.total,
        evidence_breakdown={
            "contract": ev.contract,
            "delivery": ev.delivery,
            "invoice": ev.invoice,
            "dunning": ev.dunning,
            "missing": ev.missing,
        },
        ability_score=ab.score,
        ability_components=ab.components,
        willingness_score=wi.score,
        willingness_components=wi.components,
        p_served=round(p_served, 4),
        p_default=round(p_default, 4),
        p_win_contested=round(p_win_contested, 4),
        p_settle=round(p_settle, 4),
        p_collect=round(p_collect, 4),
        p_cash_success=round(p_cash, 4),
        priors_json=priors_data,
        posteriors_json=post_data,
        observations_json=obs_data,
        drivers_json=[asdict(d) if hasattr(d, '__dataclass_fields__') else d for d in drivers],
        model_version="v2",
    )
    db.add(score)
    await db.flush()
    await db.refresh(score)
    return score
