from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import get_current_user
from ..database import get_db
from ..models import Case, CaseProcessScore, CaseStatus, ChatMessage, MessageRole, User
from ..schemas import CaseCreate, CaseRead, CaseUpdate, ProcessScoreRead
from ..services.llm_agent import get_initial_system_message

router = APIRouter(prefix="/api/cases", tags=["cases"])


@router.get("", response_model=List[CaseRead])
async def list_cases(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Case).where(Case.user_id == user.id).order_by(Case.updated_at.desc())
    )
    return result.scalars().all()


@router.post("", response_model=CaseRead, status_code=status.HTTP_201_CREATED)
async def create_case(
    body: CaseCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    case = Case(
        user_id=user.id,
        title=body.title,
        status=CaseStatus.INTAKE,
        claimant_name=user.full_name,
        claimant_email=user.email,
    )
    db.add(case)
    await db.flush()

    # Create initial system message
    system_msg = ChatMessage(
        case_id=case.id,
        role=MessageRole.SYSTEM,
        content=get_initial_system_message(),
        step=CaseStatus.INTAKE,
    )
    # Create initial assistant greeting
    greeting = ChatMessage(
        case_id=case.id,
        role=MessageRole.ASSISTANT,
        content=(
            "Willkommen beim EU-Bagatellverfahren-Assistenten! Ich werde Sie durch das "
            "Europäische Verfahren für geringfügige Forderungen (bis 5.000 €) gemäß der "
            "Verordnung (EG) Nr. 861/2007 begleiten.\n\n"
            "Zunächst muss ich prüfen, ob Ihr Fall für das EU-Bagatellverfahren geeignet ist. "
            "Bitte beantworten Sie mir dazu einige Fragen:\n\n"
            "1. **In welchem EU-Mitgliedstaat haben Sie Ihren Wohnsitz?**\n"
            "2. **In welchem EU-Mitgliedstaat hat der Schuldner/Beklagte seinen Sitz?**\n"
            "3. **Um welchen Betrag handelt es sich (in Euro)?**\n"
            "4. **Worum geht es bei Ihrer Forderung?** (z.B. unbezahlte Rechnung, "
            "mangelhafte Ware, nicht erbrachte Dienstleistung)"
        ),
        step=CaseStatus.INTAKE,
    )
    db.add_all([system_msg, greeting])
    await db.commit()
    await db.refresh(case)
    return case


@router.get("/{case_id}", response_model=CaseRead)
async def get_case(
    case_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Case).where(Case.id == case_id, Case.user_id == user.id)
    )
    case = result.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="Fall nicht gefunden.")
    return case


@router.patch("/{case_id}", response_model=CaseRead)
async def update_case(
    case_id: UUID,
    body: CaseUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Case).where(Case.id == case_id, Case.user_id == user.id)
    )
    case = result.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="Fall nicht gefunden.")

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(case, field, value)

    await db.commit()
    await db.refresh(case)
    return case


@router.get("/{case_id}/score", response_model=Optional[ProcessScoreRead])
async def get_case_score(
    case_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the latest process score for a user's case."""
    result = await db.execute(
        select(Case).where(Case.id == case_id, Case.user_id == user.id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Fall nicht gefunden.")

    result = await db.execute(
        select(CaseProcessScore)
        .where(CaseProcessScore.case_id == case_id)
        .order_by(CaseProcessScore.created_at.desc())
        .limit(1)
    )
    score = result.scalar_one_or_none()
    if not score:
        return None
    return score
