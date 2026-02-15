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
    # Section 1: Court
    court_name: Optional[str] = None
    court_address: Optional[str] = None
    court_country: Optional[str] = None
    # Section 2: Claimant
    claimant_is_legal_person: Optional[bool] = None
    claimant_name: Optional[str] = None
    claimant_date_of_birth: Optional[str] = None
    claimant_id_number: Optional[str] = None
    claimant_address: Optional[str] = None
    claimant_city: Optional[str] = None
    claimant_country: Optional[str] = None
    claimant_phone: Optional[str] = None
    claimant_fax: Optional[str] = None
    claimant_email: Optional[str] = None
    claimant_other: Optional[str] = None
    claimant_representative: Optional[str] = None
    # Section 3: Defendant
    defendant_is_legal_person: Optional[bool] = None
    defendant_name: Optional[str] = None
    defendant_date_of_birth: Optional[str] = None
    defendant_id_number: Optional[str] = None
    defendant_address: Optional[str] = None
    defendant_city: Optional[str] = None
    defendant_country: Optional[str] = None
    defendant_phone: Optional[str] = None
    defendant_fax: Optional[str] = None
    defendant_email: Optional[str] = None
    defendant_other: Optional[str] = None
    defendant_representative: Optional[str] = None
    # Section 4: Jurisdiction
    jurisdiction_basis: Optional[str] = None
    jurisdiction_details: Optional[str] = None
    # Section 5: Cross-border
    claimant_domicile_country: Optional[str] = None
    defendant_domicile_country: Optional[str] = None
    court_member_state: Optional[str] = None
    # Section 6: Bank
    bank_fee_payment_method: Optional[str] = None
    bank_account_holder: Optional[str] = None
    bank_name_bic: Optional[str] = None
    bank_iban: Optional[str] = None
    # Section 7: Claim
    claim_amount: Optional[float] = None
    claim_currency: Optional[str] = None
    claim_non_monetary: Optional[str] = None
    claim_non_monetary_value: Optional[float] = None
    claim_non_monetary_currency: Optional[str] = None
    claim_request_costs: Optional[bool] = None
    claim_costs: Optional[str] = None
    claim_interest_rate: Optional[float] = None
    claim_interest_from_date: Optional[str] = None
    claim_interest_to_date: Optional[str] = None
    claim_interest_type: Optional[str] = None
    claim_interest_on_costs: Optional[bool] = None
    # Section 8: Details
    claim_description: Optional[str] = None
    claim_basis: Optional[str] = None
    claim_evidence: Optional[str] = None
    # Section 9: Oral hearing
    request_oral_hearing: Optional[bool] = None
    oral_hearing_reasons: Optional[str] = None
    request_personal_attendance: Optional[bool] = None
    personal_attendance_reasons: Optional[str] = None
    # Section 10: Electronic service
    consent_electronic_service: Optional[bool] = None
    consent_electronic_communication: Optional[bool] = None
    # Section 11: Certificate
    request_enforcement_certificate: Optional[bool] = None
    certificate_language: Optional[str] = None
    # Section 12: Additional info
    additional_information: Optional[str] = None


class CaseRead(BaseModel):
    id: UUID
    title: str
    status: CaseStatus
    # Section 1
    court_name: Optional[str] = None
    court_address: Optional[str] = None
    court_country: Optional[str] = None
    # Section 2
    claimant_is_legal_person: Optional[bool] = None
    claimant_name: Optional[str] = None
    claimant_date_of_birth: Optional[str] = None
    claimant_id_number: Optional[str] = None
    claimant_address: Optional[str] = None
    claimant_city: Optional[str] = None
    claimant_country: Optional[str] = None
    claimant_phone: Optional[str] = None
    claimant_fax: Optional[str] = None
    claimant_email: Optional[str] = None
    claimant_other: Optional[str] = None
    claimant_representative: Optional[str] = None
    # Section 3
    defendant_is_legal_person: Optional[bool] = None
    defendant_name: Optional[str] = None
    defendant_date_of_birth: Optional[str] = None
    defendant_id_number: Optional[str] = None
    defendant_address: Optional[str] = None
    defendant_city: Optional[str] = None
    defendant_country: Optional[str] = None
    defendant_phone: Optional[str] = None
    defendant_fax: Optional[str] = None
    defendant_email: Optional[str] = None
    defendant_other: Optional[str] = None
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
    bank_account_holder: Optional[str] = None
    bank_name_bic: Optional[str] = None
    bank_iban: Optional[str] = None
    bank_account_details: Optional[str] = None
    # Section 7
    claim_amount: Optional[float] = None
    claim_currency: Optional[str] = None
    claim_non_monetary: Optional[str] = None
    claim_non_monetary_value: Optional[float] = None
    claim_non_monetary_currency: Optional[str] = None
    claim_request_costs: Optional[bool] = None
    claim_costs: Optional[str] = None
    claim_interest_rate: Optional[float] = None
    claim_interest_from_date: Optional[str] = None
    claim_interest_to_date: Optional[str] = None
    claim_interest_type: Optional[str] = None
    claim_interest_on_costs: Optional[bool] = None
    # Section 8
    claim_description: Optional[str] = None
    claim_basis: Optional[str] = None
    claim_evidence: Optional[str] = None
    # Section 9
    request_oral_hearing: Optional[bool] = None
    oral_hearing_reasons: Optional[str] = None
    request_personal_attendance: Optional[bool] = None
    personal_attendance_reasons: Optional[str] = None
    # Section 10
    consent_electronic_service: Optional[bool] = None
    consent_electronic_communication: Optional[bool] = None
    # Section 11
    request_enforcement_certificate: Optional[bool] = None
    certificate_language: Optional[str] = None
    # Section 12
    additional_information: Optional[str] = None
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
