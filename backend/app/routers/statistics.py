"""Statistics & Bayesian Learning API — admin-only endpoints for
completed-case analytics, seed data, prior updates, and expected-value
calculations.

Endpoints:
  GET  /api/statistics/overview       — aggregate stats + posteriors + completed case detail
  POST /api/statistics/seed           — seed 5 fictional + 100 historical cases (admin)
  POST /api/statistics/update-priors  — recalculate PriorsConfig from event outcomes (admin)
  GET  /api/cases/{case_id}/expected-value — per-case expected-value breakdown (admin)
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta
from typing import Any, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import get_current_user
from ..database import get_db
from ..models import (
    Case,
    CaseEvent,
    CaseEventType,
    CaseProcessScore,
    CaseStatus,
    PriorsConfig,
    User,
)
from ..services.scoring import estimate

# ---------------------------------------------------------------------------
# Bayes utilities — used only for admin statistics display, not for scoring
# ---------------------------------------------------------------------------

import math as _math
from dataclasses import dataclass as _dataclass

DEFAULT_PRIORS: dict[str, tuple[float, float]] = {
    "valid":    (6.0, 2.0),
    "provable": (4.0, 6.0),
    "payment":  (5.0, 5.0),
}

RATE_EVENT_MAP: dict[str, dict] = {
    "valid": {
        "success": {CaseEventType.JUDGMENT_WIN, CaseEventType.DEFAULT, CaseEventType.SETTLED},
        "failure": {CaseEventType.JUDGMENT_LOSS},
    },
    "provable": {
        "success": {CaseEventType.JUDGMENT_WIN},
        "failure": {CaseEventType.JUDGMENT_LOSS},
    },
    "payment": {
        "success": {CaseEventType.PAYMENT_RECEIVED},
        "failure": {CaseEventType.COLLECTION_FAILED},
    },
}


@_dataclass
class _BayesPosterior:
    alpha_prior: float; beta_prior: float; successes: int; trials: int
    alpha_post: float; beta_post: float; mean: float
    ci_low: float = 0.0; ci_high: float = 1.0


def _beta_quantile(a: float, b: float, p: float) -> float:
    if a <= 0 or b <= 0:
        return 0.5
    mu = a / (a + b)
    var = (a * b) / ((a + b) ** 2 * (a + b + 1))
    std = _math.sqrt(var) if var > 0 else 0
    z = -1.645 if p < 0.5 else 1.645
    return max(0.0, min(1.0, mu + z * std))


def bayes_update(alpha: float, beta_param: float, successes: int, trials: int) -> _BayesPosterior:
    f = trials - successes
    a, b = alpha + successes, beta_param + f
    mean = a / (a + b) if (a + b) > 0 else 0.5
    return _BayesPosterior(
        alpha_prior=alpha, beta_prior=beta_param, successes=successes, trials=trials,
        alpha_post=a, beta_post=b, mean=mean,
        ci_low=round(_beta_quantile(a, b, 0.05), 4),
        ci_high=round(_beta_quantile(a, b, 0.95), 4),
    )


def count_events(events: list, rate_name: str) -> tuple[int, int]:
    mapping = RATE_EVENT_MAP.get(rate_name, {})
    s = sum(1 for e in events if e.event_type in mapping.get("success", set()))
    f = sum(1 for e in events if e.event_type in mapping.get("failure", set()))
    return s, s + f

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/statistics", tags=["statistics"])


# ---------------------------------------------------------------------------
# Pydantic response schemas (local to this module)
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


class CompletedCaseDetail(BaseModel):
    id: UUID
    title: str
    claim_amount: Optional[float] = None
    claim_currency: Optional[str] = None
    outcome_success: bool
    p_cash_success: Optional[float] = None
    net_ev: Optional[float] = None


class OverviewResponse(BaseModel):
    total_cases: int
    completed_cases: int
    success_rate: float
    avg_recovery: Optional[float] = None
    posteriors: List[PosteriorItem]
    completed_cases_detail: List[CompletedCaseDetail]


class SeedResponse(BaseModel):
    fictional_cases_created: int
    historical_aggregate_events_created: int
    message: str


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


RATE_LABELS: dict[str, str] = {
    "valid":    "Anspruchs-Gültigkeitsrate",
    "provable": "Beweisbarkeitsrate",
    "payment":  "Zahlungsrate",
}


def _estimate_court_fees(claim_amount: float) -> float:
    """Simplified ESCP court fee estimation.

    Uses a percentage-based formula with a minimum floor:
      fee = max(35, claim_amount * 0.035)
    This is a reasonable approximation across EU member states for ESCP claims.
    """
    return max(35.0, claim_amount * 0.035)


SERVICE_COSTS_FLAT = 75.0   # flat service cost estimate (EUR)
COMMISSION_RATE = 0.30      # 30% commission on collected amount


def _estimate_attorney_costs(claim_amount: float) -> float:
    """Estimate portal's attorney/legal operational costs.

    Simplified schedule based on claim amount:
      - Up to 500 EUR:  50 EUR flat
      - 500-2000 EUR:   50 + 5% of amount above 500
      - 2000-5000 EUR:  125 + 3% of amount above 2000
    """
    if claim_amount <= 500:
        return 50.0
    elif claim_amount <= 2000:
        return 50.0 + (claim_amount - 500) * 0.05
    else:
        return 125.0 + (claim_amount - 2000) * 0.03


def _estimate_opponent_costs(claim_amount: float) -> float:
    """Estimate opponent's costs that portal must pay on loss.

    In ESCP proceedings, the losing party typically pays the winner's
    reasonable costs.  Estimated as attorney costs + a small overhead.
    """
    return _estimate_attorney_costs(claim_amount) * 1.2


def _compute_net_ev(claim_amount: float, outcome_success: bool) -> float:
    """Compute net expected value for a *completed* case from the
    **project owner's** (portal's) perspective.

    On success:
      net = 30% commission + cost compensation (court fees + attorney costs) - own costs
    On failure:
      net = -(own costs + opponent costs)

    Own costs = court_fees + attorney_costs + service_costs
    """
    court_fees = _estimate_court_fees(claim_amount)
    attorney_costs = _estimate_attorney_costs(claim_amount)
    service_costs = SERVICE_COSTS_FLAT

    if outcome_success:
        commission = claim_amount * COMMISSION_RATE
        cost_compensation = court_fees + attorney_costs  # recovered from opponent
        own_costs = court_fees + attorney_costs + service_costs
        return round(commission + cost_compensation - own_costs, 2)
    else:
        own_costs = court_fees + attorney_costs + service_costs
        opponent_costs = _estimate_opponent_costs(claim_amount)
        return round(-(own_costs + opponent_costs), 2)


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
    - Last 20 completed cases with outcome details
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

    # ── Load events for each completed case and determine success ──
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

    # ── Success rate ──
    successful_count = sum(1 for v in case_success_map.values() if v)
    success_rate = (
        round(successful_count / completed_count, 4)
        if completed_count > 0
        else 0.0
    )

    # ── Average recovery (mean claim_amount of successful completed cases) ──
    successful_amounts: list[float] = []
    for c in completed_cases_list:
        if case_success_map.get(c.id) and c.claim_amount and c.claim_amount > 0:
            successful_amounts.append(c.claim_amount)

    avg_recovery: Optional[float] = (
        round(sum(successful_amounts) / len(successful_amounts), 2)
        if successful_amounts
        else None
    )

    # ── Bayesian posteriors aggregated from ALL completed-case events ──
    flat_events: list[CaseEvent] = []
    for evts in case_events_map.values():
        flat_events.extend(evts)

    posteriors: list[PosteriorItem] = []
    for rate_name in ["valid", "provable", "payment"]:
        prior_alpha, prior_beta = DEFAULT_PRIORS.get(rate_name, (2.0, 2.0))
        successes, trials = count_events(flat_events, rate_name)
        post = bayes_update(prior_alpha, prior_beta, successes, trials)

        posteriors.append(PosteriorItem(
            name=rate_name,
            label=RATE_LABELS.get(rate_name, rate_name),
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

    # ── All completed cases with detail ──
    # Sort by created_at descending (no arbitrary limit so all cases are shown)
    sorted_completed = sorted(
        completed_cases_list,
        key=lambda c: c.created_at or datetime.min,
        reverse=True,
    )

    # Pre-fetch latest p_cash_success for these cases in one query
    detail_ids = [c.id for c in sorted_completed]
    p_cash_map: dict[UUID, Optional[float]] = {}
    if detail_ids:
        # Use a subquery to get the latest score per case
        for cid in detail_ids:
            score_result = await db.execute(
                select(CaseProcessScore.p_cash_success)
                .where(CaseProcessScore.case_id == cid)
                .order_by(CaseProcessScore.created_at.desc())
                .limit(1)
            )
            p_cash_map[cid] = score_result.scalar_one_or_none()

    completed_cases_detail: list[CompletedCaseDetail] = []
    for c in sorted_completed:
        outcome_success = case_success_map.get(c.id, False)
        claim_amt = c.claim_amount or 0.0
        net_ev = _compute_net_ev(claim_amt, outcome_success) if claim_amt > 0 else None

        completed_cases_detail.append(CompletedCaseDetail(
            id=c.id,
            title=c.title,
            claim_amount=c.claim_amount,
            claim_currency=c.claim_currency,
            outcome_success=outcome_success,
            p_cash_success=p_cash_map.get(c.id),
            net_ev=net_ev,
        ))

    return OverviewResponse(
        total_cases=total_cases,
        completed_cases=completed_count,
        success_rate=success_rate,
        avg_recovery=avg_recovery,
        posteriors=posteriors,
        completed_cases_detail=completed_cases_detail,
    )


# ---------------------------------------------------------------------------
# 2) POST /api/statistics/seed  (admin only)
# ---------------------------------------------------------------------------

def _build_seed_cases(admin_user_id: UUID) -> list[dict]:
    """Build 5 detailed fictional completed cases for demo purposes.

    1. Strong case:  Invoice for goods, EUR 2500, defendant DE, successful
    2. Weak case:    Oral agreement for services, EUR 800, no evidence, unsuccessful
    3. Disputed case: Contract dispute, EUR 3000, defendant disputes quality, settled
    4. Insolvency case: Strong evidence, EUR 4500, defendant insolvent, unsuccessful
    5. Cross-border case: IT supplier, EUR 1200, defendant FR, successful via default
    """
    now = datetime.utcnow()
    cases: list[dict] = []

    # ── Case 1: Strong case — Invoice for goods, EUR 2500, defendant DE, successful ──
    c1_id = uuid.uuid4()
    cases.append({
        "case": Case(
            id=c1_id,
            user_id=admin_user_id,
            title="Müller GmbH vs. Fischer OHG — Warenlieferung Elektronikteile",
            status=CaseStatus.COMPLETED,
            court_name="Amtsgericht Stuttgart",
            court_address="Hauffstraße 5, 70190 Stuttgart",
            court_country="DE",
            claimant_is_legal_person=True,
            claimant_name="Müller Elektronik GmbH",
            claimant_address="Industriestraße 12, 70569 Stuttgart",
            claimant_city="Stuttgart",
            claimant_country="DE",
            claimant_email="info@mueller-elektronik.de",
            defendant_is_legal_person=True,
            defendant_name="Fischer Handels OHG",
            defendant_address="Königstraße 40, 70173 Stuttgart",
            defendant_city="Stuttgart",
            defendant_country="DE",
            defendant_email="office@fischer-handel.de",
            jurisdiction_basis="Art. 4 Abs. 1 EuGVVO",
            claimant_domicile_country="DE",
            defendant_domicile_country="DE",
            court_member_state="DE",
            is_cross_border=False,
            claim_amount=2500.0,
            claim_currency="EUR",
            claim_request_costs=True,
            claim_interest_rate=5.0,
            claim_interest_from_date="2025-04-01",
            claim_interest_type="statutory",
            claim_description=(
                "Lieferung von Elektronikbauteilen gemäß Kaufvertrag vom 01.02.2025. "
                "Ware am 15.02.2025 geliefert und angenommen. "
                "Rechnung Nr. 2025-0198 über EUR 2.500 war am 01.04.2025 fällig. "
                "Trotz Mahnung erfolgte keine Zahlung."
            ),
            claim_basis="Kaufvertrag, Auftragsbestätigung, Lieferschein",
            claim_evidence=(
                "Kaufvertrag, Auftragsbestätigung, Lieferschein mit Empfangsbestätigung, "
                "Rechnung Nr. 2025-0198, Mahnung mit Fristsetzung"
            ),
            applicability_result="applicable",
            success_probability=0.85,
            assessment_summary=(
                "Starke Beweislage: schriftlicher Vertrag, Liefernachweis, "
                "dokumentierte Mahnung. Hohe Erfolgswahrscheinlichkeit."
            ),
            created_at=now - timedelta(days=90),
            updated_at=now - timedelta(days=5),
        ),
        "events": [
            CaseEvent(id=uuid.uuid4(), case_id=c1_id,
                      event_type=CaseEventType.FILED,
                      payload={"court": "Amtsgericht Stuttgart", "date": "2025-05-01"},
                      created_at=now - timedelta(days=85)),
            CaseEvent(id=uuid.uuid4(), case_id=c1_id,
                      event_type=CaseEventType.SERVICE_OK,
                      payload={"method": "post", "date": "2025-05-15"},
                      created_at=now - timedelta(days=70)),
            CaseEvent(id=uuid.uuid4(), case_id=c1_id,
                      event_type=CaseEventType.DEFAULT,
                      payload={"reason": "no_response_within_30_days", "date": "2025-06-15"},
                      created_at=now - timedelta(days=40)),
            CaseEvent(id=uuid.uuid4(), case_id=c1_id,
                      event_type=CaseEventType.JUDGMENT_WIN,
                      payload={"amount_awarded": 2500.0, "date": "2025-06-20"},
                      created_at=now - timedelta(days=35)),
            CaseEvent(id=uuid.uuid4(), case_id=c1_id,
                      event_type=CaseEventType.PAYMENT_RECEIVED,
                      payload={"amount": 2500.0, "method": "bank_transfer", "date": "2025-07-10"},
                      created_at=now - timedelta(days=5)),
        ],
        "score_overrides": {
            "evidence_score": 90.0,
            "p_claim_valid": 0.87, "p_claim_provable": 0.82, "p_payment": 0.73,
            "p_cash_success": 0.52,
            "legal_validity_json": {"p_entstanden": 0.92, "p_not_untergegangen": 0.95, "p_durchsetzbar": 0.90, "applicable_law": "BGB §433", "p_claim_valid_llm": 0.79, "stat_valid": 0.75},
            "provability_json": {"evidence_score": 90.0, "p_evidence_sigmoid": 0.98, "stat_provable": 0.55, "p_claim_provable": 0.82},
            "payment_analysis_json": {"ability_score": 78, "insolvency_risk": "low", "p_willingness": 0.75, "p_payment": 0.73},
        },
    })

    # ── Case 2: Weak case — Oral agreement, EUR 800, no evidence, unsuccessful ──
    c2_id = uuid.uuid4()
    cases.append({
        "case": Case(
            id=c2_id,
            user_id=admin_user_id,
            title="Schneider vs. Braun — Mündlicher Dienstleistungsvertrag",
            status=CaseStatus.COMPLETED,
            court_name="Amtsgericht Berlin-Mitte",
            court_address="Littenstraße 12-17, 10179 Berlin",
            court_country="DE",
            claimant_is_legal_person=False,
            claimant_name="Hans Schneider",
            claimant_address="Berliner Str. 22, 10115 Berlin",
            claimant_city="Berlin",
            claimant_country="DE",
            claimant_email="h.schneider@email.de",
            defendant_is_legal_person=False,
            defendant_name="Karl Braun",
            defendant_address="Münchener Str. 5, 10789 Berlin",
            defendant_city="Berlin",
            defendant_country="DE",
            defendant_email="k.braun@email.de",
            jurisdiction_basis="Art. 4 Abs. 1 EuGVVO",
            claimant_domicile_country="DE",
            defendant_domicile_country="DE",
            court_member_state="DE",
            is_cross_border=False,
            claim_amount=800.0,
            claim_currency="EUR",
            claim_description=(
                "Mündlich vereinbarte Gartenarbeiten im März 2025. "
                "Kein schriftlicher Vertrag. Arbeiten wurden erbracht, "
                "jedoch keine Dokumentation der Leistung vorhanden."
            ),
            claim_basis="Mündliche Vereinbarung",
            claim_evidence="Keine schriftlichen Nachweise",
            applicability_result="applicable",
            success_probability=0.20,
            assessment_summary=(
                "Schwache Beweislage: nur mündliche Vereinbarung, "
                "keine Dokumentation. Geringe Erfolgsaussichten."
            ),
            created_at=now - timedelta(days=80),
            updated_at=now - timedelta(days=30),
        ),
        "events": [
            CaseEvent(id=uuid.uuid4(), case_id=c2_id,
                      event_type=CaseEventType.FILED,
                      payload={"court": "Amtsgericht Berlin-Mitte", "date": "2025-05-15"},
                      created_at=now - timedelta(days=75)),
            CaseEvent(id=uuid.uuid4(), case_id=c2_id,
                      event_type=CaseEventType.SERVICE_OK,
                      payload={"method": "post", "date": "2025-06-01"},
                      created_at=now - timedelta(days=60)),
            CaseEvent(id=uuid.uuid4(), case_id=c2_id,
                      event_type=CaseEventType.DEFENDANT_RESPONDED,
                      payload={"response_type": "contest", "date": "2025-06-20"},
                      created_at=now - timedelta(days=45)),
            CaseEvent(id=uuid.uuid4(), case_id=c2_id,
                      event_type=CaseEventType.JUDGMENT_LOSS,
                      payload={"reason": "insufficient_evidence", "date": "2025-07-15"},
                      created_at=now - timedelta(days=30)),
        ],
        "score_overrides": {
            "evidence_score": 15.0,
            "p_claim_valid": 0.55, "p_claim_provable": 0.18, "p_payment": 0.50,
            "p_cash_success": 0.05,
            "legal_validity_json": {"p_entstanden": 0.60, "p_not_untergegangen": 0.90, "p_durchsetzbar": 0.85, "applicable_law": "BGB §611", "p_claim_valid_llm": 0.46, "stat_valid": 0.75},
            "provability_json": {"evidence_score": 15.0, "p_evidence_sigmoid": 0.02, "stat_provable": 0.40, "p_claim_provable": 0.18},
            "payment_analysis_json": {"ability_score": 52, "insolvency_risk": "unknown", "p_willingness": 0.50, "p_payment": 0.50},
        },
    })

    # ── Case 3: Disputed case — Contract dispute, EUR 3000, settled ──
    c3_id = uuid.uuid4()
    cases.append({
        "case": Case(
            id=c3_id,
            user_id=admin_user_id,
            title="Weber GmbH vs. Rossi S.r.l. — Qualitätsstreit Textilien",
            status=CaseStatus.COMPLETED,
            court_name="Amtsgericht München",
            court_address="Pacellistraße 5, 80333 München",
            court_country="DE",
            claimant_is_legal_person=True,
            claimant_name="Weber Mode GmbH",
            claimant_address="Maximilianstraße 10, 80539 München",
            claimant_city="München",
            claimant_country="DE",
            claimant_email="recht@weber-mode.de",
            defendant_is_legal_person=True,
            defendant_name="Rossi Tessuti S.r.l.",
            defendant_address="Via Monte Napoleone 8, 20121 Milano",
            defendant_city="Milano",
            defendant_country="IT",
            defendant_email="legale@rossi-tessuti.it",
            jurisdiction_basis="Art. 7 Nr. 1 lit. b EuGVVO",
            jurisdiction_details="Defendant disputes quality of delivered textiles",
            claimant_domicile_country="DE",
            defendant_domicile_country="IT",
            court_member_state="DE",
            is_cross_border=True,
            claim_amount=3000.0,
            claim_currency="EUR",
            claim_request_costs=True,
            claim_interest_rate=5.0,
            claim_interest_from_date="2025-03-01",
            claim_description=(
                "Lieferung von Textilien gemäß Vertrag. "
                "Beklagter beanstandet die Qualität und verweigert Zahlung. "
                "Klägerin bestreitet Mängel."
            ),
            claim_basis="Kaufvertrag vom 10.01.2025",
            claim_evidence=(
                "Kaufvertrag, Lieferschein, Qualitätszertifikat, "
                "Reklamationsschreiben des Beklagten"
            ),
            applicability_result="applicable",
            success_probability=0.55,
            assessment_summary=(
                "Streitfall mit Qualitätsdispute. "
                "Vergleich erzielt: EUR 2.400 (80% der Forderung)."
            ),
            created_at=now - timedelta(days=100),
            updated_at=now - timedelta(days=15),
        ),
        "events": [
            CaseEvent(id=uuid.uuid4(), case_id=c3_id,
                      event_type=CaseEventType.FILED,
                      payload={"court": "Amtsgericht München", "date": "2025-04-10"},
                      created_at=now - timedelta(days=95)),
            CaseEvent(id=uuid.uuid4(), case_id=c3_id,
                      event_type=CaseEventType.SERVICE_OK,
                      payload={"method": "post_registered", "date": "2025-04-25"},
                      created_at=now - timedelta(days=80)),
            CaseEvent(id=uuid.uuid4(), case_id=c3_id,
                      event_type=CaseEventType.DEFENDANT_RESPONDED,
                      payload={"response_type": "contest", "defense": "quality_dispute", "date": "2025-05-15"},
                      created_at=now - timedelta(days=60)),
            CaseEvent(id=uuid.uuid4(), case_id=c3_id,
                      event_type=CaseEventType.SETTLED,
                      payload={"settlement_amount": 2400.0, "date": "2025-06-10",
                               "note": "Vergleich: EUR 2.400 in einer Summe"},
                      created_at=now - timedelta(days=35)),
            CaseEvent(id=uuid.uuid4(), case_id=c3_id,
                      event_type=CaseEventType.PAYMENT_RECEIVED,
                      payload={"amount": 2400.0, "date": "2025-07-01", "method": "bank_transfer"},
                      created_at=now - timedelta(days=15)),
        ],
        "score_overrides": {
            "evidence_score": 65.0,
            "p_claim_valid": 0.65, "p_claim_provable": 0.55, "p_payment": 0.98,
            "p_cash_success": 0.35,
            "legal_validity_json": {"p_entstanden": 0.65, "p_not_untergegangen": 0.92, "p_durchsetzbar": 0.90, "applicable_law": "BGB §634 (Werkmängel) / Rom-I-VO Art. 4", "p_claim_valid_llm": 0.54, "stat_valid": 0.75},
            "provability_json": {"evidence_score": 65.0, "p_evidence_sigmoid": 0.73, "stat_provable": 0.40, "p_claim_provable": 0.55},
            "payment_analysis_json": {"ability_score": 80, "insolvency_risk": "low", "p_willingness": 0.90, "p_payment": 0.98},
        },
    })

    # ── Case 4: Insolvency case — Strong evidence, EUR 4500, defendant insolvent, unsuccessful ──
    c4_id = uuid.uuid4()
    cases.append({
        "case": Case(
            id=c4_id,
            user_id=admin_user_id,
            title="Becker e.K. vs. Novak s.r.o. — Zahlungsausfall wegen Insolvenz",
            status=CaseStatus.COMPLETED,
            court_name="Amtsgericht Köln",
            court_address="Luxemburger Str. 101, 50939 Köln",
            court_country="DE",
            claimant_is_legal_person=False,
            claimant_name="Thomas Becker e.K.",
            claimant_address="Apostelnstraße 15, 50667 Köln",
            claimant_city="Köln",
            claimant_country="DE",
            claimant_email="t.becker@becker-it.de",
            defendant_is_legal_person=True,
            defendant_name="Novak Strojírenství s.r.o.",
            defendant_address="Václavské náměstí 10, 110 00 Praha",
            defendant_city="Praha",
            defendant_country="CZ",
            defendant_email="info@novak-stroj.cz",
            jurisdiction_basis="Art. 4 Abs. 1 EuGVVO",
            claimant_domicile_country="DE",
            defendant_domicile_country="CZ",
            court_member_state="DE",
            is_cross_border=True,
            claim_amount=4500.0,
            claim_currency="EUR",
            claim_request_costs=True,
            claim_interest_rate=5.0,
            claim_interest_from_date="2025-02-01",
            claim_description=(
                "Lieferung von IT-Ausstattung an Beklagte. "
                "Vollständige Dokumentation vorhanden. "
                "Beklagte hat Insolvenz angemeldet."
            ),
            claim_basis="Kaufvertrag, Auftragsbestätigung, Lieferschein",
            claim_evidence=(
                "Kaufvertrag, Auftragsbestätigung, Lieferschein, "
                "Rechnung Nr. BIT-2025-044, zwei Mahnungen, "
                "Insolvenzbekanntmachung des Handelsregisters"
            ),
            applicability_result="applicable",
            success_probability=0.15,
            assessment_summary=(
                "Starke Beweislage, aber Beklagter ist insolvent. "
                "Urteil gewonnen, Vollstreckung gescheitert."
            ),
            created_at=now - timedelta(days=120),
            updated_at=now - timedelta(days=20),
        ),
        "events": [
            CaseEvent(id=uuid.uuid4(), case_id=c4_id,
                      event_type=CaseEventType.FILED,
                      payload={"court": "Amtsgericht Köln", "date": "2025-03-01"},
                      created_at=now - timedelta(days=115)),
            CaseEvent(id=uuid.uuid4(), case_id=c4_id,
                      event_type=CaseEventType.SERVICE_OK,
                      payload={"method": "post", "date": "2025-03-20"},
                      created_at=now - timedelta(days=100)),
            CaseEvent(id=uuid.uuid4(), case_id=c4_id,
                      event_type=CaseEventType.DEFAULT,
                      payload={"reason": "no_response", "date": "2025-04-20"},
                      created_at=now - timedelta(days=70)),
            CaseEvent(id=uuid.uuid4(), case_id=c4_id,
                      event_type=CaseEventType.JUDGMENT_WIN,
                      payload={"amount_awarded": 4500.0, "date": "2025-04-25"},
                      created_at=now - timedelta(days=65)),
            CaseEvent(id=uuid.uuid4(), case_id=c4_id,
                      event_type=CaseEventType.COLLECTION_FAILED,
                      payload={"reason": "defendant_insolvent", "date": "2025-06-01"},
                      created_at=now - timedelta(days=20)),
        ],
        "score_overrides": {
            "evidence_score": 85.0,
            "p_claim_valid": 0.88, "p_claim_provable": 0.82, "p_payment": 0.11,
            "p_cash_success": 0.08,
            "legal_validity_json": {"p_entstanden": 0.92, "p_not_untergegangen": 0.85, "p_durchsetzbar": 0.90, "applicable_law": "tschech. OZ §2079 / Rom-I-VO Art. 4", "p_claim_valid_llm": 0.70, "stat_valid": 0.75},
            "provability_json": {"evidence_score": 85.0, "p_evidence_sigmoid": 0.95, "stat_provable": 0.40, "p_claim_provable": 0.82},
            "payment_analysis_json": {"ability_score": 5, "insolvency_risk": "high", "ability_reasoning": "Insolvenzverfahren beim Handelsregister Praha eingetragen", "p_willingness": 0.50, "p_payment": 0.11},
        },
    })

    # ── Case 5: Cross-border case — IT supplier, EUR 1200, defendant FR, successful via default ──
    c5_id = uuid.uuid4()
    cases.append({
        "case": Case(
            id=c5_id,
            user_id=admin_user_id,
            title="Schmidt IT GmbH vs. Dupont SARL — IT-Dienstleistungen",
            status=CaseStatus.COMPLETED,
            court_name="Amtsgericht Frankfurt am Main",
            court_address="Gerichtsstraße 2, 60313 Frankfurt am Main",
            court_country="DE",
            claimant_is_legal_person=True,
            claimant_name="Schmidt IT Solutions GmbH",
            claimant_address="Mainzer Landstraße 50, 60325 Frankfurt am Main",
            claimant_city="Frankfurt am Main",
            claimant_country="DE",
            claimant_email="recht@schmidt-it.de",
            defendant_is_legal_person=True,
            defendant_name="Dupont Digital SARL",
            defendant_address="15 Rue de Rivoli, 75001 Paris",
            defendant_city="Paris",
            defendant_country="FR",
            defendant_email="contact@dupont-digital.fr",
            jurisdiction_basis="Art. 7 Nr. 1 lit. b EuGVVO — Erfüllungsort der Dienstleistung",
            jurisdiction_details="IT-Dienstleistungen remote von Frankfurt aus erbracht",
            claimant_domicile_country="DE",
            defendant_domicile_country="FR",
            court_member_state="DE",
            is_cross_border=True,
            claim_amount=1200.0,
            claim_currency="EUR",
            claim_request_costs=True,
            claim_interest_rate=5.0,
            claim_interest_from_date="2025-05-01",
            claim_description=(
                "Remote-IT-Support und Systemwartung für die Beklagte "
                "im Zeitraum Januar bis März 2025. "
                "Beklagte reagierte nicht auf Rechnungen und Mahnungen."
            ),
            claim_basis="Dienstleistungsvertrag vom 15.12.2024, E-Mail-Korrespondenz",
            claim_evidence=(
                "Vertrag, Stundennachweise, Rechnung Nr. SIT-2025-031, "
                "zwei Mahnungen per Einschreiben"
            ),
            applicability_result="applicable",
            success_probability=0.72,
            assessment_summary=(
                "Grenzüberschreitend DE→FR. Versäumnisurteil nach ausbleibender Reaktion. "
                "Vollstreckung in Frankreich erfolgreich."
            ),
            created_at=now - timedelta(days=110),
            updated_at=now - timedelta(days=8),
        ),
        "events": [
            CaseEvent(id=uuid.uuid4(), case_id=c5_id,
                      event_type=CaseEventType.FILED,
                      payload={"court": "Amtsgericht Frankfurt am Main", "date": "2025-04-01"},
                      created_at=now - timedelta(days=105)),
            CaseEvent(id=uuid.uuid4(), case_id=c5_id,
                      event_type=CaseEventType.SERVICE_OK,
                      payload={"method": "huissier", "date": "2025-04-20"},
                      created_at=now - timedelta(days=90)),
            CaseEvent(id=uuid.uuid4(), case_id=c5_id,
                      event_type=CaseEventType.DEFAULT,
                      payload={"reason": "no_response_within_30_days", "date": "2025-05-25"},
                      created_at=now - timedelta(days=55)),
            CaseEvent(id=uuid.uuid4(), case_id=c5_id,
                      event_type=CaseEventType.JUDGMENT_WIN,
                      payload={"amount_awarded": 1200.0, "date": "2025-05-30"},
                      created_at=now - timedelta(days=50)),
            CaseEvent(id=uuid.uuid4(), case_id=c5_id,
                      event_type=CaseEventType.PAYMENT_RECEIVED,
                      payload={"amount": 1200.0, "method": "bank_transfer", "date": "2025-07-05"},
                      created_at=now - timedelta(days=8)),
        ],
        "score_overrides": {
            "evidence_score": 75.0,
            "p_claim_valid": 0.83, "p_claim_provable": 0.76, "p_payment": 0.63,
            "p_cash_success": 0.40,
            "legal_validity_json": {"p_entstanden": 0.88, "p_not_untergegangen": 0.92, "p_durchsetzbar": 0.90, "applicable_law": "frz. Code Civil Art. 1709 / Rom-I-VO Art. 4", "p_claim_valid_llm": 0.73, "stat_valid": 0.75},
            "provability_json": {"evidence_score": 75.0, "p_evidence_sigmoid": 0.88, "stat_provable": 0.40, "p_claim_provable": 0.76},
            "payment_analysis_json": {"ability_score": 68, "insolvency_risk": "low", "p_willingness": 0.55, "p_payment": 0.63},
        },
    })

    return cases


def _build_historical_events(admin_user_id: UUID) -> tuple[list[Case], list[CaseEvent]]:  # noqa: C901
    """Generate 75 historical cases with rich, outcome-correlated features for NN training.

    Outcome distribution (60 NN training cases + 15 REJECTED excluded):
      Group 1 (15) service_fail  → REJECTED, no NN label
      Group 2 (22) full_success  → PAYMENT_RECEIVED (class 0)
      Group 3 ( 6) insolvency    → COLLECTION_FAILED (class 2)
      Group 4 (12) partial       → SETTLED only, no PAYMENT_RECEIVED (class 1)
      Group 5 (10) win+coll.fail → COLLECTION_FAILED (class 2)
      Group 6 (10) judgment_loss → JUDGMENT_LOSS (class 2)

    Text fields embed keywords for all 40 NN feature dimensions:
    Anspruchsart (Zahlung/Herausgabe/Schadenersatz), Rechtsgrund (Vertrag/Delikt),
    B2B/B2C/C2C, Beweise (Vertrag, Lieferschein, Rechnung, Mahnung, GStV),
    Einwendungen (kein Vertrag, mangelhaft, Verjährung), Insolvenz, Dienstleistung.
    Year/quarter is spread across 2022-2025 via created_at.
    """
    now = datetime.utcnow()
    all_cases: list[Case] = []
    all_events: list[CaseEvent] = []
    case_idx = 0

    # ── helpers ──────────────────────────────────────────────────────────────

    def _ev(case_id: UUID, etype: CaseEventType, days_ago: int) -> CaseEvent:
        return CaseEvent(
            id=uuid.uuid4(),
            case_id=case_id,
            event_type=etype,
            payload={"source": "historical_seed"},
            created_at=now - timedelta(days=max(days_ago, 1)),
        )

    def _make(  # noqa: PLR0913
        idx: int,
        status: CaseStatus,
        amount: float,
        claimant_legal: bool,
        defendant_legal: bool,
        claimant_country: str,
        defendant_country: str,
        is_cross_border: bool,
        claim_basis: str,
        claim_evidence: str,
        claim_description: str,
    ) -> Case:
        # Spread created_at across ~3 years (case 0 ≈ 2023-01, case 74 ≈ 2025-11)
        days_back = max(10, 1050 - idx * 14)
        return Case(
            id=uuid.uuid4(),
            user_id=admin_user_id,
            title=f"[HIST] Historischer Fall #{idx + 1:03d}",
            status=status,
            claim_amount=round(amount, 2),
            claim_currency="EUR",
            claimant_name=f"Kläger {idx + 1}",
            claimant_country=claimant_country,
            claimant_domicile_country=claimant_country,
            claimant_is_legal_person=claimant_legal,
            defendant_name=f"Beklagter {idx + 1}",
            defendant_country=defendant_country,
            defendant_domicile_country=defendant_country,
            defendant_is_legal_person=defendant_legal,
            is_cross_border=is_cross_border,
            claim_basis=claim_basis,
            claim_evidence=claim_evidence,
            claim_description=claim_description,
            created_at=now - timedelta(days=days_back),
            updated_at=now - timedelta(days=max(1, days_back - 60)),
        )

    def _d(idx: int) -> str:
        return f"{(idx % 28) + 1:02d}.{(idx % 9) + 1:02d}.202{2 + (idx % 4)}"

    def _n(idx: int) -> str:
        return str(1000 + idx)

    def _a(idx: int) -> str:
        return str(int(500 + (idx * 47) % 4500))

    # ── Group 1: service_fail (15) → REJECTED, not in NN training ────────────
    _g1_cl = ["DE", "DE", "AT", "FR", "IT", "DE", "NL", "DE", "ES", "DE", "AT", "DE", "FR", "DE", "NL"]
    _g1_df = ["FR", "IT", "ES", "BE", "NL", "PL", "CZ", "RO", "HU", "SK", "BG", "HR", "PT", "GR", "LV"]
    for i in range(15):
        c = _make(
            case_idx,
            status=CaseStatus.REJECTED,
            amount=round(400 + (case_idx * 53) % 3600, 2),
            claimant_legal=bool(i % 2),
            defendant_legal=bool(i % 3),
            claimant_country=_g1_cl[i],
            defendant_country=_g1_df[i],
            is_cross_border=True,
            claim_basis=f"Kaufvertrag vom {_d(case_idx)}, Auftragsbestätigung",
            claim_evidence=f"Rechnung Nr. {_n(case_idx)}, Fälligkeit {_d(case_idx)}",
            claim_description="Beklagter unter angegebener Adresse nicht erreichbar. Zustellung fehlgeschlagen.",
        )
        all_cases.append(c)
        all_events += [
            _ev(c.id, CaseEventType.FILED,        400 - case_idx * 2),
            _ev(c.id, CaseEventType.SERVICE_FAIL, 390 - case_idx * 2),
        ]
        case_idx += 1

    # ── Group 2: full_success (22) → PAYMENT_RECEIVED (class 0) ──────────────
    # Sub-A (8): B2B, DE→DE, Zahlung, Kaufvertrag, full evidence set
    _g2a_amounts = [850, 1200, 2100, 1650, 975, 3200, 1450, 2750]
    for i in range(8):
        has_gstv = i % 4 == 0  # 2 of 8 have Gerichtsstandsvereinbarung
        basis = (
            f"Kaufvertrag vom {_d(case_idx)}, Gerichtsstandsvereinbarung zugunsten AG Stuttgart"
            if has_gstv else
            f"Schriftlicher Kaufvertrag vom {_d(case_idx)}, Auftragsbestätigung"
        )
        ev_parts = [
            f"Kaufvertrag vom {_d(case_idx)}",
            f"Lieferschein Nr. {_n(case_idx)} mit Empfangsbestätigung",
            f"Rechnung Nr. {_n(case_idx)} über EUR {_g2a_amounts[i]}",
            f"Mahnung vom {_d(case_idx)} mit 14-Tage-Frist",
        ]
        c = _make(
            case_idx,
            status=CaseStatus.COMPLETED,
            amount=_g2a_amounts[i],
            claimant_legal=True,
            defendant_legal=bool(i % 3 != 1),
            claimant_country="DE",
            defendant_country="DE",
            is_cross_border=False,
            claim_basis=basis,
            claim_evidence=", ".join(ev_parts),
            claim_description=(
                f"Zahlung aus Kaufvertrag. Lieferung erfolgte am {_d(case_idx)}. "
                f"Rechnung Nr. {_n(case_idx)} über EUR {_g2a_amounts[i]} blieb unbezahlt. "
                "Beklagter hat trotz Mahnung und Fristsetzung nicht gezahlt."
            ),
        )
        all_cases.append(c)
        all_events += [
            _ev(c.id, CaseEventType.FILED,            350 - case_idx),
            _ev(c.id, CaseEventType.SERVICE_OK,       340 - case_idx),
            _ev(c.id, CaseEventType.DEFAULT,          310 - case_idx),
            _ev(c.id, CaseEventType.JUDGMENT_WIN,     300 - case_idx),
            _ev(c.id, CaseEventType.PAYMENT_RECEIVED, 270 - case_idx),
        ]
        case_idx += 1

    # Sub-B (5): B2B, cross-border DE→AT/NL/BE, Zahlung, strong evidence
    _g2b_countries = ["AT", "NL", "BE", "AT", "NL"]
    _g2b_amounts = [1300, 2200, 1800, 950, 3100]
    for i in range(5):
        df_cc = _g2b_countries[i]
        ev_parts = [
            f"Kaufvertrag vom {_d(case_idx)}",
            f"Lieferschein Nr. {_n(case_idx)}, Empfangsquittung",
            f"Rechnung Nr. {_n(case_idx)} über EUR {_g2b_amounts[i]}",
            f"Einschreiben-Mahnung vom {_d(case_idx)} mit Fristsetzung",
        ]
        c = _make(
            case_idx,
            status=CaseStatus.COMPLETED,
            amount=_g2b_amounts[i],
            claimant_legal=True,
            defendant_legal=True,
            claimant_country="DE",
            defendant_country=df_cc,
            is_cross_border=True,
            claim_basis=f"Rahmenliefervertrag, Einzelbestellung vom {_d(case_idx)}",
            claim_evidence=", ".join(ev_parts),
            claim_description=(
                f"Grenzüberschreitende Warenlieferung DE→{df_cc}. "
                f"Zahlung der Rechnung Nr. {_n(case_idx)} über EUR {_g2b_amounts[i]} ausstehend. "
                "Beklagte hat trotz zweifacher Mahnung nicht reagiert."
            ),
        )
        all_cases.append(c)
        all_events += [
            _ev(c.id, CaseEventType.FILED,            350 - case_idx),
            _ev(c.id, CaseEventType.SERVICE_OK,       338 - case_idx),
            _ev(c.id, CaseEventType.DEFAULT,          308 - case_idx),
            _ev(c.id, CaseEventType.JUDGMENT_WIN,     298 - case_idx),
            _ev(c.id, CaseEventType.PAYMENT_RECEIVED, 265 - case_idx),
        ]
        case_idx += 1

    # Sub-C (4): B2B, cross-border DE→FR/IT/ES, Dienstleistung, won default
    _g2c_countries = ["FR", "IT", "ES", "FR"]
    _g2c_amounts = [1100, 2400, 1750, 980]
    for i in range(4):
        df_cc = _g2c_countries[i]
        ev_parts = [
            f"Dienstleistungsvertrag vom {_d(case_idx)}",
            f"Stundennachweise Zeitraum Q{(case_idx % 4)+1}/202{2+(case_idx%3)}",
            f"Rechnung Nr. {_n(case_idx)} über EUR {_g2c_amounts[i]}",
            f"Mahnung mit Fristsetzung vom {_d(case_idx)}",
        ]
        c = _make(
            case_idx,
            status=CaseStatus.COMPLETED,
            amount=_g2c_amounts[i],
            claimant_legal=True,
            defendant_legal=True,
            claimant_country="DE",
            defendant_country=df_cc,
            is_cross_border=True,
            claim_basis=f"Dienstleistungsvertrag vom {_d(case_idx)}, E-Mail-Korrespondenz",
            claim_evidence=", ".join(ev_parts),
            claim_description=(
                f"IT-Dienstleistungen und Beratung für Beklagte in {df_cc}. "
                f"Rechnung Nr. {_n(case_idx)} über EUR {_g2c_amounts[i]} blieb unbezahlt. "
                "Beklagte reagierte nicht auf Mahnungen. Versäumnisurteil ergangen."
            ),
        )
        all_cases.append(c)
        all_events += [
            _ev(c.id, CaseEventType.FILED,            345 - case_idx),
            _ev(c.id, CaseEventType.SERVICE_OK,       330 - case_idx),
            _ev(c.id, CaseEventType.DEFAULT,          300 - case_idx),
            _ev(c.id, CaseEventType.JUDGMENT_WIN,     290 - case_idx),
            _ev(c.id, CaseEventType.PAYMENT_RECEIVED, 255 - case_idx),
        ]
        case_idx += 1

    # Sub-D (3): B2C (legal→private), DE→DE, Zahlung, Kaufvertrag
    _g2d_amounts = [650, 480, 820]
    for i in range(3):
        ev_parts = [
            f"Kaufvertrag vom {_d(case_idx)}",
            f"Lieferschein Nr. {_n(case_idx)}",
            f"Rechnung Nr. {_n(case_idx)} über EUR {_g2d_amounts[i]}",
            f"Mahnung vom {_d(case_idx)}",
        ]
        c = _make(
            case_idx,
            status=CaseStatus.COMPLETED,
            amount=_g2d_amounts[i],
            claimant_legal=True,
            defendant_legal=False,
            claimant_country="DE",
            defendant_country="DE",
            is_cross_border=False,
            claim_basis=f"Kaufvertrag vom {_d(case_idx)}",
            claim_evidence=", ".join(ev_parts),
            claim_description=(
                f"Kaufpreiszahlung ausstehend. Beklagter (Privatperson) hat Ware erhalten, "
                f"Rechnung Nr. {_n(case_idx)} jedoch nicht beglichen. Mahnung blieb ohne Reaktion."
            ),
        )
        all_cases.append(c)
        all_events += [
            _ev(c.id, CaseEventType.FILED,            340 - case_idx),
            _ev(c.id, CaseEventType.SERVICE_OK,       330 - case_idx),
            _ev(c.id, CaseEventType.DEFAULT,          300 - case_idx),
            _ev(c.id, CaseEventType.JUDGMENT_WIN,     290 - case_idx),
            _ev(c.id, CaseEventType.PAYMENT_RECEIVED, 260 - case_idx),
        ]
        case_idx += 1

    # Sub-E (2): B2B, Herausgabe + Kaufvertrag, won
    for i in range(2):
        ev_parts = [
            f"Kaufvertrag vom {_d(case_idx)}, Eigentumsvorbehaltsklausel",
            f"Lieferschein Nr. {_n(case_idx)}",
            f"Mahnung auf Herausgabe vom {_d(case_idx)}",
        ]
        c = _make(
            case_idx,
            status=CaseStatus.COMPLETED,
            amount=round(900 + i * 600, 2),
            claimant_legal=True,
            defendant_legal=True,
            claimant_country="DE",
            defendant_country=["AT", "NL"][i],
            is_cross_border=True,
            claim_basis=f"Kaufvertrag mit Eigentumsvorbehalt vom {_d(case_idx)}",
            claim_evidence=", ".join(ev_parts),
            claim_description=(
                "Herausgabe der gelieferten Waren verlangt (Eigentumsvorbehalt). "
                "Kaufpreis nicht beglichen. Beklagter verweigert Rückgabe. "
                "Herausgabeanspruch aus Kaufvertrag mit Eigentumsvorbehalt."
            ),
        )
        all_cases.append(c)
        all_events += [
            _ev(c.id, CaseEventType.FILED,            335 - case_idx),
            _ev(c.id, CaseEventType.SERVICE_OK,       325 - case_idx),
            _ev(c.id, CaseEventType.DEFAULT,          295 - case_idx),
            _ev(c.id, CaseEventType.JUDGMENT_WIN,     285 - case_idx),
            _ev(c.id, CaseEventType.PAYMENT_RECEIVED, 250 - case_idx),
        ]
        case_idx += 1

    # ── Group 3: insolvency → COLLECTION_FAILED (6) → class 2 ────────────────
    # Strong evidence, eastern-EU defendants, Insolvenz keyword
    _g3_countries = ["PL", "CZ", "SK", "HU", "RO", "BG"]
    _g3_amounts = [2800, 3400, 1900, 4200, 2600, 3100]
    for i in range(6):
        ev_parts = [
            f"Kaufvertrag vom {_d(case_idx)}, Auftragsbestätigung",
            f"Lieferschein Nr. {_n(case_idx)} mit Empfangsbestätigung",
            f"Rechnung Nr. {_n(case_idx)} über EUR {_g3_amounts[i]}",
            f"Erste und zweite Mahnung mit Fristsetzung",
        ]
        c = _make(
            case_idx,
            status=CaseStatus.COMPLETED,
            amount=_g3_amounts[i],
            claimant_legal=True,
            defendant_legal=True,
            claimant_country="DE",
            defendant_country=_g3_countries[i],
            is_cross_border=True,
            claim_basis=f"Kaufvertrag vom {_d(case_idx)}, Auftragsbestätigung",
            claim_evidence=", ".join(ev_parts),
            claim_description=(
                "Vollständige Dokumentation vorhanden. "
                "Beklagter hat Insolvenzverfahren angemeldet. "
                "Insolvenzbekanntmachung im Handelsregister eingetragen. "
                "Vollstreckung im Ausland wegen Insolvenz gescheitert. "
                "Forderung zur Insolvenztabelle angemeldet."
            ),
        )
        all_cases.append(c)
        all_events += [
            _ev(c.id, CaseEventType.FILED,             320 - case_idx),
            _ev(c.id, CaseEventType.SERVICE_OK,        308 - case_idx),
            _ev(c.id, CaseEventType.DEFAULT,           278 - case_idx),
            _ev(c.id, CaseEventType.JUDGMENT_WIN,      268 - case_idx),
            _ev(c.id, CaseEventType.COLLECTION_FAILED, 230 - case_idx),
        ]
        case_idx += 1

    # ── Group 4: partial_success → SETTLED only (12) → class 1 ───────────────
    # SETTLED without PAYMENT_RECEIVED → class 1
    # Sub-A (8): quality dispute (mangelhaft), cross-border
    _g4a_countries = ["IT", "FR", "ES", "IT", "FR", "ES", "PT", "IT"]
    _g4a_amounts = [1600, 2200, 1350, 3000, 1900, 2600, 1100, 2800]
    for i in range(8):
        has_delivery = i % 2 == 0
        ev_parts = [f"Kaufvertrag vom {_d(case_idx)}", f"Rechnung Nr. {_n(case_idx)}"]
        if has_delivery:
            ev_parts.append(f"Lieferschein Nr. {_n(case_idx)}")
        ev_parts.append(f"Mahnung vom {_d(case_idx)}")
        c = _make(
            case_idx,
            status=CaseStatus.COMPLETED,
            amount=_g4a_amounts[i],
            claimant_legal=True,
            defendant_legal=bool(i % 2),
            claimant_country="DE",
            defendant_country=_g4a_countries[i],
            is_cross_border=True,
            claim_basis=f"Kaufvertrag vom {_d(case_idx)}",
            claim_evidence=", ".join(ev_parts),
            claim_description=(
                "Beklagter beanstandet die Qualität der gelieferten Waren — mangelhaft erfüllt. "
                "Qualitätsmängel werden geltend gemacht, Klägerin bestreitet die Mängelrüge. "
                "Vergleich erzielt: Zahlung eines reduzierten Betrages vereinbart (Teilerfolg)."
            ),
        )
        all_cases.append(c)
        all_events += [
            _ev(c.id, CaseEventType.FILED,               310 - case_idx),
            _ev(c.id, CaseEventType.SERVICE_OK,          298 - case_idx),
            _ev(c.id, CaseEventType.DEFENDANT_RESPONDED, 275 - case_idx),
            _ev(c.id, CaseEventType.SETTLED,             250 - case_idx),
            # No PAYMENT_RECEIVED → class 1
        ]
        case_idx += 1

    # Sub-B (4): Schadenersatz / außervertraglicher Schaden, settled
    _g4b_countries = ["IT", "FR", "ES", "NL"]
    _g4b_amounts = [1400, 2000, 1750, 1250]
    for i in range(4):
        ev_parts = [
            f"Werkvertrag vom {_d(case_idx)}",
            f"Schadensdokumentation vom {_d(case_idx)}",
            f"Rechnung Nr. {_n(case_idx)} über Schadenersatz",
        ]
        c = _make(
            case_idx,
            status=CaseStatus.COMPLETED,
            amount=_g4b_amounts[i],
            claimant_legal=bool(i % 2),
            defendant_legal=bool(i % 3 != 1),
            claimant_country=["DE", "AT", "FR", "DE"][i],
            defendant_country=_g4b_countries[i],
            is_cross_border=True,
            claim_basis=f"Außervertraglicher Schadenersatzanspruch, Werkvertrag vom {_d(case_idx)}",
            claim_evidence=", ".join(ev_parts),
            claim_description=(
                "Schadenersatz wegen mangelhafter Werkleistung. "
                "Beklagter hat Werkleistung nicht erfüllt bzw. mangelhaft erbracht. "
                "Schaden entstanden durch Nichterfüllung vertraglicher Pflichten. "
                "Vergleich: Teilbetrag als Schadenersatz anerkannt."
            ),
        )
        all_cases.append(c)
        all_events += [
            _ev(c.id, CaseEventType.FILED,               305 - case_idx),
            _ev(c.id, CaseEventType.SERVICE_OK,          292 - case_idx),
            _ev(c.id, CaseEventType.DEFENDANT_RESPONDED, 268 - case_idx),
            _ev(c.id, CaseEventType.SETTLED,             244 - case_idx),
            # No PAYMENT_RECEIVED → class 1
        ]
        case_idx += 1

    # ── Group 5: win → COLLECTION_FAILED (10) → class 2 ──────────────────────
    # Sub-A (5): insolvency
    _g5a_countries = ["CZ", "PL", "HU", "RO", "SK"]
    _g5a_amounts = [2100, 3500, 1850, 4000, 2700]
    for i in range(5):
        ev_parts = [
            f"Kaufvertrag vom {_d(case_idx)}",
            f"Lieferschein Nr. {_n(case_idx)}",
            f"Rechnung Nr. {_n(case_idx)}",
            f"Mahnung mit Fristsetzung vom {_d(case_idx)}",
        ]
        c = _make(
            case_idx,
            status=CaseStatus.COMPLETED,
            amount=_g5a_amounts[i],
            claimant_legal=True,
            defendant_legal=True,
            claimant_country="DE",
            defendant_country=_g5a_countries[i],
            is_cross_border=True,
            claim_basis=f"Kaufvertrag vom {_d(case_idx)}",
            claim_evidence=", ".join(ev_parts),
            claim_description=(
                "Urteil gewonnen. Beklagter hat Insolvenz angemeldet. "
                "Insolvenzverfahren eröffnet, Forderung zur Insolvenztabelle angemeldet. "
                "Vollstreckung mangels vollstreckbarem Vermögen eingestellt."
            ),
        )
        all_cases.append(c)
        all_events += [
            _ev(c.id, CaseEventType.FILED,                290 - case_idx),
            _ev(c.id, CaseEventType.SERVICE_OK,           278 - case_idx),
            _ev(c.id, CaseEventType.DEFENDANT_RESPONDED,  255 - case_idx),
            _ev(c.id, CaseEventType.JUDGMENT_WIN,         228 - case_idx),
            _ev(c.id, CaseEventType.COLLECTION_FAILED,    195 - case_idx),
        ]
        case_idx += 1

    # Sub-B (5): no attachable assets, various EU
    _g5b_countries = ["FR", "IT", "ES", "PT", "GR"]
    _g5b_amounts = [1700, 2900, 2300, 1600, 3200]
    for i in range(5):
        ev_parts = [
            f"Kaufvertrag vom {_d(case_idx)}",
            f"Lieferschein Nr. {_n(case_idx)}",
            f"Rechnung Nr. {_n(case_idx)}",
        ]
        c = _make(
            case_idx,
            status=CaseStatus.COMPLETED,
            amount=_g5b_amounts[i],
            claimant_legal=True,
            defendant_legal=bool(i % 2),
            claimant_country="DE",
            defendant_country=_g5b_countries[i],
            is_cross_border=True,
            claim_basis=f"Kaufvertrag vom {_d(case_idx)}",
            claim_evidence=", ".join(ev_parts),
            claim_description=(
                "Urteil erwirkt. Vollstreckung im Ausland nicht erfolgreich. "
                "Beklagter hat kein pfändbares Vermögen im Inland nachgewiesen. "
                "Vollstreckung eingestellt. Forderungsausfall."
            ),
        )
        all_cases.append(c)
        all_events += [
            _ev(c.id, CaseEventType.FILED,                285 - case_idx),
            _ev(c.id, CaseEventType.SERVICE_OK,           272 - case_idx),
            _ev(c.id, CaseEventType.DEFENDANT_RESPONDED,  249 - case_idx),
            _ev(c.id, CaseEventType.JUDGMENT_WIN,         222 - case_idx),
            _ev(c.id, CaseEventType.COLLECTION_FAILED,    188 - case_idx),
        ]
        case_idx += 1

    # ── Group 6: JUDGMENT_LOSS (10) → class 2 ────────────────────────────────
    # Sub-A (5): no contract / oral only (kein Vertrag defense)
    _g6a_countries = ["DE", "AT", "DE", "NL", "DE"]
    _g6a_amounts = [420, 680, 550, 780, 390]
    for i in range(5):
        c = _make(
            case_idx,
            status=CaseStatus.COMPLETED,
            amount=_g6a_amounts[i],
            claimant_legal=bool(i % 3 == 0),
            defendant_legal=False,
            claimant_country="DE",
            defendant_country=_g6a_countries[i],
            is_cross_border=_g6a_countries[i] != "DE",
            claim_basis="Mündliche Vereinbarung, keine schriftlichen Unterlagen",
            claim_evidence="Keine schriftlichen Nachweise vorhanden. Zeugenaussagen.",
            claim_description=(
                "Mündlich vereinbarte Leistung ohne schriftlichen Vertrag. "
                "Beklagter bestreitet das Zustandekommen eines Vertrages — kein Vertrag abgeschlossen. "
                "Keine Dokumentation der erbrachten Leistung vorhanden. "
                "Klage abgewiesen mangels Nachweises."
            ),
        )
        all_cases.append(c)
        all_events += [
            _ev(c.id, CaseEventType.FILED,                280 - case_idx),
            _ev(c.id, CaseEventType.SERVICE_OK,           268 - case_idx),
            _ev(c.id, CaseEventType.DEFENDANT_RESPONDED,  245 - case_idx),
            _ev(c.id, CaseEventType.JUDGMENT_LOSS,        215 - case_idx),
        ]
        case_idx += 1

    # Sub-B (3): mangelhaft + insufficient evidence
    _g6b_countries = ["DE", "AT", "BE"]
    _g6b_amounts = [950, 720, 1100]
    for i in range(3):
        c = _make(
            case_idx,
            status=CaseStatus.COMPLETED,
            amount=_g6b_amounts[i],
            claimant_legal=bool(i % 2),
            defendant_legal=True,
            claimant_country="DE",
            defendant_country=_g6b_countries[i],
            is_cross_border=_g6b_countries[i] != "DE",
            claim_basis=f"Kaufvertrag mündlich, Rechnung Nr. {_n(case_idx)}",
            claim_evidence=f"Rechnung Nr. {_n(case_idx)}, keine weiteren Nachweise",
            claim_description=(
                "Beklagter macht Qualitätsmängel der gelieferten Ware geltend — mangelhaft erfüllt. "
                "Mängelrüge: Ware entspricht nicht der vereinbarten Beschaffenheit. "
                "Klägerin kann Mängelfreiheit nicht nachweisen. "
                "Gericht folgt der Einwendung: Klage abgewiesen."
            ),
        )
        all_cases.append(c)
        all_events += [
            _ev(c.id, CaseEventType.FILED,                275 - case_idx),
            _ev(c.id, CaseEventType.SERVICE_OK,           263 - case_idx),
            _ev(c.id, CaseEventType.DEFENDANT_RESPONDED,  240 - case_idx),
            _ev(c.id, CaseEventType.JUDGMENT_LOSS,        210 - case_idx),
        ]
        case_idx += 1

    # Sub-C (2): Verjährung defense
    _g6c_amounts = [840, 1300]
    for i in range(2):
        ev_parts = [
            f"Kaufvertrag vom {_d(case_idx)} (alt)",
            f"Rechnung Nr. {_n(case_idx)} (über 3 Jahre alt)",
        ]
        c = _make(
            case_idx,
            status=CaseStatus.COMPLETED,
            amount=_g6c_amounts[i],
            claimant_legal=True,
            defendant_legal=bool(i),
            claimant_country="DE",
            defendant_country=["DE", "AT"][i],
            is_cross_border=bool(i),
            claim_basis=f"Kaufvertrag vom {_d(case_idx)}",
            claim_evidence=", ".join(ev_parts),
            claim_description=(
                "Forderung aus Kaufvertrag. Beklagter erhebt Einrede der Verjährung. "
                "Verjährung gemäß § 195 BGB (3 Jahre) eingetreten. "
                "Klage wegen Verjährung abgewiesen."
            ),
        )
        all_cases.append(c)
        all_events += [
            _ev(c.id, CaseEventType.FILED,                270 - case_idx),
            _ev(c.id, CaseEventType.SERVICE_OK,           258 - case_idx),
            _ev(c.id, CaseEventType.DEFENDANT_RESPONDED,  235 - case_idx),
            _ev(c.id, CaseEventType.JUDGMENT_LOSS,        205 - case_idx),
        ]
        case_idx += 1

    return all_cases, all_events


@router.post("/seed", response_model=SeedResponse, status_code=status.HTTP_201_CREATED)
async def seed_demo_data(
    admin: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
    force: bool = Query(False, description="Delete existing [HIST] cases and re-seed with fresh rich data"),
):
    """Seed 5 fictional completed cases + 75 historical observation cases for NN training.

    Idempotent by default: skips cases whose title already exists and skips
    historical seeding if ``[HIST]`` cases are already present.
    Pass ``?force=true`` to delete existing ``[HIST]`` cases and re-seed them
    with the current feature-rich training data.
    """
    try:
        # ── optionally delete existing [HIST] cases ──
        if force:
            # Fetch IDs of existing [HIST] cases first (to cascade-delete child rows)
            hist_ids_res = await db.execute(
                select(Case.id).where(Case.title.like("[HIST]%"))
            )
            hist_ids = [row[0] for row in hist_ids_res.fetchall()]
            if hist_ids:
                # Delete in FK-safe order: events → scores → cases
                await db.execute(
                    delete(CaseEvent).where(CaseEvent.case_id.in_(hist_ids))
                )
                await db.execute(
                    delete(CaseProcessScore).where(CaseProcessScore.case_id.in_(hist_ids))
                )
                await db.execute(
                    delete(Case).where(Case.id.in_(hist_ids))
                )

        # Check if historical data already seeded (after potential forced delete)
        hist_check = await db.execute(
            select(func.count(Case.id)).where(Case.title.like("[HIST]%"))
        )
        hist_exists = (hist_check.scalar() or 0) > 0

        fictional_count = 0
        historical_event_count = 0

        # ── 5 fictional cases ──
        seed_data = _build_seed_cases(admin.id)
        for item in seed_data:
            existing = await db.execute(
                select(func.count(Case.id)).where(Case.title == item["case"].title)
            )
            if (existing.scalar() or 0) > 0:
                continue

            db.add(item["case"])
            for event in item["events"]:
                db.add(event)

            # Create a v3 process score snapshot
            overrides = item["score_overrides"]
            pj = overrides.get("payment_analysis_json", {})
            score = CaseProcessScore(
                case_id=item["case"].id,
                # v3 pillars
                p_claim_valid=overrides.get("p_claim_valid"),
                p_claim_provable=overrides.get("p_claim_provable"),
                p_payment=overrides.get("p_payment"),
                legal_validity_json=overrides.get("legal_validity_json"),
                provability_json=overrides.get("provability_json"),
                payment_analysis_json=pj if pj else None,
                # legacy fields (for backward compat display)
                evidence_score=overrides.get("evidence_score", 50.0),
                evidence_breakdown=overrides.get("provability_json", {}).get("evidence_breakdown") or {"source": "seed_data"},
                ability_score=pj.get("ability_score", 75.0),
                ability_components={"insolvency_risk": pj.get("insolvency_risk", "unknown"), "source": "seed_data"},
                willingness_score=round((pj.get("p_willingness", 0.5)) * 100, 1),
                willingness_components={"p_willingness": pj.get("p_willingness", 0.5), "source": "seed_data"},
                p_cash_success=overrides.get("p_cash_success", 0.25),
                priors_json={"source": "seed_data"},
                posteriors_json={"source": "seed_data"},
                observations_json={"source": "seed_data"},
                drivers_json=[],
                model_version="v3-seed",
            )
            db.add(score)
            fictional_count += 1

        # ── 100 historical cases ──
        if not hist_exists:
            hist_cases, hist_events = _build_historical_events(admin.id)
            for c in hist_cases:
                db.add(c)
            for e in hist_events:
                db.add(e)
            historical_event_count = len(hist_events)
        else:
            historical_event_count = -1  # signal: already existed

        await db.commit()

        msg = f"{fictional_count} fiktive Fälle erstellt."
        if historical_event_count == -1:
            msg += " Historische Daten waren bereits vorhanden (kein force)."
        else:
            msg += f" {historical_event_count} historische Events aus 75 Fällen erstellt."

        return SeedResponse(
            fictional_cases_created=fictional_count,
            historical_aggregate_events_created=max(0, historical_event_count),
            message=msg,
        )

    except Exception:
        await db.rollback()
        logger.exception("Error seeding demo data")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Erstellen der Testdaten.",
        )


# ---------------------------------------------------------------------------
# 3) POST /api/statistics/update-priors  (admin only)
# ---------------------------------------------------------------------------

@router.post("/update-priors", response_model=UpdatePriorsResponse)
async def update_priors_from_outcomes(
    admin: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Recalculate Beta priors from ALL completed-case event outcomes.

    For each rate (served, default, settle, collect):
      1. Count successes and trials from ALL events in the database.
      2. Compute new_alpha = DEFAULT_alpha + total_successes
      3. Compute new_beta  = DEFAULT_beta  + total_failures
      4. Upsert into PriorsConfig (claim_subtype='general', country='*').
    """
    try:
        # Load ALL events
        all_events_result = await db.execute(select(CaseEvent))
        all_events = list(all_events_result.scalars().all())

        rates_updated: list[str] = []
        priors_items: list[UpdatedPriorItem] = []

        for rate_name in ["valid", "provable", "payment"]:
            mapping = RATE_EVENT_MAP.get(rate_name, {})
            success_types = mapping.get("success", set())
            failure_types = mapping.get("failure", set())

            successes = sum(1 for e in all_events if e.event_type in success_types)
            failures = sum(1 for e in all_events if e.event_type in failure_types)
            trials = successes + failures

            base_alpha, base_beta = DEFAULT_PRIORS.get(rate_name, (2.0, 2.0))

            new_alpha = base_alpha + successes
            new_beta = base_beta + failures

            # Upsert into PriorsConfig
            existing_result = await db.execute(
                select(PriorsConfig).where(
                    PriorsConfig.rate_name == rate_name,
                    PriorsConfig.claim_subtype == "general",
                    PriorsConfig.country == "*",
                )
            )
            existing = existing_result.scalar_one_or_none()

            old_alpha = existing.alpha if existing else base_alpha
            old_beta = existing.beta if existing else base_beta

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

            rates_updated.append(rate_name)
            posterior_mean = (
                round(new_alpha / (new_alpha + new_beta), 4)
                if (new_alpha + new_beta) > 0
                else 0.5
            )

            priors_items.append(UpdatedPriorItem(
                rate_name=rate_name,
                old_alpha=round(old_alpha, 2),
                old_beta=round(old_beta, 2),
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

# Approximate court fees by member state for EU Small Claims Procedure
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
    # Revenue side
    expected_commission: float
    # Cost components
    court_fees: float
    attorney_costs: float
    service_fees: float
    opponent_costs: float
    # Win scenario
    cost_compensation: float  # court_fees + attorney_costs recovered on win
    # Net expected value for project owner
    net_expected_value: float
    # Expected loss costs
    expected_loss_costs: float
    # Decision
    recommendation: str
    recommendation_reason: str
    min_probability_threshold: float  # 80%
    breakdown: dict


ev_router = APIRouter(prefix="/api/cases", tags=["cases", "statistics"])


@ev_router.get("/{case_id}/expected-value", response_model=ExpectedValueResult)
async def get_expected_value(
    case_id: UUID,
    admin: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Calculate expected value for a case based on its latest process score.

    Returns expected recovery, costs, commission, net EV, and a recommendation.
    """
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

    # Get latest process score (or compute on the fly)
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

    # --- Cost components ---
    court_country = case.court_country or case.court_member_state or "*"
    court_fees = _calculate_court_fees(claim_amount, court_country)

    is_cross_border = case.is_cross_border or (
        case.claimant_country and case.defendant_country
        and case.claimant_country != case.defendant_country
    )
    service_fees = 80.0 if is_cross_border else 50.0
    attorney_costs = _estimate_attorney_costs(claim_amount)
    opponent_costs = _estimate_opponent_costs(claim_amount)

    # --- Project owner EV formula ---
    # Revenue: p_win × 30% × claim_amount
    expected_commission = p_win * COMMISSION_RATE * claim_amount

    # Cost compensation on win: court_fees + attorney_costs recovered from opponent
    cost_compensation = court_fees + attorney_costs

    # Expected loss costs: p_loss × (own costs excl. service + opponent costs)
    # On loss we lose court fees, attorney costs, AND pay opponent costs
    expected_loss_costs = p_loss * (court_fees + attorney_costs + opponent_costs)

    # Net EV = expected commission - service_fees (always) - expected loss costs
    # Equivalent to:
    #   p_win × (30% × claim + cost_comp - own_costs)
    #   + p_loss × (-own_costs - opponent_costs)
    net_ev = expected_commission - service_fees - expected_loss_costs

    # --- Recommendation logic (minimum 80% win probability to take case) ---
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
