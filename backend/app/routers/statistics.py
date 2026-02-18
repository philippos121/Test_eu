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

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select, func
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
    "served": "Zustellungsrate",
    "default": "Versäumnisrate",
    "settle": "Vergleichsrate",
    "collect": "Inkassorate",
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


def _compute_net_ev(claim_amount: float, outcome_success: bool) -> float:
    """Compute net expected value for a completed case.

    For successful cases:
      net_ev = claim_amount * 0.70 - court_fees - service_costs

    The 0.70 factor represents the claimant's share after 30% commission.
    For unsuccessful cases net_ev is the negative of sunk costs.
    """
    if outcome_success:
        collected = claim_amount * (1.0 - COMMISSION_RATE)
        court_fees = _estimate_court_fees(claim_amount)
        return round(collected - court_fees - SERVICE_COSTS_FLAT, 2)
    else:
        court_fees = _estimate_court_fees(claim_amount)
        return round(-(court_fees + SERVICE_COSTS_FLAT), 2)


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
    for rate_name in ["served", "default", "settle", "collect"]:
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

    # ── Last 20 completed cases with detail ──
    # Sort by created_at descending, take 20
    sorted_completed = sorted(
        completed_cases_list,
        key=lambda c: c.created_at or datetime.min,
        reverse=True,
    )[:20]

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
            "p_served": 0.80, "p_default": 0.55, "p_win_contested": 0.75,
            "p_settle": 0.25, "p_collect": 0.70, "p_cash_success": 0.52,
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
            "p_served": 0.70, "p_default": 0.40, "p_win_contested": 0.15,
            "p_settle": 0.10, "p_collect": 0.30, "p_cash_success": 0.05,
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
            "p_served": 0.75, "p_default": 0.35, "p_win_contested": 0.50,
            "p_settle": 0.45, "p_collect": 0.60, "p_cash_success": 0.35,
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
            "p_served": 0.78, "p_default": 0.55, "p_win_contested": 0.70,
            "p_settle": 0.15, "p_collect": 0.10, "p_cash_success": 0.08,
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
            "p_served": 0.72, "p_default": 0.50, "p_win_contested": 0.60,
            "p_settle": 0.20, "p_collect": 0.65, "p_cash_success": 0.40,
        },
    })

    return cases


