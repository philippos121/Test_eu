import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'providers/auth_provider.dart';
import 'screens/auth/login_screen.dart';
import 'screens/auth/register_screen.dart';
import 'screens/cases/cases_list_screen.dart';
import 'screens/cases/case_detail_screen.dart';
import 'screens/cases/chat_screen.dart';
import 'screens/documents/documents_screen.dart';
import 'screens/admin/admin_dashboard_screen.dart';
import 'screens/admin/nn_dashboard_screen.dart';
import 'screens/admin/statistics_screen.dart';
import 'screens/settings/settings_screen.dart';
import 'widgets/main_shell.dart';

final routerProvider = Provider<GoRouter>((ref) {
  final auth = ref.watch(authProvider);

  return GoRouter(
    initialLocation: '/cases',
    redirect: (context, state) {
      final loggedIn = auth.valueOrNull != null;
      final onAuth = state.matchedLocation.startsWith('/auth');
      if (!loggedIn && !onAuth) return '/auth/login';
      if (loggedIn && onAuth) return '/cases';
      return null;
    },
    refreshListenable: _AuthListenable(ref),
    routes: [
      // Auth routes (no shell)
      GoRoute(path: '/auth/login', builder: (_, __) => const LoginScreen()),
      GoRoute(path: '/auth/register', builder: (_, __) => const RegisterScreen()),

      // App shell with bottom nav
      ShellRoute(
        builder: (context, state, child) => MainShell(child: child),
        routes: [
          GoRoute(
            path: '/cases',
            builder: (_, __) => const CasesListScreen(),
            routes: [
              GoRoute(
                path: ':caseId',
                builder: (_, state) =>
                    CaseDetailScreen(caseId: state.pathParameters['caseId']!),
                routes: [
                  GoRoute(
                    path: 'chat',
                    builder: (_, state) =>
                        ChatScreen(caseId: state.pathParameters['caseId']!),
                  ),
                  GoRoute(
                    path: 'documents',
                    builder: (_, state) =>
                        DocumentsScreen(caseId: state.pathParameters['caseId']!),
                  ),
                ],
              ),
            ],
          ),
          GoRoute(
            path: '/statistics',
            builder: (_, __) => const StatisticsScreen(),
          ),
          GoRoute(
            path: '/admin',
            builder: (_, __) => const AdminDashboardScreen(),
            routes: [
              GoRoute(
                path: 'nn',
                builder: (_, __) => const NNDashboardScreen(),
              ),
            ],
          ),
          GoRoute(
            path: '/settings',
            builder: (_, __) => const SettingsScreen(),
          ),
        ],
      ),
    ],
  );
});

// Bridges Riverpod auth state to GoRouter's Listenable
class _AuthListenable extends ChangeNotifier {
  _AuthListenable(Ref ref) {
    ref.listen(authProvider, (_, __) => notifyListeners());
  }
}
