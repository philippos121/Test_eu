"""Pydantic models for the EU Small Claims scoring pipeline v3."""
from __future__ import annotations

from enum import Enum
from typing import Any, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ClaimType(str, Enum):
    INVOICE = "invoice"           # Kaufpreis / Warenlieferung
    WERKLOHN = "werklohn"         # Werkvertrag / Dienstleistung
    REFUND = "refund"             # Rückforderung
    DAMAGES = "damages"           # Schadensersatz
    UNJUST_ENRICHMENT = "unjust_enrichment"
    OTHER = "other"


class YesNoUnknown(str, Enum):
    YES = "yes"
    NO = "no"
    UNKNOWN = "unknown"


class PerformanceStatus(str, Enum):
    YES = "yes"
    NO = "no"
    PARTIAL = "partial"
    UNKNOWN = "unknown"


class DefenseType(str, Enum):
    NONE = "none"
    MANGEL = "mangel"               # Defect / quality dispute
    AUFRECHNUNG = "aufrechnung"     # Set-off
    RUECKTRITT = "ruecktritt"       # Withdrawal
    VERJAEHRUNG = "verjaehrung"     # Limitation
    ZUSTAENDIGKEIT = "zustaendigkeit"  # Jurisdiction
    OTHER = "other"


class ExtinguishedStatus(str, Enum):
    FULLY_PAID = "fully_paid"
    PARTLY_PAID = "partly_paid"
    SETTLEMENT = "settlement"
    RELEASE = "release"
    NO = "no"
    UNKNOWN = "unknown"


class EvidenceType(str, Enum):
    WRITTEN_CONTRACT = "written_contract"
    EMAIL_CHAIN = "email_chain"
    INVOICE = "invoice"
    DELIVERY_NOTE = "delivery_note"
    TRACKING = "tracking"
    ACCEPTANCE_PROTOCOL = "acceptance_protocol"
    MESSAGES = "messages"
    WITNESS_STATEMENT = "witness_statement"
    BANK_RECORD = "bank_record"
    EXPERT_REPORT = "expert_report"
    OTHER = "other"


class DebtorType(str, Enum):
    PRIVATE = "private"
    COMPANY = "company"


class EnforcementComplexity(str, Enum):
    SAME_COUNTRY = "same_country"
    CROSS_BORDER_EU = "cross_border_eu"
    CROSS_BORDER_NON_EU = "cross_border_non_eu"


class CaseOutcome(str, Enum):
    WON = "won"
    LOST = "lost"
    SETTLED = "settled"
    WITHDRAWN = "withdrawn"


class InsolvencyStatus(str, Enum):
    SOLVENT = "solvent"
    INSOLVENT = "insolvent"
    UNKNOWN = "unknown"
    CHECK_PENDING = "check_pending"


# ---------------------------------------------------------------------------
# Input Models
# ---------------------------------------------------------------------------

class Allegations(BaseModel):
    """Nur Vorbringen, keine Beweis-Indizien — verhindert Doppelzählung."""
    contract_formed_alleged: YesNoUnknown = YesNoUnknown.UNKNOWN
    contract_details: str = ""
    performance_done_alleged: PerformanceStatus = PerformanceStatus.UNKNOWN
    amount_due_alleged: YesNoUnknown = YesNoUnknown.UNKNOWN
    amount_basis: str = ""
    due_date_alleged: YesNoUnknown = YesNoUnknown.UNKNOWN
    non_payment_alleged: YesNoUnknown = YesNoUnknown.UNKNOWN
    defenses_known: DefenseType = DefenseType.NONE
    defense_details: str = ""
    claim_extinguished_alleged: ExtinguishedStatus = ExtinguishedStatus.NO
    # Enforceability flags
    standing_risk: YesNoUnknown = YesNoUnknown.NO
    wrong_defendant_risk: YesNoUnknown = YesNoUnknown.NO
    limitation_risk: YesNoUnknown = YesNoUnknown.NO
    jurisdiction_risk: YesNoUnknown = YesNoUnknown.NO
    # Alternative legal basis
    unjust_enrichment_alleged: YesNoUnknown = YesNoUnknown.NO


