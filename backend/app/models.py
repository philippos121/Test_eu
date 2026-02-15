import uuid
from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import (
    Column,
    DateTime,
    Enum,
    ForeignKey,
    String,
    Text,
    Float,
    Boolean,
)
from sqlalchemy.dialects.postgresql import UUID
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


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(320), unique=True, nullable=False, index=True)
    hashed_password = Column(String(128), nullable=False)
    full_name = Column(String(256), nullable=False)
    language = Column(String(5), default="de")
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
    claimant_is_legal_person = Column(Boolean, default=False)  # natural vs legal person
    claimant_name = Column(String(256))  # surname+first / entity name
    claimant_date_of_birth = Column(String(32))
    claimant_id_number = Column(String(128))  # Personal ID / passport / registration no.
    claimant_address = Column(Text)  # Street and number / PO box
    claimant_city = Column(String(256))  # City and postal code
    claimant_country = Column(String(2))
    claimant_phone = Column(String(64))
    claimant_fax = Column(String(64))
    claimant_email = Column(String(320))
    claimant_other = Column(Text)  # Other details
    claimant_representative = Column(Text)  # Section 2.2: Representative name + contact

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
    defendant_representative = Column(Text)  # Section 3.2

    # --- Form A Section 4: Jurisdiction basis (Brüssel-Ia-VO) ---
    # Official numbering per Delegated Regulation 2017/1259:
    # 4.1 Domicile of defendant
    # 4.2 Domicile of consumer (consumer contracts)
    # 4.3 Domicile of policyholder/insured/beneficiary (insurance)
    # 4.4 Place of performance of contractual obligation
    # 4.5 Place of harmful event (tort/delict)
    # 4.6 Place of immovable property
    # 4.7 Choice of court agreed by parties
    # 4.8 Other (specify)
    jurisdiction_basis = Column(String(64))  # e.g. "4.1", "4.7"
    jurisdiction_details = Column(Text)

    # --- Form A Section 5: Cross-border nature ---
    claimant_domicile_country = Column(String(2))  # 5.1
    defendant_domicile_country = Column(String(2))  # 5.2
    court_member_state = Column(String(2))  # 5.3
    is_cross_border = Column(Boolean, default=False)

    # --- Form A Section 6: Bank details (optional) ---
    bank_fee_payment_method = Column(Text)  # 6.1 How to pay court fees
    bank_account_holder = Column(String(256))  # 6.2.1 Kontoinhaber
    bank_name_bic = Column(Text)  # 6.2.2 Name der Bank, BIC
    bank_iban = Column(String(64))  # 6.2.3 Kontonummer/IBAN
    bank_account_details = Column(Text)  # 6.2 legacy / free text fallback

    # --- Form A Section 7: Claim ---
    claim_amount = Column(Float)  # 7.1 Monetary claim
    claim_currency = Column(String(3), default="EUR")
    claim_non_monetary = Column(Text)  # 7.2 Non-monetary claim description
    claim_non_monetary_value = Column(Float)  # 7.2.2 Estimated value
    claim_non_monetary_currency = Column(String(3))  # 7.2.2 Currency
    claim_request_costs = Column(Boolean, default=False)  # 7.3 Request cost reimbursement
    claim_costs = Column(Text)  # 7.3.3 Cost details
    claim_interest_rate = Column(Float)  # Interest rate
    claim_interest_from_date = Column(String(32))  # Date from which interest is claimed
    claim_interest_to_date = Column(String(32))  # Date to which interest is claimed
    claim_interest_type = Column(String(32))  # "contractual" or "statutory"
    claim_interest_on_costs = Column(Boolean, default=False)  # 7.5

    # --- Form A Section 8: Details of claim ---
    claim_description = Column(Text)  # 8.1 Substance of claim
    claim_basis = Column(Text)  # Legal basis of the claim
    claim_evidence = Column(Text)  # 8.2 Evidence / supporting documents

    # --- Form A Section 9: Oral hearing ---
    request_oral_hearing = Column(Boolean, default=False)
    oral_hearing_reasons = Column(Text)  # 9.1 reasons
    request_personal_attendance = Column(Boolean, default=False)  # 9.2
    personal_attendance_reasons = Column(Text)  # 9.2 reasons

    # --- Form A Section 10: Electronic service ---
    consent_electronic_service = Column(Boolean, default=False)  # 10.1
    consent_electronic_communication = Column(Boolean, default=False)  # 10.2

    # --- Form A Section 11: Certificate for enforcement ---
    request_enforcement_certificate = Column(Boolean, default=True)  # 11.1
    certificate_language = Column(String(32))  # 11.2 language for certificate

    # --- Form A Section 12: Additional information ---
    additional_information = Column(Text)

    # --- Assessment fields ---
    applicability_result = Column(Text)
    success_probability = Column(Float)  # 0.0 - 1.0
    assessment_summary = Column(Text)
    applicable_law = Column(Text)  # Determined applicable law (Rome I/II)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="cases")
    messages = relationship("ChatMessage", back_populates="case", cascade="all, delete-orphan", order_by="ChatMessage.created_at")
    documents = relationship("Document", back_populates="case", cascade="all, delete-orphan")


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
    doc_type = Column(String(64), nullable=False)  # form_a, form_c, etc.
    created_at = Column(DateTime, default=datetime.utcnow)

    case = relationship("Case", back_populates="documents")