def _build_historical_events(admin_user_id: UUID) -> tuple[list[Case], list[CaseEvent]]:
    """Generate 100 historical observation cases with realistic event distributions.

    Target rates:
      - ~70% service success rate  (70 SERVICE_OK, 30 SERVICE_FAIL)
      - ~50% default rate          (35 DEFAULT, 35 DEFENDANT_RESPONDED of 70 served)
      - ~30% settlement rate       (11 SETTLED of 35 responded)
      - ~60% collection rate       (30 PAYMENT_RECEIVED of ~49 favorable outcomes)

    Each historical case gets a ``[HIST]`` title prefix for easy identification.
    """
    now = datetime.utcnow()
    all_cases: list[Case] = []
    all_events: list[CaseEvent] = []

    total = 100
    served_ok = 70
    served_fail = 30
    defaulted = 35          # of 70 served
    responded = 35          # of 70 served
    settled = 11            # of 35 responded (~30%)
    judgment = 24           # responded - settled
    judgment_win = 14       # of 24 judgment
    judgment_loss = 10      # of 24 judgment
    collected = 30          # of 49 favorable (defaulted + judgment_win)
    collection_failed = 19  # of 49 favorable

    case_idx = 0
    countries = ["DE", "FR", "IT", "AT", "NL", "ES", "BE"]

    def _make_hist_case(idx: int) -> Case:
        return Case(
            id=uuid.uuid4(),
            user_id=admin_user_id,
            title=f"[HIST] Historischer Fall #{idx + 1:03d}",
            status=CaseStatus.COMPLETED,
            claim_amount=round(500 + (idx * 47) % 4500, 2),
            claim_currency="EUR",
            claimant_name=f"Kläger {idx + 1}",
            defendant_name=f"Beklagter {idx + 1}",
            claimant_country=countries[idx % 7],
            defendant_country=countries[(idx + 3) % 7],
            is_cross_border=True,
            created_at=now - timedelta(days=365 - idx),
            updated_at=now - timedelta(days=30),
        )

    def _ev(case_id: UUID, etype: CaseEventType, days_ago: int) -> CaseEvent:
        return CaseEvent(
            id=uuid.uuid4(),
            case_id=case_id,
            event_type=etype,
            payload={"source": "historical_seed"},
            created_at=now - timedelta(days=max(days_ago, 1)),
        )

    # ── Group 1: service failed (30 cases) ──
    for _ in range(served_fail):
        c = _make_hist_case(case_idx)
        c.status = CaseStatus.REJECTED
        all_cases.append(c)
        all_events.append(_ev(c.id, CaseEventType.FILED, 350 - case_idx))
        all_events.append(_ev(c.id, CaseEventType.SERVICE_FAIL, 340 - case_idx))
        case_idx += 1

    # ── Group 2: served -> defaulted -> collected ──
    defaults_collected = min(collected, defaulted)  # 30 (limited by defaulted=35)
    for _ in range(defaults_collected):
        c = _make_hist_case(case_idx)
        all_cases.append(c)
        all_events.append(_ev(c.id, CaseEventType.FILED, 350 - case_idx))
        all_events.append(_ev(c.id, CaseEventType.SERVICE_OK, 340 - case_idx))
        all_events.append(_ev(c.id, CaseEventType.DEFAULT, 310 - case_idx))
        all_events.append(_ev(c.id, CaseEventType.JUDGMENT_WIN, 300 - case_idx))
        all_events.append(_ev(c.id, CaseEventType.PAYMENT_RECEIVED, 270 - case_idx))
        case_idx += 1

    # ── Group 3: served -> defaulted -> collection failed ──
    defaults_failed = defaulted - defaults_collected  # 5
    for _ in range(defaults_failed):
        c = _make_hist_case(case_idx)
        all_cases.append(c)
        all_events.append(_ev(c.id, CaseEventType.FILED, 350 - case_idx))
        all_events.append(_ev(c.id, CaseEventType.SERVICE_OK, 340 - case_idx))
        all_events.append(_ev(c.id, CaseEventType.DEFAULT, 310 - case_idx))
        all_events.append(_ev(c.id, CaseEventType.JUDGMENT_WIN, 300 - case_idx))
        all_events.append(_ev(c.id, CaseEventType.COLLECTION_FAILED, 270 - case_idx))
        case_idx += 1

    # ── Group 4: served -> responded -> settled -> payment ──
    for _ in range(settled):
        c = _make_hist_case(case_idx)
        all_cases.append(c)
        all_events.append(_ev(c.id, CaseEventType.FILED, 350 - case_idx))
        all_events.append(_ev(c.id, CaseEventType.SERVICE_OK, 340 - case_idx))
        all_events.append(_ev(c.id, CaseEventType.DEFENDANT_RESPONDED, 320 - case_idx))
        all_events.append(_ev(c.id, CaseEventType.SETTLED, 300 - case_idx))
        all_events.append(_ev(c.id, CaseEventType.PAYMENT_RECEIVED, 280 - case_idx))
        case_idx += 1

    # ── Group 5: served -> responded -> judgment win -> collected ──
    win_collected = max(0, collected - defaults_collected)
    for i in range(min(win_collected, judgment_win)):
        c = _make_hist_case(case_idx)
        all_cases.append(c)
        all_events.append(_ev(c.id, CaseEventType.FILED, 350 - case_idx))
        all_events.append(_ev(c.id, CaseEventType.SERVICE_OK, 340 - case_idx))
        all_events.append(_ev(c.id, CaseEventType.DEFENDANT_RESPONDED, 320 - case_idx))
        all_events.append(_ev(c.id, CaseEventType.JUDGMENT_WIN, 290 - case_idx))
        all_events.append(_ev(c.id, CaseEventType.PAYMENT_RECEIVED, 260 - case_idx))
        case_idx += 1

    # ── Group 6: served -> responded -> judgment win -> collection failed ──
    win_not_collected = judgment_win - min(win_collected, judgment_win)
    remaining_coll_fail = max(0, collection_failed - defaults_failed)
    win_failed = min(win_not_collected, remaining_coll_fail)
    for _ in range(win_failed):
        c = _make_hist_case(case_idx)
        all_cases.append(c)
        all_events.append(_ev(c.id, CaseEventType.FILED, 350 - case_idx))
        all_events.append(_ev(c.id, CaseEventType.SERVICE_OK, 340 - case_idx))
        all_events.append(_ev(c.id, CaseEventType.DEFENDANT_RESPONDED, 320 - case_idx))
        all_events.append(_ev(c.id, CaseEventType.JUDGMENT_WIN, 290 - case_idx))
        all_events.append(_ev(c.id, CaseEventType.COLLECTION_FAILED, 260 - case_idx))
        case_idx += 1

    # ── Group 7: served -> responded -> judgment loss ──
    for _ in range(judgment_loss):
        c = _make_hist_case(case_idx)
        all_cases.append(c)
        all_events.append(_ev(c.id, CaseEventType.FILED, 350 - case_idx))
        all_events.append(_ev(c.id, CaseEventType.SERVICE_OK, 340 - case_idx))
        all_events.append(_ev(c.id, CaseEventType.DEFENDANT_RESPONDED, 320 - case_idx))
        all_events.append(_ev(c.id, CaseEventType.JUDGMENT_LOSS, 290 - case_idx))
        case_idx += 1

    # ── Fill remaining to reach exactly 100 (extra successful default cases) ──
    while case_idx < total:
        c = _make_hist_case(case_idx)
        all_cases.append(c)
        all_events.append(_ev(c.id, CaseEventType.FILED, 350 - case_idx))
        all_events.append(_ev(c.id, CaseEventType.SERVICE_OK, 340 - case_idx))
        all_events.append(_ev(c.id, CaseEventType.DEFAULT, 310 - case_idx))
        all_events.append(_ev(c.id, CaseEventType.JUDGMENT_WIN, 300 - case_idx))
        all_events.append(_ev(c.id, CaseEventType.PAYMENT_RECEIVED, 270 - case_idx))
        case_idx += 1

    return all_cases, all_events


