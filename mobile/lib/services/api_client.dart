import 'package:dio/dio.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import '../config/api_config.dart';

const _tokenKey = 'eu_portal_access_token';

class ApiClient {
  ApiClient._();
  static final ApiClient instance = ApiClient._();

  final _storage = const FlutterSecureStorage();

  late final Dio _dio = Dio(
    BaseOptions(
      baseUrl: ApiConfig.baseUrl,
      connectTimeout: ApiConfig.connectTimeout,
      receiveTimeout: ApiConfig.receiveTimeout,
      headers: {'Content-Type': 'application/json'},
    ),
  )..interceptors.addAll([
      InterceptorsWrapper(
        onRequest: (options, handler) async {
          final token = await _storage.read(key: _tokenKey);
          if (token != null) {
            options.headers['Authorization'] = 'Bearer $token';
          }
          handler.next(options);
        },
        onError: (error, handler) {
          handler.next(error);
        },
      ),
    ]);

  Future<void> saveToken(String token) => _storage.write(key: _tokenKey, value: token);
  Future<void> deleteToken() => _storage.delete(key: _tokenKey);
  Future<String?> readToken() => _storage.read(key: _tokenKey);

  Future<Response<T>> get<T>(String path, {Map<String, dynamic>? queryParameters}) =>
      _dio.get<T>(path, queryParameters: queryParameters);

  Future<Response<T>> post<T>(String path, {dynamic data, Map<String, dynamic>? queryParameters}) =>
      _dio.post<T>(path, data: data, queryParameters: queryParameters);

  Future<Response<T>> patch<T>(String path, {dynamic data}) => _dio.patch<T>(path, data: data);

  Future<Response<T>> delete<T>(String path) => _dio.delete<T>(path);

  Future<Response<T>> postForm<T>(String path, {required Map<String, dynamic> formData}) =>
      _dio.post<T>(path, data: FormData.fromMap(formData),
          options: Options(contentType: 'multipart/form-data'));

  Future<Response> download(String path, String savePath) =>
      _dio.download(path, savePath);

  /// Returns the full URL for a download path with the token as query param
  Future<String> downloadUrl(String path) async {
    final token = await readToken() ?? '';
    return '${ApiConfig.baseUrl}$path?token=$token';
  }
}