class CaseInput(BaseModel):
    case_id: UUID = Field(default_factory=uuid4)
    claim_type: ClaimType = ClaimType.INVOICE
    claim_amount: float = 0.0
    currency: str = "EUR"
    court_country: str = "DE"       # EU member state ISO-2
    debtor_country: str = "DE"
    creditor_country: str = "DE"
    applicable_law_country: Optional[str] = None  # if absent: heuristic
    debtor_is_consumer: bool = False
    creditor_is_consumer: bool = False
    # Timeline
    contract_date: Optional[str] = None
    performance_date: Optional[str] = None
    invoice_date: Optional[str] = None
    due_date: Optional[str] = None
    reminder_dates: list[str] = Field(default_factory=list)
    # Allegations
    allegations: Allegations = Field(default_factory=Allegations)


class EvidenceItem(BaseModel):
    type: EvidenceType = EvidenceType.OTHER
    description: str = ""
    date: Optional[str] = None
    amount: Optional[float] = None
    parties: str = ""
    signed_or_attributable: bool = False
    authenticity_concern: bool = False
    strength_rating: int = Field(default=3, ge=1, le=5)


class RecoveryInput(BaseModel):
    debtor_name: str = ""
    debtor_address: str = ""
    address_quality: str = "medium"  # low/medium/high
    company_id: Optional[str] = None  # VAT / registration number
    debtor_type: DebtorType = DebtorType.COMPANY
    known_assets_or_income: YesNoUnknown = YesNoUnknown.UNKNOWN
    payment_history: str = "unknown"  # good/bad/unknown
    prior_dunning: bool = False
    debtor_disputes: bool = False
    enforcement_complexity: EnforcementComplexity = EnforcementComplexity.SAME_COUNTRY
    known_bank_account: bool = False
    known_employer_or_income_source: bool = False
    costs_sensitivity: str = "medium"  # low/medium/high


class CostModelParams(BaseModel):
    fee_rate: float = 0.30
    costs_fixed: float = 0.0
    costs_filing: float = 35.0
    costs_service: float = 75.0
    costs_translation: float = 0.0
    costs_attorney: float = 0.0
    costs_enforcement: float = 50.0
    expected_cost_compensation_win: float = 0.0
    expected_loss_costs_total: float = 200.0
    take_case_requires_pwin_80: bool = True
    require_ev_positive: bool = True
    p_win_min: float = 0.80


class ClosedCaseFeedback(BaseModel):
    outcome: CaseOutcome
    reason_label: Optional[str] = None  # noisy: unschluessig_recht, contract_not_proven, etc.
    reason_confidence: float = 0.7
    court_country: str = "DE"
    applicable_law_country: Optional[str] = None
    claim_type: ClaimType = ClaimType.INVOICE
    is_b2b: bool = True
    decision_date: Optional[str] = None


# ---------------------------------------------------------------------------
# Output / Result Models
# ---------------------------------------------------------------------------

class SourceRef(BaseModel):
    url: str
    title: str = ""
    snippet: str = ""
    fetched_at: str = ""
    domain: str = ""


class ApplicableLawDecision(BaseModel):
    country: str
    method: str = "explicit"  # explicit / heuristic_court / heuristic_rome_i
    confidence: float = 1.0
    notes: str = ""
    sources: list[SourceRef] = Field(default_factory=list)


class LegalElement(BaseModel):
    name: str
    description: str = ""
    required: bool = True
    fulfilled_from_allegations: Optional[bool] = None


class LegalBasis(BaseModel):
    name: str
    statute: str = ""
    elements: list[LegalElement] = Field(default_factory=list)
    match_score: float = 0.0


