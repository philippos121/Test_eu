"""
Process-score engine: EvidenceScorer, BayesUpdater, AbilityScorer,
WillingnessScorer, and the top-level estimate() function.
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
    """Rule-based evidence scorer from case fields + extracted LLM facts."""
    facts = facts or {}
    r = EvidenceResult()

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

DEFAULT_PRIORS: dict[str, tuple[float, float]] = {
    "served":  (8.0, 2.0),   # ~80 % base service rate
    "default": (5.0, 5.0),   # ~50 %
    "settle":  (2.0, 8.0),   # ~20 %
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
        "failure": set(),  # no explicit failure event
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


def bayes_update(
    alpha: float,
    beta_param: float,
    successes: int,
    trials: int,
) -> BayesPosterior:
    """Beta-Binomial posterior update."""
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
            return (row.alpha, row.beta)

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
# F) p_cash_success formula
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
# H) Top-level estimate()
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

    # Gather extracted facts from LLM traces
    trace_result = await db.execute(
        select(CaseLLMTrace).where(CaseLLMTrace.case_id == case_id).order_by(CaseLLMTrace.created_at)
    )
    traces = list(trace_result.scalars().all())
    merged_facts: dict = {}
    for t in traces:
        if t.extracted_facts:
            merged_facts.update(t.extracted_facts)

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
        }

    # F) Map scores → probabilities
    p_served = posteriors["served"].mean
    p_default = posteriors["default"].mean
    p_settle = posteriors["settle"].mean
    p_collect_base = posteriors["collect"].mean

    # Adjust p_win_contested from evidence + contestation risk
    p_win_contested = (ev.total / 100.0) * (1 - cr * 0.5)
    p_win_contested = max(0.0, min(1.0, p_win_contested))

    # Adjust p_collect by ability score
    p_collect = p_collect_base * (ab.score / 100.0)
    p_collect = max(0.0, min(1.0, p_collect))

    p_cash = compute_p_cash_success(p_served, p_default, p_win_contested, p_settle, p_collect)

    # G) Drivers
    drivers = compute_drivers(ev, ab, wi, cr, posteriors)

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
        model_version="v1",
    )
    db.add(score)
    await db.flush()
    await db.refresh(score)
    return score
