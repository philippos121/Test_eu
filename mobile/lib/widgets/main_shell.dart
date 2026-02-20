import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../providers/auth_provider.dart';
import '../theme.dart';

class MainShell extends ConsumerWidget {
  final Widget child;
  const MainShell({super.key, required this.child});

  static int _tabIndex(String location) {
    if (location.startsWith('/cases')) return 0;
    if (location.startsWith('/statistics')) return 1;
    if (location.startsWith('/admin')) return 2;
    if (location.startsWith('/settings')) return 3;
    return 0;
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final user = ref.watch(authProvider).valueOrNull;
    final isAdmin = user?.isAdmin ?? false;
    final location = GoRouterState.of(context).matchedLocation;
    final currentIndex = _tabIndex(location);

    final destinations = <_NavDest>[
      const _NavDest(icon: Icons.folder_outlined, activeIcon: Icons.folder, label: 'Fälle', path: '/cases'),
      const _NavDest(icon: Icons.bar_chart_outlined, activeIcon: Icons.bar_chart, label: 'Statistik', path: '/statistics'),
      if (isAdmin)
        const _NavDest(icon: Icons.admin_panel_settings_outlined, activeIcon: Icons.admin_panel_settings, label: 'Admin', path: '/admin'),
      const _NavDest(icon: Icons.settings_outlined, activeIcon: Icons.settings, label: 'Einstellungen', path: '/settings'),
    ];

    return Scaffold(
      body: child,
      bottomNavigationBar: NavigationBar(
        selectedIndex: currentIndex.clamp(0, destinations.length - 1),
        onDestinationSelected: (i) => context.go(destinations[i].path),
        destinations: destinations
            .map((d) => NavigationDestination(
                  icon: Icon(d.icon),
                  selectedIcon: Icon(d.activeIcon, color: AppTheme.primary),
                  label: d.label,
                ))
            .toList(),
      ),
    );
  }
}

class _NavDest {
  final IconData icon;
  final IconData activeIcon;
  final String label;
  final String path;
  const _NavDest({required this.icon, required this.activeIcon, required this.label, required this.path});
}
