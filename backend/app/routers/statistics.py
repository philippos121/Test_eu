"""Statistics API — admin-only endpoints for completed-case analytics,
seed data, prior updates, and expected-value calculations.

Endpoints:
  GET  /api/statistics/overview       — aggregate stats + posteriors + completed case detail
  POST /api/statistics/seed           — seed 30 fictional cases (admin)
  POST /api/statistics/test-case      — add a custom test case and recalculate (admin)
  POST /api/statistics/update-priors  — recalculate PriorsConfig from event outcomes (admin)
  GET  /api/cases/{case_id}/expected-value — per-case expected-value breakdown (admin)
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import get_current_user
from ..database import get_db
from ..models import (
    Case,
    CaseEvent,
    CaseEventType,
    CaseLLMTrace,
    CaseProcessScore,
    CaseStatus,
    ChatMessage,
    Document,
    PriorsConfig,
    User,
)
from ..services.scoring import (
    DEFAULT_PRIORS,
    RATE_EVENT_MAP,
    bayes_update,
    count_events,
    estimate,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/statistics", tags=["statistics"])


# ---------------------------------------------------------------------------
# Pydantic response schemas
# ---------------------------------------------------------------------------

class PosteriorItem(BaseModel):
    name: str
    label: str
    prior_alpha: float
    prior_beta: float
    successes: int
    trials: int
    post_alpha: float
    post_beta: float
    mean: float
    ci_low: float
    ci_high: float


class PipelineScores(BaseModel):
    """Pipeline v3 3-tier probability scores."""
    p_recht: float = 0.0
    p_entstanden: float = 0.0
    p_nicht_untergegangen: float = 1.0
    p_durchsetzbar: float = 1.0
    p_beweis: float = 0.0
    p_obsiegen: float = 0.0
    p_eintreibung: Optional[float] = None
    p_gesamt: Optional[float] = None
    ev_betreiber: Optional[float] = None
    take_case: Optional[bool] = None
    claim_type: str = "invoice"
    court_country: str = "DE"
    element_scores: dict = {}


class CompletedCaseDetail(BaseModel):
    id: UUID
    title: str
    claim_amount: Optional[float] = None
    claim_currency: Optional[str] = None
    outcome_success: bool
    outcome: str = ""           # won/lost/settled/withdrawn
    p_cash_success: Optional[float] = None
    net_ev: Optional[float] = None
    pipeline: Optional[PipelineScores] = None
    # Detailed fields for the 100 fictional cases
    description: str = ""
    evidence_desc: str = ""
    assessment: str = ""
    claimant_name: str = ""
    claimant_country: str = ""
    defendant_name: str = ""
    defendant_country: str = ""
    court_country: str = ""
    is_cross_border: bool = False
    is_seed: bool = False       # True for seed/test cases, False for real cases
    is_test: bool = False       # True for user-created test cases


class LearningInsight(BaseModel):
    rate_name: str
    label: str
    prior_mean: float
    posterior_mean: float
    successes: int
    failures: int
    interpretation: str


class PipelineAggregates(BaseModel):
    """Aggregate pipeline v3 statistics across all cases."""
    avg_p_recht: float = 0.0
    avg_p_beweis: float = 0.0
    avg_p_obsiegen: float = 0.0
    avg_p_eintreibung: Optional[float] = None
    avg_p_gesamt: Optional[float] = None
    avg_ev: float = 0.0
    take_case_rate: float = 0.0
    total_evaluated: int = 0


class BayesLearningStep(BaseModel):
    """A step in the Bayesian learning progression."""
    step: int
    element: str
    alpha: float
    beta: float
    mean: float
    context_key: str = ""
    case_outcome: str = ""


class OverviewResponse(BaseModel):
    total_cases: int
    completed_cases: int
    success_rate: float
    avg_recovery: Optional[float] = None
    posteriors: List[PosteriorItem]
    completed_cases_detail: List[CompletedCaseDetail]
    learning_insights: List[LearningInsight] = []
    pipeline_aggregates: Optional[PipelineAggregates] = None
    bayes_learning_progression: List[BayesLearningStep] = []


class SeedResponse(BaseModel):
    fictional_cases_created: int
    historical_aggregate_events_created: int
    message: str


class TestCaseRequest(BaseModel):
    """Request body for creating a custom test case."""
    title: str = "Benutzerdefinierter Testfall"
    claim_type: str = "invoice"
    claimant_name: str = "Testkläger"
    claimant_country: str = "DE"
    defendant_name: str = "Testbeklagter"
    defendant_country: str = "DE"
    court_country: str = "DE"
    claim_amount: float = 1000.0
    description: str = ""
    evidence_desc: str = ""
    p_recht: float = 0.5
    p_beweis: float = 0.5
    p_eintreibung: Optional[float] = 0.7
    outcome: str = "won"  # won/lost/settled/withdrawn


class TestCaseResponse(BaseModel):
    case_id: UUID
    message: str
    pipeline: PipelineScores


class UpdatedPriorItem(BaseModel):
    rate_name: str
    old_alpha: float
    old_beta: float
    new_alpha: float
    new_beta: float
    successes: int
    failures: int
    trials: int
    posterior_mean: float


class UpdatePriorsResponse(BaseModel):
    rates_updated: List[str]
    priors: List[UpdatedPriorItem]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _require_admin(user: User = Depends(get_current_user)) -> User:
    """Dependency that ensures the current user has admin privileges."""
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Nur für Administratoren.",
        )
    return user


def _is_successful(events: list[CaseEvent]) -> bool:
    """A completed case is considered successful if it has a PAYMENT_RECEIVED event."""
    return any(e.event_type == CaseEventType.PAYMENT_RECEIVED for e in events)


def _outcome_from_events(events: list[CaseEvent]) -> str:
    """Determine outcome string from events."""
    types = {e.event_type for e in events}
    if CaseEventType.PAYMENT_RECEIVED in types:
        if CaseEventType.SETTLED in types:
            return "settled"
        return "won"
    if CaseEventType.JUDGMENT_LOSS in types:
        return "lost"
    if CaseEventType.COLLECTION_FAILED in types:
        return "lost"
    if CaseEventType.SERVICE_FAIL in types:
        return "withdrawn"
    return "lost"


RATE_LABELS: dict[str, str] = {
    "served": "Zustellungsrate",
    "default": "Versäumnisrate",
    "settle": "Vergleichsrate",
    "collect": "Inkassorate",
}

DISPLAY_RATE_LABELS: dict[str, str] = {
    "merit": "Schlüssigkeitsprüfung",
    "default_settle": "Versäumnis-/Vergleichsrate",
    "collect": "Inkassorate",
}

DISPLAY_RATE_EVENT_MAP: dict[str, dict] = {
    "merit": {
        "success": {CaseEventType.SERVICE_OK},
        "failure": {CaseEventType.SERVICE_FAIL},
    },
    "default_settle": {
        "success": {CaseEventType.DEFAULT, CaseEventType.SETTLED},
        "failure": {CaseEventType.JUDGMENT_WIN, CaseEventType.JUDGMENT_LOSS},
    },
    "collect": {
        "success": {CaseEventType.PAYMENT_RECEIVED},
        "failure": {CaseEventType.COLLECTION_FAILED},
    },
}

DISPLAY_DEFAULT_PRIORS: dict[str, tuple[float, float]] = {
    "merit": (7.0, 3.0),
    "default_settle": (5.0, 5.0),
    "collect": (6.0, 4.0),
}


def _estimate_court_fees(claim_amount: float) -> float:
    """Simplified ESCP court fee estimation."""
    return max(35.0, claim_amount * 0.035)


SERVICE_COSTS_FLAT = 75.0
COMMISSION_RATE = 0.30


def _estimate_attorney_costs(claim_amount: float) -> float:
    """Estimate portal's attorney/legal operational costs."""
    if claim_amount <= 500:
        return 50.0
    elif claim_amount <= 2000:
        return 50.0 + (claim_amount - 500) * 0.05
    else:
        return 125.0 + (claim_amount - 2000) * 0.03


