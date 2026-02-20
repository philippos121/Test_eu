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
import 'screens/onboarding/welcome_screen.dart';
import 'screens/onboarding/how_it_works_screen.dart';
import 'screens/onboarding/agb_screen.dart';
import 'screens/settings/settings_screen.dart';
import 'widgets/main_shell.dart';

// Public routes that do not require authentication
const _publicPrefixes = ['/', '/how-it-works', '/agb', '/auth'];

final routerProvider = Provider<GoRouter>((ref) {
  return GoRouter(
    initialLocation: '/',
    redirect: (context, state) {
      final auth = ref.read(authProvider);
      final loggedIn = auth.valueOrNull != null;
      final loc = state.matchedLocation;

      final isPublic = _publicPrefixes.any(
        (p) => p == '/' ? loc == '/' : loc.startsWith(p),
      );

      // Unauthenticated user trying to access a protected route
      if (!loggedIn && !isPublic) return '/';

      // Authenticated user landing on auth screens → go to cases
      if (loggedIn && loc.startsWith('/auth')) return '/cases';

      return null;
    },
    refreshListenable: _AuthListenable(ref),
    routes: [
      // ── Public / onboarding routes (no shell) ───────────────────────────
      GoRoute(path: '/', builder: (_, __) => const WelcomeScreen()),
      GoRoute(path: '/how-it-works', builder: (_, __) => const HowItWorksScreen()),
      GoRoute(path: '/agb', builder: (_, __) => const AgbScreen()),

      // ── Auth routes (no shell) ───────────────────────────────────────────
      GoRoute(path: '/auth/login', builder: (_, __) => const LoginScreen()),
      GoRoute(path: '/auth/register', builder: (_, __) => const RegisterScreen()),

      // ── App shell with bottom nav (requires auth) ────────────────────────
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
