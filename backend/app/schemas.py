from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel

from .models import CaseStatus, MessageRole


# --- Auth ---

class UserCreate(BaseModel):
    email: str
    password: str
    full_name: str
    language: str = "de"


class UserRead(BaseModel):
    id: UUID
    email: str
    full_name: str
    language: str
    created_at: datetime

    model_config = {"from_attributes": True}


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenPayload(BaseModel):
    sub: str


# --- Cases ---

class CaseCreate(BaseModel):
    title: str


class CaseUpdate(BaseModel):
    title: Optional[str] = None
    # Section 1
    court_name: Optional[str] = None
    court_address: Optional[str] = None
    court_country: Optional[str] = None
    # Section 2
    claimant_name: Optional[str] = None
    claimant_id_number: Optional[str] = None
    claimant_address: Optional[str] = None
    claimant_city: Optional[str] = None
    claimant_country: Optional[str] = None
    claimant_phone: Optional[str] = None
    claimant_email: Optional[str] = None
    claimant_representative: Optional[str] = None
    # Section 3
    defendant_name: Optional[str] = None
    defendant_id_number: Optional[str] = None
    defendant_address: Optional[str] = None
    defendant_city: Optional[str] = None
    defendant_country: Optional[str] = None
    defendant_phone: Optional[str] = None
    defendant_email: Optional[str] = None
    defendant_representative: Optional[str] = None
    # Section 4
    jurisdiction_basis: Optional[str] = None
    jurisdiction_details: Optional[str] = None
    # Section 5
    claimant_domicile_country: Optional[str] = None
    defendant_domicile_country: Optional[str] = None
    court_member_state: Optional[str] = None
    # Section 7
    claim_amount: Optional[float] = None
    claim_currency: Optional[str] = None
    claim_non_monetary: Optional[str] = None
    claim_costs: Optional[str] = None
    claim_interest_rate: Optional[float] = None
    claim_interest_from_date: Optional[str] = None
    claim_interest_type: Optional[str] = None
    # Section 8
    claim_description: Optional[str] = None
    claim_basis: Optional[str] = None
    claim_evidence: Optional[str] = None
    request_oral_hearing: Optional[bool] = None


class CaseRead(BaseModel):
    id: UUID
    title: str
    status: CaseStatus
    # Section 1
    court_name: Optional[str] = None
    court_address: Optional[str] = None
    court_country: Optional[str] = None
    # Section 2
    claimant_name: Optional[str] = None
    claimant_id_number: Optional[str] = None
    claimant_address: Optional[str] = None
    claimant_city: Optional[str] = None
    claimant_country: Optional[str] = None
    claimant_phone: Optional[str] = None
    claimant_email: Optional[str] = None
    claimant_representative: Optional[str] = None
    # Section 3
    defendant_name: Optional[str] = None
    defendant_id_number: Optional[str] = None
    defendant_address: Optional[str] = None
    defendant_city: Optional[str] = None
    defendant_country: Optional[str] = None
    defendant_phone: Optional[str] = None
    defendant_email: Optional[str] = None
    defendant_representative: Optional[str] = None
    # Section 4
    jurisdiction_basis: Optional[str] = None
    jurisdiction_details: Optional[str] = None
    # Section 5
    claimant_domicile_country: Optional[str] = None
    defendant_domicile_country: Optional[str] = None
    court_member_state: Optional[str] = None
    is_cross_border: Optional[bool] = None
    # Section 6
    bank_fee_payment_method: Optional[str] = None
    bank_account_details: Optional[str] = None
    # Section 7
    claim_amount: Optional[float] = None
    claim_currency: Optional[str] = None
    claim_non_monetary: Optional[str] = None
    claim_costs: Optional[str] = None
    claim_interest_rate: Optional[float] = None
    claim_interest_from_date: Optional[str] = None
    claim_interest_type: Optional[str] = None
    # Section 8
    claim_description: Optional[str] = None
    claim_basis: Optional[str] = None
    claim_evidence: Optional[str] = None
    request_oral_hearing: Optional[bool] = None
    # Section 9
    request_enforcement_certificate: Optional[bool] = None
    # Assessment
    applicability_result: Optional[str] = None
    success_probability: Optional[float] = None
    assessment_summary: Optional[str] = None
    applicable_law: Optional[str] = None
    # Timestamps
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# --- Chat ---

class ChatMessageCreate(BaseModel):
    content: str


class ChatMessageRead(BaseModel):
    id: UUID
    role: MessageRole
    content: str
    step: Optional[CaseStatus] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ChatResponse(BaseModel):
    message: ChatMessageRead
    case: CaseRead


# --- Documents ---

class DocumentRead(BaseModel):
    id: UUID
    filename: str
    doc_type: str
    created_at: datetime

    model_config = {"from_attributes": True}