def _estimate_opponent_costs(claim_amount: float) -> float:
    """Estimate opponent's costs that portal must pay on loss."""
    return _estimate_attorney_costs(claim_amount) * 1.2


def _compute_net_ev(claim_amount: float, outcome_success: bool) -> float:
    """Compute net expected value for a *completed* case."""
    court_fees = _estimate_court_fees(claim_amount)
    attorney_costs = _estimate_attorney_costs(claim_amount)
    service_costs = SERVICE_COSTS_FLAT

    if outcome_success:
        commission = claim_amount * COMMISSION_RATE
        cost_compensation = court_fees + attorney_costs
        own_costs = court_fees + attorney_costs + service_costs
        return round(commission + cost_compensation - own_costs, 2)
    else:
        own_costs = court_fees + attorney_costs + service_costs
        opponent_costs = _estimate_opponent_costs(claim_amount)
        return round(-(own_costs + opponent_costs), 2)


def _build_insight_text(rate_name: str, prior_mean: float, posterior_mean: float,
                        successes: int, failures: int) -> str:
    """Generate a human-readable learning insight for a display rate."""
    total = successes + failures
    delta = posterior_mean - prior_mean
    direction = "gestiegen" if delta > 0 else "gesunken"
    abs_delta = abs(delta) * 100

    if rate_name == "merit":
        if total == 0:
            return "Noch keine Beobachtungen zur Schlüssigkeitsprüfung."
        return (
            f"Von {total} geprüften Fällen bestanden {successes} die Schlüssigkeitsprüfung "
            f"({failures} abgewiesen). Die geschätzte Rate ist von "
            f"{prior_mean:.0%} auf {posterior_mean:.0%} {direction} ({abs_delta:+.1f} Pp.)."
        )
    elif rate_name == "default_settle":
        if total == 0:
            return "Noch keine Beobachtungen zur Versäumnis-/Vergleichsrate."
        return (
            f"Von {total} zugestellten Fällen endeten {successes} durch Versäumnisurteil oder "
            f"Vergleich ({failures} gingen in die streitige Verhandlung). "
            f"Rate: {prior_mean:.0%} → {posterior_mean:.0%} ({abs_delta:+.1f} Pp.)."
        )
    elif rate_name == "collect":
        if total == 0:
            return "Noch keine Beobachtungen zur Inkassorate."
        return (
            f"Von {total} titulierten Forderungen wurden {successes} erfolgreich beigetrieben "
            f"({failures} scheiterten, z.B. wegen Insolvenz). "
            f"Rate: {prior_mean:.0%} → {posterior_mean:.0%} ({abs_delta:+.1f} Pp.)."
        )
    return ""


