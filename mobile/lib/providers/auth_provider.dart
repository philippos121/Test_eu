import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/user.dart';
import '../services/auth_service.dart';

// The central auth state
class AuthState {
  final AppUser? user;
  final bool isLoading;
  final String? error;

  const AuthState({this.user, this.isLoading = false, this.error});

  bool get isLoggedIn => user != null;
  bool get isAdmin => user?.isAdmin ?? false;

  AuthState copyWith({AppUser? user, bool? isLoading, String? error, bool clearUser = false}) =>
      AuthState(
        user: clearUser ? null : (user ?? this.user),
        isLoading: isLoading ?? this.isLoading,
        error: error,
      );
}

class AuthNotifier extends AsyncNotifier<AppUser?> {
  final _svc = AuthService();

  @override
  Future<AppUser?> build() async => _svc.getMe();

  Future<void> login(String email, String password) async {
    state = const AsyncLoading();
    state = await AsyncValue.guard(() async {
      final result = await _svc.login(email: email, password: password);
      return result.user;
    });
  }

  Future<void> register(String email, String password, String fullName) async {
    state = const AsyncLoading();
    state = await AsyncValue.guard(() async {
      await _svc.register(email: email, password: password, fullName: fullName);
      final result = await _svc.login(email: email, password: password);
      return result.user;
    });
  }

  Future<void> logout() async {
    await _svc.logout();
    state = const AsyncData(null);
  }
}

final authProvider = AsyncNotifierProvider<AuthNotifier, AppUser?>(AuthNotifier.new);