@router.post("/seed", response_model=SeedResponse, status_code=status.HTTP_201_CREATED)
async def seed_demo_data(
    admin: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Seed 5 fictional completed cases + 100 historical observation cases.

    Idempotent: skips cases whose title already exists and skips historical
    seeding if ``[HIST]`` cases are already present.
    """
    try:
        # Check if historical data already seeded
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

            # Create a process score snapshot
            overrides = item["score_overrides"]
            score = CaseProcessScore(
                case_id=item["case"].id,
                evidence_score=overrides.get("evidence_score", 50.0),
                evidence_breakdown={"source": "seed_data"},
                ability_score=75.0,
                ability_components={"source": "seed_data"},
                willingness_score=50.0,
                willingness_components={"source": "seed_data"},
                p_served=overrides.get("p_served", 0.70),
                p_default=overrides.get("p_default", 0.50),
                p_win_contested=overrides.get("p_win_contested", 0.50),
                p_settle=overrides.get("p_settle", 0.30),
                p_collect=overrides.get("p_collect", 0.60),
                p_cash_success=overrides.get("p_cash_success", 0.25),
                priors_json={"source": "seed_data"},
                posteriors_json={"source": "seed_data"},
                observations_json={"source": "seed_data"},
                drivers_json=[],
                model_version="v2-seed",
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
            msg += " Historische Daten waren bereits vorhanden."
        else:
            msg += f" {historical_event_count} historische Events aus 100 Fällen erstellt."

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

        for rate_name in ["served", "default", "settle", "collect"]:
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
    p_cash_success: float
    expected_recovery: float
    court_fees: float
    service_fees: float
    commission: float
    net_expected_value: float
    recommendation: str
    recommendation_reason: str
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

    p_cash = score.p_cash_success

    expected_recovery = claim_amount * p_cash

    court_country = case.court_country or case.court_member_state or "*"
    court_fees = _calculate_court_fees(claim_amount, court_country)

    is_cross_border = case.is_cross_border or (
        case.claimant_country and case.defendant_country
        and case.claimant_country != case.defendant_country
    )
    service_fees = 80.0 if is_cross_border else 50.0

    commission = expected_recovery * 0.30
    net_ev = expected_recovery - commission - court_fees - service_fees

    # Recommendation logic
    if net_ev > 0 and p_cash >= 0.35:
        recommendation = "empfohlen"
        reason = (
            f"Positiver erwarteter Nettoertrag von {net_ev:.2f} {claim_currency}. "
            f"Erfolgswahrscheinlichkeit {p_cash:.0%} liegt über der Schwelle von 35%."
        )
    elif net_ev > 0 and p_cash >= 0.20:
        recommendation = "riskant"
        reason = (
            f"Erwarteter Nettoertrag positiv ({net_ev:.2f} {claim_currency}), "
            f"aber Erfolgswahrscheinlichkeit ({p_cash:.0%}) ist grenzwertig."
        )
    elif net_ev > 0:
        recommendation = "riskant"
        reason = (
            f"Erwarteter Nettoertrag knapp positiv ({net_ev:.2f} {claim_currency}), "
            f"aber sehr niedrige Erfolgswahrscheinlichkeit ({p_cash:.0%})."
        )
    else:
        recommendation = "nicht empfohlen"
        reason = (
            f"Negativer erwarteter Nettoertrag ({net_ev:.2f} {claim_currency}). "
            f"Kosten übersteigen den erwarteten Ertrag bei {p_cash:.0%} Erfolgswahrscheinlichkeit."
        )

    return ExpectedValueResult(
        case_id=case_id,
        claim_amount=claim_amount,
        claim_currency=claim_currency,
        p_cash_success=round(p_cash, 4),
        expected_recovery=round(expected_recovery, 2),
        court_fees=round(court_fees, 2),
        service_fees=round(service_fees, 2),
        commission=round(commission, 2),
        net_expected_value=round(net_ev, 2),
        recommendation=recommendation,
        recommendation_reason=reason,
        breakdown={
            "formula": "net_ev = (claim_amount * p_cash_success) - commission - court_fees - service_fees",
            "p_cash_success": round(p_cash, 4),
            "expected_recovery_calc": f"{claim_amount} * {p_cash:.4f} = {expected_recovery:.2f}",
            "commission_rate": "30%",
            "commission_calc": f"{expected_recovery:.2f} * 0.30 = {commission:.2f}",
            "court_fees_country": court_country,
            "service_type": "cross_border" if is_cross_border else "domestic",
        },
    )
