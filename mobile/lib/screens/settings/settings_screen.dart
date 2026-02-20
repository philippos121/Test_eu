import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:url_launcher/url_launcher.dart';
import '../../providers/auth_provider.dart';
import '../../theme.dart';
import '../../widgets/common.dart';

class SettingsScreen extends ConsumerWidget {
  const SettingsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final user = ref.watch(authProvider).valueOrNull;

    return Scaffold(
      backgroundColor: AppTheme.surface,
      appBar: AppBar(title: const Text('Einstellungen')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          // User profile card
          if (user != null)
            Card(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Row(children: [
                  CircleAvatar(
                    radius: 28,
                    backgroundColor: AppTheme.primary,
                    child: Text(user.initials,
                        style: const TextStyle(
                            color: Colors.white, fontSize: 18, fontWeight: FontWeight.w800)),
                  ),
                  const SizedBox(width: 14),
                  Expanded(
                    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      Text(user.fullName,
                          style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
                      Text(user.email,
                          style: const TextStyle(fontSize: 13, color: Colors.grey)),
                      const SizedBox(height: 4),
                      if (user.isAdmin)
                        Container(
                          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                          decoration: BoxDecoration(
                            color: AppTheme.primary.withOpacity(0.1),
                            borderRadius: BorderRadius.circular(4),
                          ),
                          child: const Text('Administrator',
                              style: TextStyle(
                                  fontSize: 10,
                                  color: AppTheme.primary,
                                  fontWeight: FontWeight.w600)),
                        ),
                    ]),
                  ),
                ]),
              ),
            ),
          const SizedBox(height: 16),

          // App info
          const SectionHeader(title: 'APP-INFO'),
          Card(
            child: Column(children: [
              _SettingsTile(
                icon: Icons.info_outline,
                title: 'Über die App',
                subtitle: 'EU-Bagatellverfahren — Verordnung 861/2007',
                onTap: () => _showAbout(context),
              ),
              const Divider(height: 1, indent: 56),
              _SettingsTile(
                icon: Icons.policy_outlined,
                title: 'EU-Verordnung 861/2007',
                subtitle: 'Geringfügige Forderungen bis EUR 5.000',
                onTap: () => launchUrl(Uri.parse('https://eur-lex.europa.eu/legal-content/DE/TXT/?uri=CELEX:32007R0861')),
              ),
            ]),
          ),

          const SectionHeader(title: 'VERFAHREN'),
          Card(
            child: Column(children: [
              _SettingsTile(
                icon: Icons.school_outlined,
                title: 'Wie funktioniert das Verfahren?',
                subtitle: '5-stufiges EU-Klageformular-A-Verfahren',
                onTap: () => _showHowItWorks(context),
              ),
              const Divider(height: 1, indent: 56),
              _SettingsTile(
                icon: Icons.calculate_outlined,
                title: 'Scoring-Methodik',
                subtitle: 'LLM × Regeln × NN-Blend (max 30%)',
                onTap: () => _showScoring(context),
              ),
            ]),
          ),