def _compute_pipeline_v3(scenario: dict, claim_amount: float) -> dict:
    """Compute pipeline v3 scores from a scenario's p_recht, p_beweis, p_eintreibung."""
    p_recht = scenario["p_recht"]
    p_beweis = scenario["p_beweis"]
    p_eintreibung = scenario.get("p_eintreibung")

    p_obsiegen = round(p_recht * p_beweis, 4)
    p_gesamt = round(p_obsiegen * p_eintreibung, 4) if p_eintreibung is not None else None

    # EV calculation
    fee_rate = 0.30
    costs = 35.0 + 75.0 + 50.0  # filing + service + enforcement
    loss_costs = 200.0
    if p_obsiegen > 0:
        ev = round(
            p_obsiegen * fee_rate * claim_amount
            - costs
            - (1 - p_obsiegen) * loss_costs,
            2,
        )
    else:
        ev = round(-costs - loss_costs, 2)

    take_case = p_obsiegen >= 0.80 and ev > 0

    # Element scores derived from p_beweis
    base = p_beweis
    element_scores = {
        "contract_basis": round(min(base + 0.10, 1.0), 4),
        "performance": round(min(base + 0.05, 1.0), 4),
        "amount_due": round(min(base + 0.02, 1.0), 4),
        "non_payment": round(base, 4),
    }

    return {
        "p_recht": p_recht,
        "p_entstanden": round(min(p_recht * 1.05, 1.0 if p_recht > 0 else 0.0), 4),
        "p_nicht_untergegangen": 0.95 if p_recht > 0 else 0.0,
        "p_durchsetzbar": 0.97 if p_recht > 0 else 0.0,
        "p_beweis": p_beweis,
        "p_obsiegen": p_obsiegen,
        "p_eintreibung": p_eintreibung,
        "p_gesamt": p_gesamt,
        "ev_betreiber": ev,
        "take_case": take_case,
        "claim_type": scenario.get("claim_type", "invoice"),
        "court_country": scenario.get("court_country", "DE"),
        "element_scores": element_scores,
    }


EVENT_TYPE_MAP = {
    "FILED": CaseEventType.FILED,
    "SERVICE_OK": CaseEventType.SERVICE_OK,
    "SERVICE_FAIL": CaseEventType.SERVICE_FAIL,
    "DEFENDANT_RESPONDED": CaseEventType.DEFENDANT_RESPONDED,
    "DEFAULT": CaseEventType.DEFAULT,
    "SETTLED": CaseEventType.SETTLED,
    "JUDGMENT_WIN": CaseEventType.JUDGMENT_WIN,
    "JUDGMENT_LOSS": CaseEventType.JUDGMENT_LOSS,
    "PAYMENT_RECEIVED": CaseEventType.PAYMENT_RECEIVED,
    "COLLECTION_FAILED": CaseEventType.COLLECTION_FAILED,
}


def _build_seed_from_scenarios(admin_user_id: UUID) -> tuple[list[Case], list[CaseEvent], list[dict]]:
    """Build fictional cases from SEED_SCENARIOS.

    Returns (cases, events, pipeline_data) where pipeline_data is a list of
    {"case_id": UUID, "pipeline_v3": dict, "outcome": bool} dicts.
    """
    from .seed_scenarios import SEED_SCENARIOS

    now = datetime.utcnow()
    all_cases: list[Case] = []
    all_events: list[CaseEvent] = []
    all_pipeline: list[dict] = []

    for idx, sc in enumerate(SEED_SCENARIOS):
        case_id = uuid.uuid4()
        amount = sc["amount"]
        outcome = sc.get("outcome", "lost")
        is_success = outcome in ("won", "settled")
        is_cb = sc.get("is_cross_border",
                        sc.get("cl_country", "DE") != sc.get("def_country", "DE"))

        case_status = CaseStatus.COMPLETED
        if outcome == "withdrawn":
            case_status = CaseStatus.REJECTED

        c = Case(
            id=case_id,
            user_id=admin_user_id,
            title=sc["title"],
            status=case_status,
            court_country=sc.get("court_country", "DE"),
            claimant_is_legal_person=True,
            claimant_name=sc.get("cl_name", f"Kläger {idx+1}"),
            claimant_country=sc.get("cl_country", "DE"),
            defendant_is_legal_person=True,
            defendant_name=sc.get("def_name", f"Beklagter {idx+1}"),
            defendant_country=sc.get("def_country", "DE"),
            is_cross_border=is_cb,
            claim_amount=amount,
            claim_currency="EUR",
            claim_description=sc.get("description", ""),
            claim_evidence=sc.get("evidence_desc", ""),
            assessment_summary=sc.get("assessment", ""),
            success_probability=round(sc["p_recht"] * sc["p_beweis"], 2),
            applicability_result="applicable",
            created_at=now - timedelta(days=365 - idx * 3),
            updated_at=now - timedelta(days=30),
        )
        all_cases.append(c)

        # Create events
        event_names = sc.get("events", ["FILED"])
        for ev_idx, ev_name in enumerate(event_names):
            etype = EVENT_TYPE_MAP.get(ev_name)
            if etype:
                all_events.append(CaseEvent(
                    id=uuid.uuid4(),
                    case_id=case_id,
                    event_type=etype,
                    payload={"source": "seed_scenario", "index": idx},
                    created_at=now - timedelta(days=350 - idx * 3 - ev_idx * 10),
                ))

        # Pipeline v3 data
        pv3 = _compute_pipeline_v3(sc, amount)
        all_pipeline.append({
            "case_id": case_id,
            "pipeline_v3": pv3,
            "outcome": is_success,
            "scenario_idx": idx,
        })

    return all_cases, all_events, all_pipeline


# ---------------------------------------------------------------------------
# 1) GET /api/statistics/overview
# ---------------------------------------------------------------------------

