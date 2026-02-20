class ProcessScore {
  final String id;
  final String caseId;
  final double? pClaimValid;
  final double? pClaimProvable;
  final double? pPayment;
  final double? pCashSuccess;
  final double? pNnPrediction;
  final Map<String, dynamic>? nnPredictionJson;
  final List<dynamic>? driversJson;
  final String? modelVersion;
  final DateTime createdAt;

  const ProcessScore({
    required this.id,
    required this.caseId,
    this.pClaimValid,
    this.pClaimProvable,
    this.pPayment,
    this.pCashSuccess,
    this.pNnPrediction,
    this.nnPredictionJson,
    this.driversJson,
    this.modelVersion,
    required this.createdAt,
  });

  factory ProcessScore.fromJson(Map<String, dynamic> j) => ProcessScore(
        id: j['id'] as String,
        caseId: j['case_id'] as String,
        pClaimValid: (j['p_claim_valid'] as num?)?.toDouble(),
        pClaimProvable: (j['p_claim_provable'] as num?)?.toDouble(),
        pPayment: (j['p_payment'] as num?)?.toDouble(),
        pCashSuccess: (j['p_cash_success'] as num?)?.toDouble(),
        pNnPrediction: (j['p_nn_prediction'] as num?)?.toDouble(),
        nnPredictionJson: j['nn_prediction_json'] as Map<String, dynamic>?,
        driversJson: j['drivers_json'] as List<dynamic>?,
        modelVersion: j['model_version'] as String?,
        createdAt: DateTime.parse(j['created_at'] as String),
      );

  double get nnWeight {
    final nn = nnPredictionJson;
    if (nn == null) return 0.0;
    return (nn['nn_weight'] as num?)?.toDouble() ?? 0.0;
  }

  String get nnWeightLabel => '${(nnWeight * 100).toStringAsFixed(0)}%';

  List<_Driver> get topDrivers {
    final raw = driversJson;
    if (raw == null) return [];
    return raw.map((d) => _Driver.fromJson(d as Map<String, dynamic>)).toList();
  }
}

class _Driver {
  final String label;
  final double delta;
  final String direction;

  const _Driver({required this.label, required this.delta, required this.direction});

  factory _Driver.fromJson(Map<String, dynamic> j) => _Driver(
        label: j['label'] as String? ?? '',
        delta: (j['delta'] as num?)?.toDouble() ?? 0.0,
        direction: j['direction'] as String? ?? '',
      );

  bool get isPositive => direction == '+' || delta > 0;
}
