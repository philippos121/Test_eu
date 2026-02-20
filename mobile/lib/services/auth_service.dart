import 'package:dio/dio.dart';
import '../config/api_config.dart';
import '../models/user.dart';
import 'api_client.dart';

class AuthService {
  final _api = ApiClient.instance;

  Future<({AppUser user, String token})> login({
    required String email,
    required String password,
  }) async {
    final res = await _api.postForm<Map<String, dynamic>>(
      ApiConfig.loginPath,
      formData: {'username': email, 'password': password},
    );
    final token = res.data!['access_token'] as String;
    await _api.saveToken(token);

    final meRes = await _api.get<Map<String, dynamic>>(ApiConfig.mePath);
    final user = AppUser.fromJson(meRes.data!);
    return (user: user, token: token);
  }

  Future<AppUser> register({
    required String email,
    required String password,
    required String fullName,
    String language = 'de',
  }) async {
    final res = await _api.post<Map<String, dynamic>>(
      ApiConfig.registerPath,
      data: {
        'email': email,
        'password': password,
        'full_name': fullName,
        'language': language,
      },
    );
    return AppUser.fromJson(res.data!);
  }

  Future<AppUser?> getMe() async {
    try {
      final res = await _api.get<Map<String, dynamic>>(ApiConfig.mePath);
      return AppUser.fromJson(res.data!);
    } on DioException catch (e) {
      if (e.response?.statusCode == 401) return null;
      rethrow;
    }
  }

  Future<void> logout() => _api.deleteToken();
}