@router.get("/overview", response_model=OverviewResponse)
async def statistics_overview(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return overview statistics across all cases.

    Includes:
    - Totals and success rate
    - Bayesian posteriors aggregated from ALL completed-case events
    - ALL completed/rejected cases with outcome details and pipeline scores
    - Pipeline v3 aggregates and Bayes learning progression
    """
    # Total cases (all statuses)
    total_result = await db.execute(select(func.count(Case.id)))
    total_cases: int = total_result.scalar() or 0

    # Completed cases (COMPLETED or REJECTED)
    completed_result = await db.execute(
        select(Case).where(
            Case.status.in_([CaseStatus.COMPLETED, CaseStatus.REJECTED])
        )
    )
    completed_cases_list: list[Case] = list(completed_result.scalars().all())
    completed_count = len(completed_cases_list)

    # Load events for each completed case and determine success
    case_events_map: dict[UUID, list[CaseEvent]] = {}
    case_success_map: dict[UUID, bool] = {}

    if completed_cases_list:
        completed_ids = [c.id for c in completed_cases_list]
        events_result = await db.execute(
            select(CaseEvent).where(CaseEvent.case_id.in_(completed_ids))
        )
        all_completed_events = list(events_result.scalars().all())

        for ev in all_completed_events:
            case_events_map.setdefault(ev.case_id, []).append(ev)

        for c in completed_cases_list:
            evts = case_events_map.get(c.id, [])
            case_success_map[c.id] = _is_successful(evts)

    # Success rate
    successful_count = sum(1 for v in case_success_map.values() if v)
    success_rate = (
        round(successful_count / completed_count, 4)
        if completed_count > 0
        else 0.0
    )

    # Average recovery
    successful_amounts: list[float] = []
    for c in completed_cases_list:
        if case_success_map.get(c.id) and c.claim_amount and c.claim_amount > 0:
            successful_amounts.append(c.claim_amount)

    avg_recovery: Optional[float] = (
        round(sum(successful_amounts) / len(successful_amounts), 2)
        if successful_amounts
        else None
    )

    # Bayesian posteriors
    flat_events: list[CaseEvent] = []
    for evts in case_events_map.values():
        flat_events.extend(evts)

    posteriors: list[PosteriorItem] = []
    learning_insights: list[LearningInsight] = []

    for rate_name in ["merit", "default_settle", "collect"]:
        prior_alpha, prior_beta = DISPLAY_DEFAULT_PRIORS.get(rate_name, (2.0, 2.0))
        mapping = DISPLAY_RATE_EVENT_MAP.get(rate_name, {})
        success_types = mapping.get("success", set())
        failure_types = mapping.get("failure", set())
        successes = sum(1 for e in flat_events if e.event_type in success_types)
        failures = sum(1 for e in flat_events if e.event_type in failure_types)
        trials = successes + failures

        post = bayes_update(prior_alpha, prior_beta, successes, trials)

        posteriors.append(PosteriorItem(
            name=rate_name,
            label=DISPLAY_RATE_LABELS.get(rate_name, rate_name),
            prior_alpha=prior_alpha,
            prior_beta=prior_beta,
            successes=successes,
            trials=trials,
            post_alpha=post.alpha_post,
            post_beta=post.beta_post,
            mean=round(post.mean, 4),
            ci_low=post.ci_low,
            ci_high=post.ci_high,
        ))

        prior_mean = round(prior_alpha / (prior_alpha + prior_beta), 4) if (prior_alpha + prior_beta) > 0 else 0.5
        interpretation = _build_insight_text(rate_name, prior_mean, round(post.mean, 4), successes, failures)
        learning_insights.append(LearningInsight(
            rate_name=rate_name,
            label=DISPLAY_RATE_LABELS.get(rate_name, rate_name),
            prior_mean=prior_mean,
            posterior_mean=round(post.mean, 4),
            successes=successes,
            failures=failures,
            interpretation=interpretation,
        ))

    # Pre-fetch CaseProcessScore for ALL completed cases
    all_completed_ids = [c.id for c in completed_cases_list]
    score_map: dict[UUID, Optional[CaseProcessScore]] = {}
    all_pipeline_data: list[dict] = []

    if all_completed_ids:
        for cid in all_completed_ids:
            score_result = await db.execute(
                select(CaseProcessScore)
                .where(CaseProcessScore.case_id == cid)
                .order_by(CaseProcessScore.created_at.desc())
                .limit(1)
            )
            sc = score_result.scalar_one_or_none()
            score_map[cid] = sc
            if sc and sc.posteriors_json and isinstance(sc.posteriors_json, dict):
                pv3 = sc.posteriors_json.get("pipeline_v3")
                if pv3:
                    pv3_copy = dict(pv3)
                    pv3_copy["_outcome"] = case_success_map.get(cid, False)
                    all_pipeline_data.append(pv3_copy)

    # Build completed cases detail — ALL cases, sorted by creation date
    sorted_completed = sorted(completed_cases_list,
                              key=lambda c: c.created_at or datetime.min,
                              reverse=True)

    # Detect seed/test cases
    seed_marker = "[TEST]"

    completed_cases_detail: list[CompletedCaseDetail] = []
    for c in sorted_completed:
        outcome_success = case_success_map.get(c.id, False)
        claim_amt = c.claim_amount or 0.0
        net_ev = _compute_net_ev(claim_amt, outcome_success) if claim_amt > 0 else None
        evts = case_events_map.get(c.id, [])
        outcome_str = _outcome_from_events(evts)

        # Extract pipeline v3 scores
        pipeline_scores = None
        sc = score_map.get(c.id)
        if sc and sc.posteriors_json and isinstance(sc.posteriors_json, dict):
            pv3 = sc.posteriors_json.get("pipeline_v3")
            if pv3:
                pipeline_scores = PipelineScores(
                    p_recht=pv3.get("p_recht", 0.0),
                    p_entstanden=pv3.get("p_entstanden", 0.0),
                    p_nicht_untergegangen=pv3.get("p_nicht_untergegangen", 1.0),
                    p_durchsetzbar=pv3.get("p_durchsetzbar", 1.0),
                    p_beweis=pv3.get("p_beweis", 0.0),
                    p_obsiegen=pv3.get("p_obsiegen", 0.0),
                    p_eintreibung=pv3.get("p_eintreibung"),
                    p_gesamt=pv3.get("p_gesamt"),
                    ev_betreiber=pv3.get("ev_betreiber"),
                    take_case=pv3.get("take_case"),
                    claim_type=pv3.get("claim_type", "invoice"),
                    court_country=pv3.get("court_country", "DE"),
                    element_scores=pv3.get("element_scores", {}),
                )

        is_seed = sc.model_version == "v3-seed" if sc and sc.model_version else False
        is_test = (c.title or "").startswith(seed_marker)

        completed_cases_detail.append(CompletedCaseDetail(
            id=c.id,
            title=c.title or "",
            claim_amount=c.claim_amount,
            claim_currency=c.claim_currency,
            outcome_success=outcome_success,
            outcome=outcome_str,
            p_cash_success=sc.p_cash_success if sc else None,
            net_ev=net_ev,
            pipeline=pipeline_scores,
            description=c.claim_description or "",
            evidence_desc=c.claim_evidence or "",
            assessment=c.assessment_summary or "",
            claimant_name=c.claimant_name or "",
            claimant_country=c.claimant_country or "",
            defendant_name=c.defendant_name or "",
            defendant_country=c.defendant_country or "",
            court_country=c.court_country or "",
            is_cross_border=c.is_cross_border or False,
            is_seed=is_seed,
            is_test=is_test,
        ))

    # Pipeline v3 aggregates
    pipeline_aggregates = None
    if all_pipeline_data:
        n = len(all_pipeline_data)
        sum_recht = sum(d.get("p_recht", 0) for d in all_pipeline_data)
        sum_beweis = sum(d.get("p_beweis", 0) for d in all_pipeline_data)
        sum_obsiegen = sum(d.get("p_obsiegen", 0) for d in all_pipeline_data)
        eintreib_vals = [d["p_eintreibung"] for d in all_pipeline_data if d.get("p_eintreibung") is not None]
        gesamt_vals = [d["p_gesamt"] for d in all_pipeline_data if d.get("p_gesamt") is not None]
        ev_vals = [d.get("ev_betreiber", 0) for d in all_pipeline_data if d.get("ev_betreiber") is not None]
        take_vals = [d.get("take_case", False) for d in all_pipeline_data]

        pipeline_aggregates = PipelineAggregates(
            avg_p_recht=round(sum_recht / n, 4) if n else 0,
            avg_p_beweis=round(sum_beweis / n, 4) if n else 0,
            avg_p_obsiegen=round(sum_obsiegen / n, 4) if n else 0,
            avg_p_eintreibung=round(sum(eintreib_vals) / len(eintreib_vals), 4) if eintreib_vals else None,
            avg_p_gesamt=round(sum(gesamt_vals) / len(gesamt_vals), 4) if gesamt_vals else None,
            avg_ev=round(sum(ev_vals) / len(ev_vals), 2) if ev_vals else 0,
            take_case_rate=round(sum(1 for t in take_vals if t) / len(take_vals), 4) if take_vals else 0,
            total_evaluated=n,
        )

    # Bayes learning progression — simulate updates across cases
    bayes_steps: list[BayesLearningStep] = []
    alpha_cb, beta_cb = 2.0, 2.0
    alpha_pf, beta_pf = 2.0, 2.0
    step_num = 0
    for pv3 in all_pipeline_data:
        outcome = pv3.get("_outcome", False)
        conf_weight = 0.175
        if outcome:
            alpha_cb += conf_weight
            alpha_pf += conf_weight
        else:
            beta_cb += conf_weight
            beta_pf += conf_weight
        step_num += 1
        if step_num <= 2 or step_num % 5 == 0 or step_num == len(all_pipeline_data):
            bayes_steps.append(BayesLearningStep(
                step=step_num,
                element="contract_basis",
                alpha=round(alpha_cb, 3),
                beta=round(beta_cb, 3),
                mean=round(alpha_cb / (alpha_cb + beta_cb), 4),
                context_key="all",
                case_outcome="success" if outcome else "failure",
            ))
            bayes_steps.append(BayesLearningStep(
                step=step_num,
                element="performance",
                alpha=round(alpha_pf, 3),
                beta=round(beta_pf, 3),
                mean=round(alpha_pf / (alpha_pf + beta_pf), 4),
                context_key="all",
                case_outcome="success" if outcome else "failure",
            ))

    return OverviewResponse(
        total_cases=total_cases,
        completed_cases=completed_count,
        success_rate=success_rate,
        avg_recovery=avg_recovery,
        posteriors=posteriors,
        completed_cases_detail=completed_cases_detail,
        learning_insights=learning_insights,
        pipeline_aggregates=pipeline_aggregates,
        bayes_learning_progression=bayes_steps,
    )


# ---------------------------------------------------------------------------
# 2) POST /api/statistics/seed  (admin only)
# ---------------------------------------------------------------------------

@router.post("/seed", response_model=SeedResponse, status_code=status.HTTP_201_CREATED)
async def seed_demo_data(
    admin: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Seed 30 fictional cases from SEED_SCENARIOS.

    Always recreates: deletes old seed data first.
    """
    try:
        # Build seed data from the 100 scenarios
        seed_cases, seed_events, seed_pipeline = _build_seed_from_scenarios(admin.id)
        seed_ids = [c.id for c in seed_cases]

        # Delete old seed cases (model_version = v3-seed)
        old_seed_scores = await db.execute(
            select(CaseProcessScore.case_id).where(
                CaseProcessScore.model_version == "v3-seed"
            )
        )
        old_seed_case_ids = list(old_seed_scores.scalars().all())

        # Also find [TEST] cases
        old_test_result = await db.execute(
            select(Case.id).where(Case.title.like("[TEST]%"))
        )
        old_test_ids = list(old_test_result.scalars().all())

        # Also find [HIST] cases from old format
        old_hist_result = await db.execute(
            select(Case.id).where(Case.title.like("[HIST]%"))
        )
        old_hist_ids = list(old_hist_result.scalars().all())

        all_old_ids = list(set(old_seed_case_ids + old_test_ids + old_hist_ids))

        if all_old_ids:
            for i in range(0, len(all_old_ids), 50):
                batch = all_old_ids[i:i + 50]
                await db.execute(delete(CaseEvent).where(CaseEvent.case_id.in_(batch)))
                await db.execute(delete(CaseProcessScore).where(CaseProcessScore.case_id.in_(batch)))
                await db.execute(delete(CaseLLMTrace).where(CaseLLMTrace.case_id.in_(batch)))
                await db.execute(delete(ChatMessage).where(ChatMessage.case_id.in_(batch)))
                await db.execute(delete(Document).where(Document.case_id.in_(batch)))
                await db.execute(delete(Case).where(Case.id.in_(batch)))

        await db.flush()

        # Create 100 fictional cases
        for c in seed_cases:
            db.add(c)
        for e in seed_events:
            db.add(e)

        # Create CaseProcessScore for each case with pipeline v3 data
        for ps in seed_pipeline:
            pv3 = ps["pipeline_v3"]
            p_obsiegen = pv3.get("p_obsiegen", 0.0)
            score = CaseProcessScore(
                case_id=ps["case_id"],
                evidence_score=50.0,
                evidence_breakdown={"source": "seed_scenario"},
                ability_score=50.0,
                ability_components={"source": "seed_scenario"},
                willingness_score=50.0,
                willingness_components={"source": "seed_scenario"},
                p_served=pv3.get("p_recht", 0.5),
                p_default=pv3.get("p_beweis", 0.5),
                p_win_contested=p_obsiegen,
                p_settle=0.0,
                p_collect=pv3.get("p_eintreibung") or 0.0,
                p_cash_success=pv3.get("p_gesamt") or p_obsiegen,
                priors_json={"source": "seed_scenario"},
                posteriors_json={"pipeline_v3": pv3},
                observations_json={"source": "seed_scenario"},
                drivers_json=[],
                model_version="v3-seed",
            )
            db.add(score)

        await db.commit()

        return SeedResponse(
            fictional_cases_created=len(seed_cases),
            historical_aggregate_events_created=len(seed_events),
            message=f"{len(seed_cases)} fiktive Fälle mit {len(seed_events)} Events erstellt.",
        )

    except Exception:
        await db.rollback()
        logger.exception("Error seeding demo data")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Erstellen der Testdaten.",
        )


