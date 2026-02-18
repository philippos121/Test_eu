import uuid
from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import (
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    Float,
    Boolean,
    text,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from .database import Base


class CaseStatus(str, PyEnum):
    INTAKE = "intake"
    APPLICABILITY_CHECK = "applicability_check"
    CASE_ASSESSMENT = "case_assessment"
    EVIDENCE_COLLECTION = "evidence_collection"
    FORM_GENERATION = "form_generation"
    COMPLETED = "completed"
    REJECTED = "rejected"


class MessageRole(str, PyEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class CaseEventType(str, PyEnum):
    FILED = "FILED"
    SERVICE_OK = "SERVICE_OK"
    SERVICE_FAIL = "SERVICE_FAIL"
    DEFENDANT_RESPONDED = "DEFENDANT_RESPONDED"
    DEFAULT = "DEFAULT"
    SETTLED = "SETTLED"
    JUDGMENT_WIN = "JUDGMENT_WIN"
    JUDGMENT_LOSS = "JUDGMENT_LOSS"
    PAYMENT_RECEIVED = "PAYMENT_RECEIVED"
    COLLECTION_FAILED = "COLLECTION_FAILED"


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(320), unique=True, nullable=False, index=True)
    hashed_password = Column(String(128), nullable=False)
    full_name = Column(String(256), nullable=False)
    language = Column(String(5), default="de")
    is_admin = Column(Boolean, default=False, server_default=text("false"))
    created_at = Column(DateTime, default=datetime.utcnow)

    cases = relationship("Case", back_populates="user", cascade="all, delete-orphan")


class Case(Base):
    __tablename__ = "cases"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    title = Column(String(512), nullable=False)
    status = Column(Enum(CaseStatus), default=CaseStatus.INTAKE, nullable=False)

    # --- Form A Section 1: Court/Tribunal ---
    court_name = Column(String(512))
    court_address = Column(Text)
    court_country = Column(String(2))

    # --- Form A Section 2: Claimant (Kläger) ---
    claimant_is_legal_person = Column(Boolean, default=False)
    claimant_name = Column(String(256))
    claimant_date_of_birth = Column(String(32))
    claimant_id_number = Column(String(128))
    claimant_address = Column(Text)
    claimant_city = Column(String(256))
    claimant_country = Column(String(2))
    claimant_phone = Column(String(64))
    claimant_fax = Column(String(64))
    claimant_email = Column(String(320))
    claimant_other = Column(Text)
    claimant_representative = Column(Text)

    # --- Form A Section 3: Defendant (Beklagter) ---
    defendant_is_legal_person = Column(Boolean, default=False)
    defendant_name = Column(String(256))
    defendant_date_of_birth = Column(String(32))
    defendant_id_number = Column(String(128))
    defendant_address = Column(Text)
    defendant_city = Column(String(256))
    defendant_country = Column(String(2))
    defendant_phone = Column(String(64))
    defendant_fax = Column(String(64))
    defendant_email = Column(String(320))
    defendant_other = Column(Text)
    defendant_representative = Column(Text)

    # --- Form A Section 4: Jurisdiction basis ---
    jurisdiction_basis = Column(String(64))
    jurisdiction_details = Column(Text)

    # --- Form A Section 5: Cross-border nature ---
    claimant_domicile_country = Column(String(2))
    defendant_domicile_country = Column(String(2))
    court_member_state = Column(String(2))
    is_cross_border = Column(Boolean, default=False)

    # --- Form A Section 6: Bank details ---
    bank_fee_payment_method = Column(Text)
    bank_account_holder = Column(String(256))
    bank_name_bic = Column(Text)
    bank_iban = Column(String(64))
    bank_account_details = Column(Text)

    # --- Form A Section 7: Claim ---
    claim_amount = Column(Float)
    claim_currency = Column(String(3), default="EUR")
    claim_non_monetary = Column(Text)
    claim_non_monetary_value = Column(Float)
    claim_non_monetary_currency = Column(String(3))
    claim_request_costs = Column(Boolean, default=False)
    claim_costs = Column(Text)
    claim_interest_rate = Column(Float)
    claim_interest_from_date = Column(String(32))
    claim_interest_to_date = Column(String(32))
    claim_interest_type = Column(String(32))
    claim_interest_on_costs = Column(Boolean, default=False)

    # --- Form A Section 8: Details of claim ---
    claim_description = Column(Text)
    claim_basis = Column(Text)
    claim_evidence = Column(Text)

    # --- Form A Section 9: Oral hearing ---
    request_oral_hearing = Column(Boolean, default=False)
    oral_hearing_reasons = Column(Text)
    request_personal_attendance = Column(Boolean, default=False)
    personal_attendance_reasons = Column(Text)

    # --- Form A Section 10: Electronic service ---
    consent_electronic_service = Column(Boolean, default=False)
    consent_electronic_communication = Column(Boolean, default=False)

    # --- Form A Section 11: Certificate for enforcement ---
    request_enforcement_certificate = Column(Boolean, default=True)
    certificate_language = Column(String(32))

    # --- Form A Section 12: Additional information ---
    additional_information = Column(Text)

    # --- Assessment fields ---
    applicability_result = Column(Text)
    success_probability = Column(Float)
    assessment_summary = Column(Text)
    applicable_law = Column(Text)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="cases")
    messages = relationship("ChatMessage", back_populates="case", cascade="all, delete-orphan", order_by="ChatMessage.created_at")
    documents = relationship("Document", back_populates="case", cascade="all, delete-orphan")
    events = relationship("CaseEvent", back_populates="case", cascade="all, delete-orphan", order_by="CaseEvent.created_at")
    llm_traces = relationship("CaseLLMTrace", back_populates="case", cascade="all, delete-orphan", order_by="CaseLLMTrace.created_at")
    process_scores = relationship("CaseProcessScore", back_populates="case", cascade="all, delete-orphan", order_by="CaseProcessScore.created_at.desc()")


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id = Column(UUID(as_uuid=True), ForeignKey("cases.id"), nullable=False)
    role = Column(Enum(MessageRole), nullable=False)
    content = Column(Text, nullable=False)
    step = Column(Enum(CaseStatus), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    case = relationship("Case", back_populates="messages")


class Document(Base):
    __tablename__ = "documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id = Column(UUID(as_uuid=True), ForeignKey("cases.id"), nullable=False)
    filename = Column(String(512), nullable=False)
    filepath = Column(String(1024), nullable=False)
    doc_type = Column(String(64), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    case = relationship("Case", back_populates="documents")


# --- New scoring models ---

class CaseEvent(Base):
    """Append-only event log for Bayes updates."""
    __tablename__ = "case_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id = Column(UUID(as_uuid=True), ForeignKey("cases.id"), nullable=False)
    event_type = Column(Enum(CaseEventType), nullable=False)
    payload = Column(JSONB, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)

    case = relationship("Case", back_populates="events")


class CaseLLMTrace(Base):
    """Store every LLM question + user answer + extracted facts."""
    __tablename__ = "case_llm_traces"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id = Column(UUID(as_uuid=True), ForeignKey("cases.id"), nullable=False)
    question = Column(Text, nullable=False)
    answer = Column(Text)
    extracted_facts = Column(JSONB, default=dict)
    step = Column(Enum(CaseStatus), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    case = relationship("Case", back_populates="llm_traces")


class CaseProcessScore(Base):
    """Computed process score snapshot."""
    __tablename__ = "case_process_scores"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id = Column(UUID(as_uuid=True), ForeignKey("cases.id"), nullable=False)

    # Evidence score (0..100) + breakdown
    evidence_score = Column(Float, default=0)
    evidence_breakdown = Column(JSONB, default=dict)

    # Ability score (0..100) + components
    ability_score = Column(Float, default=50)
    ability_components = Column(JSONB, default=dict)

    # Willingness score (0..100) + components
    willingness_score = Column(Float, default=50)
    willingness_components = Column(JSONB, default=dict)

    # 6 probabilities
    p_served = Column(Float, default=0.5)
    p_default = Column(Float, default=0.5)
    p_win_contested = Column(Float, default=0.5)
    p_settle = Column(Float, default=0.1)
    p_collect = Column(Float, default=0.5)
    p_cash_success = Column(Float, default=0.0)

    # Bayes data
    priors_json = Column(JSONB, default=dict)
    posteriors_json = Column(JSONB, default=dict)
    observations_json = Column(JSONB, default=dict)

    # Top-5 drivers
    drivers_json = Column(JSONB, default=list)

    model_version = Column(String(32), default="v1")
    created_at = Column(DateTime, default=datetime.utcnow)

    case = relationship("Case", back_populates="process_scores")


class PriorsConfig(Base):
    """Configurable Beta priors per rate, per claim_subtype + country."""
    __tablename__ = "priors_config"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    rate_name = Column(String(32), nullable=False)  # served, default, settle, collect
    claim_subtype = Column(String(64), default="general")
    country = Column(String(2), default="*")  # '*' = all countries
    alpha = Column(Float, nullable=False, default=2.0)
    beta = Column(Float, nullable=False, default=2.0)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
