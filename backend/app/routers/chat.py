from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..auth import get_current_user
from ..database import get_db
from ..models import Case, CaseStatus, ChatMessage, MessageRole, User
from ..schemas import ChatMessageCreate, ChatMessageRead, ChatResponse
from ..services.llm_agent import build_message_history, get_llm_response

router = APIRouter(prefix="/api/cases/{case_id}/chat", tags=["chat"])


@router.get("", response_model=List[ChatMessageRead])
async def get_messages(
    case_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Verify ownership
    result = await db.execute(
        select(Case).where(Case.id == case_id, Case.user_id == user.id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Fall nicht gefunden.")

    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.case_id == case_id, ChatMessage.role != MessageRole.SYSTEM)
        .order_by(ChatMessage.created_at)
    )
    return result.scalars().all()


@router.post("", response_model=ChatResponse)
async def send_message(
    case_id: UUID,
    body: ChatMessageCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Load case
    result = await db.execute(
        select(Case).where(Case.id == case_id, Case.user_id == user.id)
    )
    case = result.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="Fall nicht gefunden.")

    if case.status in (CaseStatus.COMPLETED, CaseStatus.REJECTED):
        raise HTTPException(
            status_code=400,
            detail="Dieser Fall ist bereits abgeschlossen.",
        )

    # Save user message
    user_msg = ChatMessage(
        case_id=case.id,
        role=MessageRole.USER,
        content=body.content,
        step=case.status,
    )
    db.add(user_msg)
    await db.flush()

    # Load full chat history
    msg_result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.case_id == case_id)
        .order_by(ChatMessage.created_at)
    )
    all_messages = msg_result.scalars().all()

    # Build messages for LLM
    llm_messages = build_message_history(all_messages, case)

    # Get LLM response
    response_text, update_data = await get_llm_response(llm_messages, case)

    # Apply updates to case if any
    if update_data:
        _apply_case_updates(case, update_data)

    # Save assistant message
    assistant_msg = ChatMessage(
        case_id=case.id,
        role=MessageRole.ASSISTANT,
        content=response_text,
        step=case.status,
    )
    db.add(assistant_msg)
    await db.commit()
    await db.refresh(case)
    await db.refresh(assistant_msg)

    return ChatResponse(
        message=ChatMessageRead.model_validate(assistant_msg),
        case=case,
    )


ALLOWED_CASE_FIELDS = {
    # Section 1: Court
    "court_name", "court_address", "court_country",
    # Section 2: Claimant
    "claimant_is_legal_person", "claimant_name", "claimant_date_of_birth",
    "claimant_id_number", "claimant_address", "claimant_city",
    "claimant_country", "claimant_phone", "claimant_fax", "claimant_email",
    "claimant_other", "claimant_representative",
    # Section 3: Defendant
    "defendant_is_legal_person", "defendant_name", "defendant_date_of_birth",
    "defendant_id_number", "defendant_address", "defendant_city",
    "defendant_country", "defendant_phone", "defendant_fax", "defendant_email",
    "defendant_other", "defendant_representative",
    # Section 4: Jurisdiction
    "jurisdiction_basis", "jurisdiction_details",
    # Section 5: Cross-border
    "claimant_domicile_country", "defendant_domicile_country", "court_member_state",
    "is_cross_border",
    # Section 6: Bank
    "bank_fee_payment_method", "bank_account_details",
    # Section 7: Claim
    "claim_amount", "claim_currency", "claim_non_monetary", "claim_costs",
    "claim_interest_rate", "claim_interest_from_date", "claim_interest_type",
    # Section 8: Details
    "claim_description", "claim_basis", "claim_evidence",
    # Section 9: Oral hearing
    "request_oral_hearing",
    # Section 10: Certificate
    "request_enforcement_certificate",
    # Section 12: Additional info
    "additional_information",
    # Assessment
    "success_probability", "applicability_result", "assessment_summary", "applicable_law",
}

ALLOWED_STATUS_VALUES = {s.value for s in CaseStatus}


BOOLEAN_CASE_FIELDS = {"is_cross_border", "request_oral_hearing", "request_enforcement_certificate"}


def _apply_case_updates(case: Case, updates: dict):
    """Apply validated updates from LLM extraction to case."""
    for key, value in updates.items():
        if key == "status" and value in ALLOWED_STATUS_VALUES:
            case.status = CaseStatus(value)
        elif key in ALLOWED_CASE_FIELDS:
            # Coerce types to match DB column expectations
            if key in BOOLEAN_CASE_FIELDS:
                value = bool(value)
            elif isinstance(value, bool):
                # Text column got a bool from LLM — convert
                value = None if not value else str(value)
            setattr(case, key, value)