          const SectionHeader(title: 'KONTO'),
          Card(
            child: _SettingsTile(
              icon: Icons.logout,
              title: 'Abmelden',
              subtitle: 'Von diesem Gerät abmelden',
              titleColor: AppTheme.danger,
              iconColor: AppTheme.danger,
              onTap: () => _confirmLogout(context, ref),
            ),
          ),
          const SizedBox(height: 24),
          Center(
            child: Text(
              'EU-Bagatellverfahren-Portal v1.0.0\nFlutter App',
              textAlign: TextAlign.center,
              style: TextStyle(fontSize: 11, color: Colors.grey.shade400),
            ),
          ),
          const SizedBox(height: 80),
        ],
      ),
    );
  }

  void _showAbout(BuildContext context) {
    showDialog(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('EU-Bagatellverfahren'),
        content: const Text(
          'Dieses Portal unterstützt EU-Bürger und Unternehmen bei der Einleitung geringfügiger '
          'Forderungsverfahren nach der Verordnung (EG) Nr. 861/2007 des Europäischen Parlaments.\n\n'
          'Forderungen bis EUR 5.000 können grenzüberschreitend geltend gemacht werden.\n\n'
          'Scoring: 100% LLM · 100% Regelwerk · ≤30% NN-Blend',
        ),
        actions: [TextButton(onPressed: () => Navigator.pop(context), child: const Text('OK'))],
      ),
    );
  }

  void _showHowItWorks(BuildContext context) {
    showDialog(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('Verfahrensschritte'),
        content: const SingleChildScrollView(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, mainAxisSize: MainAxisSize.min, children: [
            _Step(n: '1', title: 'Aufnahme', desc: 'Grunddaten zum Fall erfassen'),
            _Step(n: '2', title: 'Anwendbarkeit', desc: 'Prüfung der Voraussetzungen'),
            _Step(n: '3', title: 'Fallprüfung', desc: 'Sachverhalt & Rechtslage'),
            _Step(n: '4', title: 'Beweisaufnahme', desc: 'Dokumente & Nachweise'),
            _Step(n: '5', title: 'Formular A', desc: 'EU-Klageformular generieren'),
          ]),
        ),
        actions: [TextButton(onPressed: () => Navigator.pop(context), child: const Text('OK'))],
      ),
    );
  }

  void _showScoring(BuildContext context) {
    showDialog(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('Scoring-Methodik v4'),
        content: const SingleChildScrollView(
          child: Text(
            'p_cash = p_valid × p_provable × p_payment\n\n'
            'p_final = (1 − w_NN) × p_cash + w_NN × p_NN\n\n'
            'w_NN = 0.30 × (1 − e^(−n/25))   [max 30%]\n\n'
            'NN: 40 Features → 32 → 16 → 3 Softmax\n'
            'Klassen: 0=Vollerfolg, 1=Teilerfolg, 2=Misserfolg\n\n'
            'p_NN = P[0] + 0.5 × P[1]',
            style: TextStyle(fontSize: 13, fontFamily: 'monospace'),
          ),
        ),
        actions: [TextButton(onPressed: () => Navigator.pop(context), child: const Text('OK'))],
      ),
    );
  }

  Future<void> _confirmLogout(BuildContext context, WidgetRef ref) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Abmelden?'),
        content: const Text('Möchten Sie sich wirklich abmelden?'),
        actions: [
          TextButton(onPressed: () => ctx.pop(false), child: const Text('Abbrechen')),
          TextButton(
            onPressed: () => ctx.pop(true),
            style: TextButton.styleFrom(foregroundColor: AppTheme.danger),
            child: const Text('Abmelden'),
          ),
        ],
      ),
    );
    if (confirmed == true) {
      await ref.read(authProvider.notifier).logout();
    }
  }
}

class _SettingsTile extends StatelessWidget {
  final IconData icon;
  final String title;
  final String subtitle;
  final VoidCallback onTap;
  final Color? titleColor;
  final Color? iconColor;

  const _SettingsTile({
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.onTap,
    this.titleColor,
    this.iconColor,
  });

  @override
  Widget build(BuildContext context) => ListTile(
        leading: Icon(icon, color: iconColor ?? AppTheme.primary, size: 22),
        title: Text(title,
            style: TextStyle(fontSize: 14, fontWeight: FontWeight.w500, color: titleColor)),
        subtitle: Text(subtitle, style: const TextStyle(fontSize: 12)),
        trailing: const Icon(Icons.chevron_right, size: 18, color: Colors.grey),
        onTap: onTap,
      );
}

class _Step extends StatelessWidget {
  final String n;
  final String title;
  final String desc;
  const _Step({required this.n, required this.title, required this.desc});

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.only(bottom: 12),
        child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          CircleAvatar(
            radius: 12,
            backgroundColor: AppTheme.primary,
            child: Text(n, style: const TextStyle(color: Colors.white, fontSize: 11, fontWeight: FontWeight.w700)),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(title, style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 13)),
              Text(desc, style: const TextStyle(fontSize: 12, color: Colors.grey)),
            ]),
          ),
        ]),
      );
}