# ---------------------------------------------------------------------------
# 3) POST /api/statistics/test-case  (admin only)
# ---------------------------------------------------------------------------

@router.post("/test-case", response_model=TestCaseResponse, status_code=status.HTTP_201_CREATED)
async def create_test_case(
    req: TestCaseRequest,
    admin: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Create a custom test case with user-defined probabilities.

    The new case is added to the statistics and the Bayes learning
    progression is updated accordingly.
    """
    try:
        now = datetime.utcnow()
        case_id = uuid.uuid4()
        is_cb = req.claimant_country != req.defendant_country
        outcome = req.outcome.lower()
        is_success = outcome in ("won", "settled")

        case_status = CaseStatus.COMPLETED
        if outcome == "withdrawn":
            case_status = CaseStatus.REJECTED

        c = Case(
            id=case_id,
            user_id=admin.id,
            title=f"[TEST] {req.title}",
            status=case_status,
            court_country=req.court_country,
            claimant_is_legal_person=True,
            claimant_name=req.claimant_name,
            claimant_country=req.claimant_country,
            defendant_is_legal_person=True,
            defendant_name=req.defendant_name,
            defendant_country=req.defendant_country,
            is_cross_border=is_cb,
            claim_amount=req.claim_amount,
            claim_currency="EUR",
            claim_description=req.description,
            claim_evidence=req.evidence_desc,
            assessment_summary=f"Benutzerdefinierter Testfall: p_recht={req.p_recht}, p_beweis={req.p_beweis}",
            success_probability=round(req.p_recht * req.p_beweis, 2),
            applicability_result="applicable",
            created_at=now,
            updated_at=now,
        )
        db.add(c)

        # Create events based on outcome
        event_sequence = []
        if outcome == "won":
            event_sequence = [
                CaseEventType.FILED, CaseEventType.SERVICE_OK,
                CaseEventType.DEFAULT, CaseEventType.JUDGMENT_WIN,
                CaseEventType.PAYMENT_RECEIVED,
            ]
        elif outcome == "lost":
            event_sequence = [
                CaseEventType.FILED, CaseEventType.SERVICE_OK,
                CaseEventType.DEFENDANT_RESPONDED, CaseEventType.JUDGMENT_LOSS,
            ]
        elif outcome == "settled":
            event_sequence = [
                CaseEventType.FILED, CaseEventType.SERVICE_OK,
                CaseEventType.DEFENDANT_RESPONDED, CaseEventType.SETTLED,
                CaseEventType.PAYMENT_RECEIVED,
            ]
        elif outcome == "withdrawn":
            event_sequence = [CaseEventType.FILED]

        for ev_idx, etype in enumerate(event_sequence):
            db.add(CaseEvent(
                id=uuid.uuid4(),
                case_id=case_id,
                event_type=etype,
                payload={"source": "test_case"},
                created_at=now - timedelta(hours=len(event_sequence) - ev_idx),
            ))

        # Compute pipeline v3
        scenario = {
            "p_recht": req.p_recht,
            "p_beweis": req.p_beweis,
            "p_eintreibung": req.p_eintreibung,
            "claim_type": req.claim_type,
            "court_country": req.court_country,
        }
        pv3 = _compute_pipeline_v3(scenario, req.claim_amount)

        score = CaseProcessScore(
            case_id=case_id,
            evidence_score=50.0,
            evidence_breakdown={"source": "test_case"},
            ability_score=50.0,
            ability_components={"source": "test_case"},
            willingness_score=50.0,
            willingness_components={"source": "test_case"},
            p_served=req.p_recht,
            p_default=req.p_beweis,
            p_win_contested=round(req.p_recht * req.p_beweis, 4),
            p_settle=0.0,
            p_collect=req.p_eintreibung or 0.0,
            p_cash_success=pv3.get("p_gesamt") or pv3.get("p_obsiegen", 0.0),
            priors_json={"source": "test_case"},
            posteriors_json={"pipeline_v3": pv3},
            observations_json={"source": "test_case"},
            drivers_json=[],
            model_version="v3-seed",
        )
        db.add(score)

        await db.commit()

        pipeline_resp = PipelineScores(
            p_recht=pv3.get("p_recht", 0.0),
            p_beweis=pv3.get("p_beweis", 0.0),
            p_obsiegen=pv3.get("p_obsiegen", 0.0),
            p_eintreibung=pv3.get("p_eintreibung"),
            p_gesamt=pv3.get("p_gesamt"),
            ev_betreiber=pv3.get("ev_betreiber"),
            take_case=pv3.get("take_case"),
            claim_type=req.claim_type,
            court_country=req.court_country,
        )

        return TestCaseResponse(
            case_id=case_id,
            message=f"Testfall '{req.title}' erstellt. Statistik wird aktualisiert.",
            pipeline=pipeline_resp,
        )

    except Exception:
        await db.rollback()
        logger.exception("Error creating test case")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Erstellen des Testfalls.",
        )


# ---------------------------------------------------------------------------
# 4) POST /api/statistics/update-priors  (admin only)
# ---------------------------------------------------------------------------

@router.post("/update-priors", response_model=UpdatePriorsResponse)
async def update_priors_from_outcomes(
    admin: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Recalculate Beta priors from ALL completed-case event outcomes."""
    try:
        all_events_result = await db.execute(select(CaseEvent))
        all_events = list(all_events_result.scalars().all())

        rates_updated: list[str] = []
        priors_items: list[UpdatedPriorItem] = []

        # Update internal 4 rates in PriorsConfig
        for rate_name in ["served", "default", "settle", "collect"]:
            mapping = RATE_EVENT_MAP.get(rate_name, {})
            success_types = mapping.get("success", set())
            failure_types = mapping.get("failure", set())

            successes = sum(1 for e in all_events if e.event_type in success_types)
            failures = sum(1 for e in all_events if e.event_type in failure_types)

            base_alpha, base_beta = DEFAULT_PRIORS.get(rate_name, (2.0, 2.0))

            new_alpha = base_alpha + successes
            new_beta = base_beta + failures

            existing_result = await db.execute(
                select(PriorsConfig).where(
                    PriorsConfig.rate_name == rate_name,
                    PriorsConfig.claim_subtype == "general",
                    PriorsConfig.country == "*",
                )
            )
            existing = existing_result.scalar_one_or_none()

            if existing:
                existing.alpha = new_alpha
                existing.beta = new_beta
            else:
                prior = PriorsConfig(
                    rate_name=rate_name,
                    claim_subtype="general",
                    country="*",
                    alpha=new_alpha,
                    beta=new_beta,
                )
                db.add(prior)

        # Build response with 3 display rates
        display_rate_labels = {
            "merit": "Schlüssigkeitsprüfung",
            "default_settle": "Versäumnis-/Vergleichsrate",
            "collect": "Inkassorate",
        }
        for display_name in ["merit", "default_settle", "collect"]:
            mapping = DISPLAY_RATE_EVENT_MAP.get(display_name, {})
            success_types = mapping.get("success", set())
            failure_types = mapping.get("failure", set())

            successes = sum(1 for e in all_events if e.event_type in success_types)
            failures = sum(1 for e in all_events if e.event_type in failure_types)
            trials = successes + failures

            base_alpha, base_beta = DISPLAY_DEFAULT_PRIORS.get(display_name, (2.0, 2.0))

            new_alpha = base_alpha + successes
            new_beta = base_beta + failures

            posterior_mean = (
                round(new_alpha / (new_alpha + new_beta), 4)
                if (new_alpha + new_beta) > 0
                else 0.5
            )

            rates_updated.append(display_name)
            priors_items.append(UpdatedPriorItem(
                rate_name=display_rate_labels.get(display_name, display_name),
                old_alpha=round(base_alpha, 2),
                old_beta=round(base_beta, 2),
                new_alpha=round(new_alpha, 2),
                new_beta=round(new_beta, 2),
                successes=successes,
                failures=failures,
                trials=trials,
                posterior_mean=posterior_mean,
            ))

        await db.commit()

        return UpdatePriorsResponse(
            rates_updated=rates_updated,
            priors=priors_items,
        )

    except Exception:
        await db.rollback()
        logger.exception("Error updating priors")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Aktualisieren der Priors.",
        )