class LegalResearchResult(BaseModel):
    claim_type: str
    law_country: str
    ranked_legal_bases: list[LegalBasis] = Field(default_factory=list)
    defenses: list[str] = Field(default_factory=list)
    limitation_notes: str = ""
    sources: list[SourceRef] = Field(default_factory=list)
    research_status: str = "complete"  # complete / partial / insufficient
    research_warnings: list[str] = Field(default_factory=list)


class GateResult(BaseModel):
    is_hard_exclusion: bool = False
    hard_reason: str = ""
    is_soft_incomplete: bool = False
    missing_fields: list[str] = Field(default_factory=list)
    soft_cap: Optional[float] = None  # e.g. 0.20 if soft gate applies


class MeritsResult(BaseModel):
    """p_recht computation result."""
    p_entstanden: float = 0.5
    p_nicht_untergegangen: float = 1.0
    p_durchsetzbar: float = 1.0
    p_recht: float = 0.5
    confidence: float = 0.5
    gate: GateResult = Field(default_factory=GateResult)
    legal_research: Optional[LegalResearchResult] = None
    applicable_law: Optional[ApplicableLawDecision] = None
    reasoning: list[str] = Field(default_factory=list)


class ProofResult(BaseModel):
    """p_beweis computation result."""
    element_scores: dict[str, float] = Field(default_factory=dict)
    p_beweis: float = 0.5
    confidence: float = 0.5
    missing_evidence: list[str] = Field(default_factory=list)
    reasoning: list[str] = Field(default_factory=list)


class RecoverySignal(BaseModel):
    signal_type: str  # insolvency_register / web_signal / payment_history
    value: str
    confidence: float = 0.5
    source: Optional[SourceRef] = None


class RecoveryResult(BaseModel):
    """p_eintreibung computation result."""
    insolvency_status: InsolvencyStatus = InsolvencyStatus.CHECK_PENDING
    signals: list[RecoverySignal] = Field(default_factory=list)
    p_eintreibung: Optional[float] = None  # None if checks pending
    uncertainty_band: Optional[tuple[float, float]] = None
    ampel: str = "pending"  # green / yellow / red / pending
    pending_external_checks: bool = True
    reasoning: list[str] = Field(default_factory=list)


class EVResult(BaseModel):
    """Expected value for the platform operator."""
    p_win: float
    expected_revenue: float
    expected_cost_compensation: float
    expected_costs: float
    expected_loss_costs: float
    ev_betreiber: float
    take_case: bool
    take_case_reason: str = ""
    breakdown: dict[str, Any] = Field(default_factory=dict)


class EstimateResult(BaseModel):
    """Full pipeline result."""
    case_id: UUID
    # Tier 1: Legal merit
    p_recht: float = 0.0
    merits: MeritsResult = Field(default_factory=MeritsResult)
    # Tier 2: Evidence
    p_beweis: float = 0.0
    proof: ProofResult = Field(default_factory=ProofResult)
    # Combined
    p_obsiegen: float = 0.0
    # Tier 3: Recovery
    p_eintreibung: Optional[float] = None
    recovery: RecoveryResult = Field(default_factory=RecoveryResult)
    # Overall
    p_gesamt: Optional[float] = None
    # EV
    ev: Optional[EVResult] = None
    # Meta
    warnings: list[str] = Field(default_factory=list)
    sources: list[SourceRef] = Field(default_factory=list)
    model_version: str = "v3"


class LearningParams(BaseModel):
    """Stored parameters for Bayesian learning."""
    # Per (claim_type, law_country, b2b) context cell
    context_key: str  # e.g. "invoice:DE:b2b"
    # Element-level Beta priors: element_name -> (alpha, beta)
    element_priors: dict[str, tuple[float, float]] = Field(default_factory=dict)
    # Conditional priors: "element:condition" -> (alpha, beta)
    conditional_priors: dict[str, tuple[float, float]] = Field(default_factory=dict)
    # Global fallback weights
    global_weights: dict[str, float] = Field(default_factory=dict)
    # Number of observations in this cell
    n_observations: int = 0
    updated_at: str = ""
