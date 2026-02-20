class StatisticsOverview {
  final int totalCases;
  final int completedCases;
  final double successRate;
  final double avgRecovery;
  final List<PosteriorItem> posteriors;
  final List<CompletedCaseDetail> completedCasesDetail;

  const StatisticsOverview({
    required this.totalCases,
    required this.completedCases,
    required this.successRate,
    required this.avgRecovery,
    required this.posteriors,
    required this.completedCasesDetail,
  });

  factory StatisticsOverview.fromJson(Map<String, dynamic> j) => StatisticsOverview(
        totalCases: j['total_cases'] as int? ?? 0,
        completedCases: j['completed_cases'] as int? ?? 0,
        successRate: (j['success_rate'] as num?)?.toDouble() ?? 0.0,
        avgRecovery: (j['avg_recovery'] as num?)?.toDouble() ?? 0.0,
        posteriors: ((j['posteriors'] as List?) ?? [])
            .map((e) => PosteriorItem.fromJson(e as Map<String, dynamic>))
            .toList(),
        completedCasesDetail: ((j['completed_cases_detail'] as List?) ?? [])
            .map((e) => CompletedCaseDetail.fromJson(e as Map<String, dynamic>))
            .toList(),
      );
}

class PosteriorItem {
  final String name;
  final String label;
  final double priorAlpha;
  final double priorBeta;
  final int successes;
  final int trials;
  final double postAlpha;
  final double postBeta;
  final double mean;
  final double ciLow;
  final double ciHigh;

  const PosteriorItem({
    required this.name,
    required this.label,
    required this.priorAlpha,
    required this.priorBeta,
    required this.successes,
    required this.trials,
    required this.postAlpha,
    required this.postBeta,
    required this.mean,
    required this.ciLow,
    required this.ciHigh,
  });

  factory PosteriorItem.fromJson(Map<String, dynamic> j) => PosteriorItem(
        name: j['name'] as String,
        label: j['label'] as String? ?? j['name'] as String,
        priorAlpha: (j['prior_alpha'] as num?)?.toDouble() ?? 2.0,
        priorBeta: (j['prior_beta'] as num?)?.toDouble() ?? 2.0,
        successes: j['successes'] as int? ?? 0,
        trials: j['trials'] as int? ?? 0,
        postAlpha: (j['post_alpha'] as num?)?.toDouble() ?? 2.0,
        postBeta: (j['post_beta'] as num?)?.toDouble() ?? 2.0,
        mean: (j['mean'] as num?)?.toDouble() ?? 0.5,
        ciLow: (j['ci_low'] as num?)?.toDouble() ?? 0.0,
        ciHigh: (j['ci_high'] as num?)?.toDouble() ?? 1.0,
      );
}

class CompletedCaseDetail {
  final String id;
  final String title;
  final double? claimAmount;
  final String? claimCurrency;
  final bool outcomeSuccess;
  final double? pCashSuccess;
  final double? netEv;

  const CompletedCaseDetail({
    required this.id,
    required this.title,
    this.claimAmount,
    this.claimCurrency,
    required this.outcomeSuccess,
    this.pCashSuccess,
    this.netEv,
  });

  factory CompletedCaseDetail.fromJson(Map<String, dynamic> j) => CompletedCaseDetail(
        id: j['id'] as String,
        title: j['title'] as String,
        claimAmount: (j['claim_amount'] as num?)?.toDouble(),
        claimCurrency: j['claim_currency'] as String?,
        outcomeSuccess: j['outcome_success'] as bool? ?? false,
        pCashSuccess: (j['p_cash_success'] as num?)?.toDouble(),
        netEv: (j['net_ev'] as num?)?.toDouble(),
      );
}

class NNDataSummary {
  final int nLabeledCases;
  final int nClass0;
  final int nClass1;
  final int nClass2;
  final double blendWeight;
  final int nFeatures;
  final List<String> features;

  const NNDataSummary({
    required this.nLabeledCases,
    required this.nClass0,
    required this.nClass1,
    required this.nClass2,
    required this.blendWeight,
    required this.nFeatures,
    required this.features,
  });

  factory NNDataSummary.fromJson(Map<String, dynamic> j) => NNDataSummary(
        nLabeledCases: j['n_labeled_cases'] as int? ?? 0,
        nClass0: j['n_class0'] as int? ?? 0,
        nClass1: j['n_class1'] as int? ?? 0,
        nClass2: j['n_class2'] as int? ?? 0,
        blendWeight: (j['blend_weight'] as num?)?.toDouble() ?? 0.0,
        nFeatures: j['n_features'] as int? ?? 40,
        features: ((j['features'] as List?) ?? []).cast<String>(),
      );
}
