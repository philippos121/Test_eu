import '../config/api_config.dart';
import '../models/statistics.dart';
import 'api_client.dart';

class StatisticsService {
  final _api = ApiClient.instance;

  Future<StatisticsOverview> getOverview() async {
    final res = await _api.get<Map<String, dynamic>>(ApiConfig.statisticsOverviewPath);
    return StatisticsOverview.fromJson(res.data!);
  }

  Future<NNDataSummary> getNNDataSummary() async {
    final res = await _api.get<Map<String, dynamic>>(ApiConfig.nnDataSummaryPath);
    return NNDataSummary.fromJson(res.data!);
  }

  Future<Map<String, dynamic>> trainNN({
    int epochs = 300,
    double lr = 0.005,
    double l2 = 0.0001,
    int batchSize = 16,
  }) async {
    final res = await _api.post<Map<String, dynamic>>(
      ApiConfig.nnTrainPath,
      data: {'epochs': epochs, 'lr': lr, 'l2': l2, 'batch_size': batchSize},
    );
    return res.data!;
  }

  Future<Map<String, dynamic>?> getNNStatus() async {
    final res = await _api.get<dynamic>(ApiConfig.nnStatusPath);
    if (res.data == null) return null;
    return res.data as Map<String, dynamic>;
  }

  Future<List<Map<String, dynamic>>> getNNPredictions() async {
    final res = await _api.get<List<dynamic>>(ApiConfig.nnPredictionsPath);
    return res.data!.map((e) => e as Map<String, dynamic>).toList();
  }

  Future<Map<String, dynamic>> seedData({bool force = false}) async {
    final res = await _api.post<Map<String, dynamic>>(
      ApiConfig.seedPath,
      queryParameters: {'force': force},
    );
    return res.data!;
  }

  Future<Map<String, dynamic>> updatePriors() async {
    final res = await _api.post<Map<String, dynamic>>(ApiConfig.updatePriorsPath);
    return res.data!;
  }

  Future<List<Map<String, dynamic>>> getAdminCases() async {
    final res = await _api.get<List<dynamic>>(ApiConfig.adminCasesPath);
    return res.data!.map((e) => e as Map<String, dynamic>).toList();
  }

  Future<Map<String, dynamic>> getExpectedValue(String caseId) async {
    final res = await _api.get<Map<String, dynamic>>('/api/cases/$caseId/expected-value');
    return res.data!;
  }

  Future<Map<String, dynamic>> recomputeScore(String caseId) async {
    final res =
        await _api.post<Map<String, dynamic>>('/api/admin/cases/$caseId/score');
    return res.data!;
  }
}
