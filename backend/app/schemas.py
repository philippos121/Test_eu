from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel

from .models import CaseEventType, CaseStatus, MessageRole


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
    is_admin: Optional[bool] = False
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


# --- Scoring ---

class CaseEventCreate(BaseModel):
    event_type: CaseEventType
    payload: dict = {}


class CaseEventRead(BaseModel):
    id: UUID
    case_id: UUID
    event_type: CaseEventType
    payload: dict
    created_at: datetime

    model_config = {"from_attributes": True}


class LLMTraceRead(BaseModel):
    id: UUID
    case_id: UUID
    question: str
    answer: Optional[str] = None
    extracted_facts: dict = {}
    step: Optional[CaseStatus] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ProcessScoreRead(BaseModel):
    id: UUID
    case_id: UUID
    # v3 pillars
    p_claim_valid: Optional[float] = None
    p_claim_provable: Optional[float] = None
    p_payment: Optional[float] = None
    legal_validity_json: Optional[dict] = None
    provability_json: Optional[dict] = None
    payment_analysis_json: Optional[dict] = None
    # Neural network component
    p_nn_prediction: Optional[float] = None
    nn_prediction_json: Optional[dict] = None
    # legacy / evidence
    evidence_score: float
    evidence_breakdown: dict
    ability_score: float
    ability_components: dict
    willingness_score: float
    willingness_components: dict
    p_served: float
    p_default: float
    p_win_contested: float
    p_settle: float
    p_collect: float
    p_cash_success: float
    priors_json: dict
    posteriors_json: dict
    observations_json: dict
    drivers_json: list
    model_version: str
    created_at: datetime

    model_config = {"from_attributes": True}


class PriorsConfigRead(BaseModel):
    id: UUID
    rate_name: str
    claim_subtype: str
    country: str
    alpha: float
    beta: float
    updated_at: datetime

    model_config = {"from_attributes": True}


class PriorsConfigCreate(BaseModel):
    rate_name: str
    claim_subtype: str = "general"
    country: str = "*"
    alpha: float = 2.0
    beta: float = 2.0


class PriorsConfigUpdate(BaseModel):
    alpha: Optional[float] = None
    beta: Optional[float] = None
    claim_subtype: Optional[str] = None
    country: Optional[str] = None


class AdminCaseListItem(BaseModel):
    id: UUID
    title: str
    status: CaseStatus
    claimant_name: Optional[str] = None
    defendant_name: Optional[str] = None
    claim_amount: Optional[float] = None
    claim_currency: Optional[str] = None
    success_probability: Optional[float] = None
    p_cash_success: Optional[float] = None
    created_at: datetime
    updated_at: datetime
    user_email: Optional[str] = None


# --- Statistics / Bayesian Learning ---

class CompletedCaseRead(BaseModel):
    """A completed case with its outcome summary."""
    id: UUID
    title: str
    status: CaseStatus
    claimant_name: Optional[str] = None
    defendant_name: Optional[str] = None
    claimant_country: Optional[str] = None
    defendant_country: Optional[str] = None
    claim_amount: Optional[float] = None
    claim_currency: Optional[str] = None
    outcome: str  # e.g. "full_payment", "partial_payment", "settled", "abandoned"
    events: list[CaseEventRead] = []
    p_cash_success: Optional[float] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class HistoricalAggregate(BaseModel):
    """Aggregate counts from historical completed cases."""
    total_cases: int
    served_success: int
    served_fail: int
    default_count: int
    responded_count: int
    settled_count: int
    judgment_win: int
    judgment_loss: int
    payment_received: int
    collection_failed: int


class StatisticsOverview(BaseModel):
    """Aggregate statistics for the admin dashboard."""
    total_completed_cases: int
    total_events: int
    outcome_distribution: dict  # e.g. {"full_payment": 5, "partial": 3, ...}
    rate_summaries: dict  # e.g. {"served": {"successes": 70, "trials": 100, "rate": 0.70}, ...}
    historical_cases_loaded: int
    current_priors: list[PriorsConfigRead] = []


# --- Neural Network ---

class NNModelRead(BaseModel):
    id: UUID
    version: int
    is_active: bool
    feature_names: list
    architecture: dict
    training_history: list
    feature_importance: list
    hyperparams: dict
    n_train_cases: int
    n_val_cases: int
    train_accuracy: Optional[float] = None
    val_accuracy: Optional[float] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class NNTrainRequest(BaseModel):
    epochs: int = 300
    lr: float = 0.005
    l2: float = 1e-4
    batch_size: int = 16


class NNTrainResponse(BaseModel):
    success: bool
    message: str
    version: Optional[int] = None
    n_train_cases: Optional[int] = None
    n_val_cases: Optional[int] = None
    train_accuracy: Optional[float] = None
    val_accuracy: Optional[float] = None
    history: Optional[list] = None
    feature_importance: Optional[list] = None


class NNCasePrediction(BaseModel):
    case_id: str
    case_title: str
    features: Optional[dict] = None
    p_nn: float
    actual_outcome: Optional[float] = None
    correct: Optional[bool] = None


class PriorUpdateResult(BaseModel):
    """Result of recalculating priors from completed case outcomes."""
    rates_updated: list[str]
    details: dict  # rate_name -> {old_alpha, old_beta, new_alpha, new_beta, observations}


class SeedResult(BaseModel):
    """Result of seeding demo data."""
    fictional_cases_created: int
    historical_aggregate_events_created: int
    message: str


class ExpectedValueResult(BaseModel):
    """Expected value calculation for a case — from the project owner's perspective.

    Formula:
      net_ev = p_win * 0.30 * claim_amount
             - service_fees
             - p_loss * (court_fees + attorney_costs + opponent_costs)
    """
    case_id: UUID
    claim_amount: float
    claim_currency: str
    p_win: float
    p_loss: float
    # Revenue
    expected_commission: float  # p_win * 30% * claim_amount
    # Cost components
    court_fees: float
    attorney_costs: float
    service_fees: float
    opponent_costs: float
    # Win scenario
    cost_compensation: float  # court_fees + attorney_costs recovered on win
    # Loss scenario
    expected_loss_costs: float  # p_loss * (court_fees + attorney_costs + opponent_costs)
    # Net
    net_expected_value: float
    # Decision
    recommendation: str  # "empfohlen" / "riskant" / "nicht empfohlen"
    recommendation_reason: str
    min_probability_threshold: float  # 80%
    breakdown: dict