# ---------------------------------------------------------------------------
# Expected-Value sub-router  (kept at /api/cases/{case_id}/expected-value)
# ---------------------------------------------------------------------------

COURT_FEE_TABLE: dict[str, dict] = {
    "DE": {"base": 32.0, "pct": 0.03, "min": 32.0, "max": 100.0},
    "AT": {"base": 28.0, "pct": 0.02, "min": 28.0, "max": 93.0},
    "FR": {"base": 0.0,  "pct": 0.0,  "min": 0.0,  "max": 0.0},
    "IT": {"base": 43.0, "pct": 0.0,  "min": 43.0, "max": 43.0},
    "NL": {"base": 86.0, "pct": 0.0,  "min": 86.0, "max": 86.0},
    "ES": {"base": 0.0,  "pct": 0.0,  "min": 0.0,  "max": 0.0},
    "BE": {"base": 20.0, "pct": 0.02, "min": 20.0, "max": 80.0},
    "PT": {"base": 51.0, "pct": 0.0,  "min": 51.0, "max": 102.0},
    "PL": {"base": 30.0, "pct": 0.01, "min": 30.0, "max": 50.0},
    "*":  {"base": 50.0, "pct": 0.02, "min": 30.0, "max": 100.0},
}


def _calculate_court_fees(claim_amount: float, court_country: str | None) -> float:
    """Calculate approximate court fees based on the court's member state."""
    country = (court_country or "*").upper()
    schedule = COURT_FEE_TABLE.get(country, COURT_FEE_TABLE["*"])
    fee = schedule["base"] + claim_amount * schedule["pct"]
    return max(schedule["min"], min(schedule["max"], fee))


