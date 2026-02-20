enum CaseStatus {
  intake,
  applicabilityCheck,
  caseAssessment,
  evidenceCollection,
  formGeneration,
  completed,
  rejected;

  static CaseStatus fromString(String s) {
    const map = {
      'intake': CaseStatus.intake,
      'applicability_check': CaseStatus.applicabilityCheck,
      'case_assessment': CaseStatus.caseAssessment,
      'evidence_collection': CaseStatus.evidenceCollection,
      'form_generation': CaseStatus.formGeneration,
      'completed': CaseStatus.completed,
      'rejected': CaseStatus.rejected,
    };
    return map[s] ?? CaseStatus.intake;
  }

  String get label {
    const labels = {
      CaseStatus.intake: 'Aufnahme',
      CaseStatus.applicabilityCheck: 'Anwendbarkeit',
      CaseStatus.caseAssessment: 'Fallprüfung',
      CaseStatus.evidenceCollection: 'Beweisaufnahme',
      CaseStatus.formGeneration: 'Formular',
      CaseStatus.completed: 'Abgeschlossen',
      CaseStatus.rejected: 'Abgelehnt',
    };
    return labels[this] ?? toString();
  }

  int get stepIndex {
    const steps = [
      CaseStatus.intake,
      CaseStatus.applicabilityCheck,
      CaseStatus.caseAssessment,
      CaseStatus.evidenceCollection,
      CaseStatus.formGeneration,
      CaseStatus.completed,
    ];
    return steps.indexOf(this);
  }

  bool get isTerminal => this == CaseStatus.completed || this == CaseStatus.rejected;
  bool get canChat => !isTerminal;
}

class Case {
  final String id;
  final String title;
  final CaseStatus status;

  // Claimant
  final String? claimantName;
  final String? claimantEmail;
  final String? claimantCountry;
  final bool? claimantIsLegalPerson;

  // Defendant
  final String? defendantName;
  final String? defendantCountry;
  final bool? defendantIsLegalPerson;

  // Claim
  final double? claimAmount;
  final String? claimCurrency;
  final String? claimDescription;
  final String? claimEvidence;
  final String? claimBasis;

  // Scoring
  final double? successProbability;
  final double? pCashSuccess;

  // Metadata
  final DateTime createdAt;
  final DateTime updatedAt;

  // Assessment
  final String? applicabilityResult;
  final String? assessmentSummary;

  // Cross-border
  final bool? isCrossBorder;
  final String? claimantDomicileCountry;
  final String? defendantDomicileCountry;

  const Case({
    required this.id,
    required this.title,
    required this.status,
    this.claimantName,
    this.claimantEmail,
    this.claimantCountry,
    this.claimantIsLegalPerson,
    this.defendantName,
    this.defendantCountry,
    this.defendantIsLegalPerson,
    this.claimAmount,
    this.claimCurrency,
    this.claimDescription,
    this.claimEvidence,
    this.claimBasis,
    this.successProbability,
    this.pCashSuccess,
    required this.createdAt,
    required this.updatedAt,
    this.applicabilityResult,
    this.assessmentSummary,
    this.isCrossBorder,
    this.claimantDomicileCountry,
    this.defendantDomicileCountry,
  });

  factory Case.fromJson(Map<String, dynamic> j) => Case(
        id: j['id'] as String,
        title: j['title'] as String,
        status: CaseStatus.fromString(j['status'] as String),
        claimantName: j['claimant_name'] as String?,
        claimantEmail: j['claimant_email'] as String?,
        claimantCountry: j['claimant_country'] as String?,
        claimantIsLegalPerson: j['claimant_is_legal_person'] as bool?,
        defendantName: j['defendant_name'] as String?,
        defendantCountry: j['defendant_country'] as String?,
        defendantIsLegalPerson: j['defendant_is_legal_person'] as bool?,
        claimAmount: (j['claim_amount'] as num?)?.toDouble(),
        claimCurrency: j['claim_currency'] as String?,
        claimDescription: j['claim_description'] as String?,
        claimEvidence: j['claim_evidence'] as String?,
        claimBasis: j['claim_basis'] as String?,
        successProbability: (j['success_probability'] as num?)?.toDouble(),
        pCashSuccess: j['p_cash_success'] as double?,
        createdAt: DateTime.parse(j['created_at'] as String),
        updatedAt: DateTime.parse(j['updated_at'] as String),
        applicabilityResult: j['applicability_result'] as String?,
        assessmentSummary: j['assessment_summary'] as String?,
        isCrossBorder: j['is_cross_border'] as bool?,
        claimantDomicileCountry: j['claimant_domicile_country'] as String?,
        defendantDomicileCountry: j['defendant_domicile_country'] as String?,
      );

  String get formattedAmount {
    if (claimAmount == null) return '—';
    return '${claimAmount!.toStringAsFixed(2)} ${claimCurrency ?? 'EUR'}';
  }

  String get probabilityLabel {
    final p = successProbability;
    if (p == null) return '—';
    if (p >= 0.7) return 'Hoch';
    if (p >= 0.4) return 'Mittel';
    return 'Niedrig';
  }
}
