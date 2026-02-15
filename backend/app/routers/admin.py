"""Admin API – scoring dashboard, events, LLM traces, priors CRUD."""
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..auth import get_current_user
from ..database import get_db
from ..models import (
    Case,
    CaseEvent,
    CaseLLMTrace,
    CaseProcessScore,
    PriorsConfig,
    User,
)
from ..schemas import (
    AdminCaseListItem,
    CaseEventCreate,
    CaseEventRead,
    CaseRead,
    LLMTraceRead,
    PriorsConfigCreate,
    PriorsConfigRead,
    PriorsConfigUpdate,
    ProcessScoreRead,
)
from ..services.scoring import estimate

router = APIRouter(prefix="/api/admin", tags=["admin"])


# --- Helpers ---

async def _require_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Nur für Administratoren.")
    return user


# --- Cases list (admin sees all) ---

@router.get("/cases", response_model=List[AdminCaseListItem])
async def admin_list_cases(
    admin: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Case, User.email)
        .join(User, Case.user_id == User.id)
        .order_by(Case.updated_at.desc())
    )
    rows = result.all()

    items = []
    for case, user_email in rows:
        # Get latest process score p_cash_success
        score_result = await db.execute(
            select(CaseProcessScore.p_cash_success)
            .where(CaseProcessScore.case_id == case.id)
            .order_by(CaseProcessScore.created_at.desc())
            .limit(1)
        )
        p_cash = score_result.scalar_one_or_none()

        items.append(AdminCaseListItem(
            id=case.id,
            title=case.title,
            status=case.status,
            claimant_name=case.claimant_name,
            defendant_name=case.defendant_name,
            claim_amount=case.claim_amount,
            claim_currency=case.claim_currency,
            success_probability=case.success_probability,
            p_cash_success=p_cash,
            created_at=case.created_at,
            updated_at=case.updated_at,
            user_email=user_email,
        ))
    return items


# --- Case detail (admin) ---

@router.get("/cases/{case_id}", response_model=CaseRead)
async def admin_get_case(
    case_id: UUID,
    admin: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Case).where(Case.id == case_id))
    case = result.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="Fall nicht gefunden.")
    return case


# --- Process Score ---

@router.get("/cases/{case_id}/score", response_model=ProcessScoreRead)
async def get_process_score(
    case_id: UUID,
    admin: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get the latest process score for a case."""
    result = await db.execute(
        select(CaseProcessScore)
        .where(CaseProcessScore.case_id == case_id)
        .order_by(CaseProcessScore.created_at.desc())
        .limit(1)
    )
    score = result.scalar_one_or_none()
    if not score:
        raise HTTPException(status_code=404, detail="Kein Score vorhanden. Erst berechnen.")
    return score


@router.post("/cases/{case_id}/score", response_model=ProcessScoreRead, status_code=201)
async def compute_process_score(
    case_id: UUID,
    admin: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    """(Re-)compute the process score for a case."""
    # Verify case exists
    result = await db.execute(select(Case).where(Case.id == case_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Fall nicht gefunden.")

    score = await estimate(case_id, db)
    await db.commit()
    return score


@router.get("/cases/{case_id}/score/history", response_model=List[ProcessScoreRead])
async def get_score_history(
    case_id: UUID,
    admin: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(CaseProcessScore)
        .where(CaseProcessScore.case_id == case_id)
        .order_by(CaseProcessScore.created_at.desc())
    )
    return result.scalars().all()


# --- Events ---

@router.get("/cases/{case_id}/events", response_model=List[CaseEventRead])
async def list_events(
    case_id: UUID,
    admin: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(CaseEvent)
        .where(CaseEvent.case_id == case_id)
        .order_by(CaseEvent.created_at)
    )
    return result.scalars().all()


@router.post("/cases/{case_id}/events", response_model=CaseEventRead, status_code=201)
async def add_event(
    case_id: UUID,
    body: CaseEventCreate,
    admin: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    # Verify case
    result = await db.execute(select(Case).where(Case.id == case_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Fall nicht gefunden.")

    event = CaseEvent(
        case_id=case_id,
        event_type=body.event_type,
        payload=body.payload,
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)
    return event


# --- LLM Traces ---

@router.get("/cases/{case_id}/traces", response_model=List[LLMTraceRead])
async def list_traces(
    case_id: UUID,
    admin: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(CaseLLMTrace)
        .where(CaseLLMTrace.case_id == case_id)
        .order_by(CaseLLMTrace.created_at)
    )
    return result.scalars().all()


# --- Priors Config CRUD ---

@router.get("/priors", response_model=List[PriorsConfigRead])
async def list_priors(
    admin: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PriorsConfig).order_by(PriorsConfig.rate_name, PriorsConfig.claim_subtype)
    )
    return result.scalars().all()


@router.post("/priors", response_model=PriorsConfigRead, status_code=201)
async def create_prior(
    body: PriorsConfigCreate,
    admin: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    prior = PriorsConfig(
        rate_name=body.rate_name,
        claim_subtype=body.claim_subtype,
        country=body.country,
        alpha=body.alpha,
        beta=body.beta,
    )
    db.add(prior)
    await db.commit()
    await db.refresh(prior)
    return prior


@router.put("/priors/{prior_id}", response_model=PriorsConfigRead)
async def update_prior(
    prior_id: UUID,
    body: PriorsConfigUpdate,
    admin: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(PriorsConfig).where(PriorsConfig.id == prior_id))
    prior = result.scalar_one_or_none()
    if not prior:
        raise HTTPException(status_code=404, detail="Prior nicht gefunden.")

    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(prior, key, value)

    await db.commit()
    await db.refresh(prior)
    return prior


@router.delete("/priors/{prior_id}", status_code=204)
async def delete_prior(
    prior_id: UUID,
    admin: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(PriorsConfig).where(PriorsConfig.id == prior_id))
    prior = result.scalar_one_or_none()
    if not prior:
        raise HTTPException(status_code=404, detail="Prior nicht gefunden.")

    await db.delete(prior)
    await db.commit()