class ExpectedValueResult(BaseModel):
    case_id: UUID
    claim_amount: float
    claim_currency: str
    p_win: float
    p_loss: float
    expected_commission: float
    court_fees: float
    attorney_costs: float
    service_fees: float
    opponent_costs: float
    cost_compensation: float
    net_expected_value: float
    expected_loss_costs: float
    recommendation: str
    recommendation_reason: str
    min_probability_threshold: float
    breakdown: dict


ev_router = APIRouter(prefix="/api/cases", tags=["cases", "statistics"])


@ev_router.get("/{case_id}/expected-value", response_model=ExpectedValueResult)
async def get_expected_value(
    case_id: UUID,
    admin: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Calculate expected value for a case based on its latest process score."""
    case_result = await db.execute(select(Case).where(Case.id == case_id))
    case = case_result.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="Fall nicht gefunden.")

    claim_amount = case.claim_amount or 0.0
    claim_currency = case.claim_currency or "EUR"

    if claim_amount <= 0:
        raise HTTPException(
            status_code=400,
            detail="Keine Forderungshöhe angegeben. Bitte zuerst claim_amount setzen.",
        )

    score_result = await db.execute(
        select(CaseProcessScore)
        .where(CaseProcessScore.case_id == case_id)
        .order_by(CaseProcessScore.created_at.desc())
        .limit(1)
    )
    score = score_result.scalar_one_or_none()

    if not score:
        score = await estimate(case_id, db)
        await db.commit()

    p_win = score.p_cash_success
    p_loss = 1.0 - p_win

    court_country = case.court_country or case.court_member_state or "*"
    court_fees = _calculate_court_fees(claim_amount, court_country)

    is_cross_border = case.is_cross_border or (
        case.claimant_country and case.defendant_country
        and case.claimant_country != case.defendant_country
    )
    service_fees = 80.0 if is_cross_border else 50.0
    attorney_costs = _estimate_attorney_costs(claim_amount)
    opponent_costs = _estimate_opponent_costs(claim_amount)

    expected_commission = p_win * COMMISSION_RATE * claim_amount
    cost_compensation = court_fees + attorney_costs
    expected_loss_costs = p_loss * (court_fees + attorney_costs + opponent_costs)
    net_ev = expected_commission - service_fees - expected_loss_costs

    MIN_PROBABILITY_THRESHOLD = 0.80

    if p_win >= MIN_PROBABILITY_THRESHOLD and net_ev > 0:
        recommendation = "empfohlen"
        reason = (
            f"Positiver erwarteter Nettoertrag von {net_ev:.2f} {claim_currency}. "
            f"Gewinnwahrscheinlichkeit {p_win:.0%} liegt über der Schwelle von 80%."
        )
    elif p_win >= 0.60 and net_ev > 0:
        recommendation = "riskant"
        reason = (
            f"Erwarteter Nettoertrag positiv ({net_ev:.2f} {claim_currency}), "
            f"aber Gewinnwahrscheinlichkeit ({p_win:.0%}) liegt unter der 80%-Schwelle."
        )
    elif net_ev > 0:
        recommendation = "nicht empfohlen"
        reason = (
            f"Gewinnwahrscheinlichkeit ({p_win:.0%}) liegt deutlich unter 80%. "
            f"Trotz positivem EV ({net_ev:.2f} {claim_currency}) zu riskant."
        )
    else:
        recommendation = "nicht empfohlen"
        reason = (
            f"Negativer erwarteter Nettoertrag ({net_ev:.2f} {claim_currency}). "
            f"Kosten übersteigen den erwarteten Ertrag bei {p_win:.0%} Gewinnwahrscheinlichkeit."
        )

    return ExpectedValueResult(
        case_id=case_id,
        claim_amount=claim_amount,
        claim_currency=claim_currency,
        p_win=round(p_win, 4),
        p_loss=round(p_loss, 4),
        expected_commission=round(expected_commission, 2),
        court_fees=round(court_fees, 2),
        attorney_costs=round(attorney_costs, 2),
        service_fees=round(service_fees, 2),
        opponent_costs=round(opponent_costs, 2),
        cost_compensation=round(cost_compensation, 2),
        net_expected_value=round(net_ev, 2),
        expected_loss_costs=round(expected_loss_costs, 2),
        recommendation=recommendation,
        recommendation_reason=reason,
        min_probability_threshold=MIN_PROBABILITY_THRESHOLD,
        breakdown={
            "formula": (
                "net_ev = p_win * 0.30 * claim_amount"
                " - service_fees"
                " - p_loss * (court_fees + attorney_costs + opponent_costs)"
            ),
            "p_win": round(p_win, 4),
            "p_loss": round(p_loss, 4),
            "commission_calc": f"{p_win:.4f} * 0.30 * {claim_amount} = {expected_commission:.2f}",
            "cost_compensation_on_win": f"{court_fees:.2f} + {attorney_costs:.2f} = {cost_compensation:.2f}",
            "expected_loss_costs_calc": (
                f"{p_loss:.4f} * ({court_fees:.2f} + {attorney_costs:.2f} + {opponent_costs:.2f})"
                f" = {expected_loss_costs:.2f}"
            ),
            "court_fees_country": court_country,
            "service_type": "cross_border" if is_cross_border else "domestic",
            "min_probability_threshold": "80%",
        },
    )
