from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import get_current_user
from ..database import get_db
from ..models import Case, CaseLLMTrace, CaseStatus, ChatMessage, MessageRole, User
from ..schemas import ChatMessageCreate, ChatMessageRead, ChatResponse
from ..services.llm_agent import build_message_history, get_llm_response
from ..services.scoring import estimate

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

    # Write LLM trace for scoring pipeline — extract from structured data
    # AND from conversation text to capture willingness/ability signals
    extracted_facts = _extract_scoring_facts(
        update_data or {},
        user_text=body.content,
        assistant_text=response_text,
    )
    trace = CaseLLMTrace(
        case_id=case.id,
        question=body.content,
        answer=response_text,
        extracted_facts=extracted_facts,
        step=case.status,
    )
    db.add(trace)

    await db.commit()
    await db.refresh(case)
    await db.refresh(assistant_msg)

    # Auto-compute scoring on every chat interaction so users always see a score
    try:
        score_result = await estimate(case.id, db)
        # Sync the p_cash_success back to the case so the sidebar always shows it
        case.success_probability = score_result.p_cash_success
        await db.commit()
        await db.refresh(case)
    except Exception:
        pass  # scoring failure should not block chat

    return ChatResponse(
        message=ChatMessageRead.model_validate(assistant_msg),
        case=case,
    )


def _extract_scoring_facts(update_data: dict, user_text: str = "",
                           assistant_text: str = "") -> dict:
    """Map LLM update fields + conversation text to scoring-relevant fact flags.

    Extracts evidence, willingness, and ability signals from both
    structured update_data and free-text conversation content.
    """
    facts = {}

    desc = str(update_data.get("claim_description", "")).lower()
    evidence = str(update_data.get("claim_evidence", "")).lower()
    additional = str(update_data.get("additional_information", "")).lower()
    combined = desc + " " + evidence + " " + additional

    # Also scan user + assistant text for signals not in structured data
    conv_text = (user_text + " " + assistant_text).lower()
    all_text = combined + " " + conv_text

    # --- Evidence dimension ---
    if update_data.get("claim_basis"):
        facts["has_contract"] = True
    if any(kw in combined for kw in ["vertrag", "auftrag", "contract", "agreement", "schriftlich"]):
        facts["has_written_agreement"] = True
    if any(kw in combined for kw in ["geliefert", "erbracht", "delivered", "performed"]):
        facts["has_delivery_proof"] = True
    if any(kw in combined for kw in ["abgenommen", "accepted", "bestätigt"]):
        facts["has_acceptance"] = True
    if update_data.get("claim_interest_from_date"):
        facts["has_due_date"] = True
    if any(kw in combined for kw in ["mahnung", "reminder", "zahlungserinnerung"]):
        facts["has_dunning"] = True
        facts["has_reminder"] = True
    if any(kw in combined for kw in ["frist", "deadline"]):
        facts["has_deadline_set"] = True

    # --- Contestation signals ---
    if any(kw in combined for kw in ["nicht geliefert", "mangelhaft", "reklamation", "dispute"]):
        facts["defendant_disputes"] = True
    if any(kw in combined for kw in ["mangel", "defect", "quality"]):
        facts["quality_issue"] = True

    # --- Willingness dimension (from conversation + structured data) ---
    if any(kw in all_text for kw in ["teilzahlung", "partial payment", "anzahlung",
                                      "hat teilweise gezahlt", "teilbetrag"]):
        facts["partial_payment"] = True

    if any(kw in all_text for kw in ["vergleich angeboten", "vergleichsangebot",
                                      "settlement offer", "gütliche einigung",
                                      "einigung vorgeschlagen"]):
        facts["settlement_offered"] = True

    # Debtor responded to reminder (positive willingness signal)
    if any(kw in all_text for kw in ["hat auf mahnung reagiert", "hat geantwortet",
                                      "responded to reminder", "debtor responded",
                                      "schuldner hat reagiert"]):
        facts["responded_to_reminder"] = True

    # Debtor ignores reminders (negative willingness signal)
    if any(kw in all_text for kw in ["keine reaktion", "nicht reagiert",
                                      "ignoriert", "no response",
                                      "keine antwort", "unbeantwortet"]):
        facts["responded_to_reminder"] = False

    # Repeat offender
    if any(kw in all_text for kw in ["wiederholungstäter", "repeat offender",
                                      "bereits mehrfach", "schon wieder",
                                      "erneut nicht gezahlt", "mehrfach gemahnt"]):
        facts["repeat_defendant"] = True

    # --- Ability dimension (from conversation + structured data) ---
    if any(kw in all_text for kw in ["insolvent", "insolvenz", "insolvency",
                                      "bankrupt", "zahlungsunfähig",
                                      "insolvenzverfahren"]):
        facts["insolvency_flag"] = True

    if any(kw in all_text for kw in ["firma aufgelöst", "firma gelöscht",
                                      "company dissolved", "nicht mehr aktiv",
                                      "liquidiert", "liquidation",
                                      "betrieb eingestellt"]):
        facts["company_active"] = False

    return facts


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
    "bank_fee_payment_method", "bank_account_holder", "bank_name_bic",
    "bank_iban", "bank_account_details",
    # Section 7: Claim
    "claim_amount", "claim_currency", "claim_non_monetary",
    "claim_non_monetary_value", "claim_non_monetary_currency",
    "claim_request_costs", "claim_costs",
    "claim_interest_rate", "claim_interest_from_date", "claim_interest_to_date",
    "claim_interest_type", "claim_interest_on_costs",
    # Section 8: Details
    "claim_description", "claim_basis", "claim_evidence",
    # Section 9: Oral hearing
    "request_oral_hearing", "oral_hearing_reasons",
    "request_personal_attendance", "personal_attendance_reasons",
    # Section 10: Electronic service
    "consent_electronic_service", "consent_electronic_communication",
    # Section 11: Certificate
    "request_enforcement_certificate", "certificate_language",
    # Section 12: Additional info
    "additional_information",
    # Assessment
    "success_probability", "applicability_result", "assessment_summary", "applicable_law",
}

ALLOWED_STATUS_VALUES = {s.value for s in CaseStatus}


BOOLEAN_CASE_FIELDS = {
    "is_cross_border", "claimant_is_legal_person", "defendant_is_legal_person",
    "request_oral_hearing", "request_personal_attendance",
    "claim_request_costs", "claim_interest_on_costs",
    "consent_electronic_service", "consent_electronic_communication",
    "request_enforcement_certificate",
}


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
