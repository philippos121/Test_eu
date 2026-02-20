// Configuration: change BASE_URL to point to the backend server.
// In production, use your deployed server URL.
// In development: iOS simulator → http://localhost:8000,
//                 Android emulator → http://10.0.2.2:8000
class ApiConfig {
  static const String baseUrl =
      String.fromEnvironment('API_BASE_URL', defaultValue: 'http://10.0.2.2:8000');

  static const String loginPath = '/api/auth/login';
  static const String registerPath = '/api/auth/register';
  static const String mePath = '/api/auth/me';

  static const String casesPath = '/api/cases';
  static const String statisticsOverviewPath = '/api/statistics/overview';

  static const String nnStatusPath = '/api/nn/status';
  static const String nnTrainPath = '/api/nn/train';
  static const String nnPredictionsPath = '/api/nn/predictions';
  static const String nnDataSummaryPath = '/api/nn/data-summary';

  static const String adminCasesPath = '/api/admin/cases';
  static const String adminPriorsPath = '/api/admin/priors';

  static const String seedPath = '/api/statistics/seed';
  static const String updatePriorsPath = '/api/statistics/update-priors';

  static const Duration connectTimeout = Duration(seconds: 15);
  static const Duration receiveTimeout = Duration(seconds: 60);
}
