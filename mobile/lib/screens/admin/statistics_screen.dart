import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:percent_indicator/linear_percent_indicator.dart';
import '../../models/statistics.dart';
import '../../providers/auth_provider.dart';
import '../../services/statistics_service.dart';
import '../../theme.dart';
import '../../widgets/common.dart';

final _overviewProvider = FutureProvider<StatisticsOverview>((ref) {
  return StatisticsService().getOverview();
});

class StatisticsScreen extends ConsumerWidget {
  const StatisticsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final overviewAsync = ref.watch(_overviewProvider);
    final isAdmin = ref.watch(authProvider).valueOrNull?.isAdmin ?? false;

    return Scaffold(
      backgroundColor: AppTheme.surface,
      appBar: AppBar(
        title: const Text('Statistik & Lernen'),
        actions: [
          if (isAdmin)
            PopupMenuButton<String>(
              icon: const Icon(Icons.more_vert),
              onSelected: (v) => _handleAdminAction(context, ref, v),
              itemBuilder: (_) => [
                const PopupMenuItem(value: 'seed', child: Text('Seed-Daten erstellen')),
                const PopupMenuItem(value: 'seed_force', child: Text('Seed-Daten neu erstellen')),
                const PopupMenuItem(value: 'update_priors', child: Text('Priors aktualisieren')),
              ],
            ),
        ],
      ),
      body: overviewAsync.when(
        loading: () => const LoadingCenter(),
        error: (e, _) =>
            ErrorCenter(error: e, onRetry: () => ref.invalidate(_overviewProvider)),
        data: (stats) => RefreshIndicator(
          onRefresh: () async => ref.invalidate(_overviewProvider),
          color: AppTheme.primary,
          child: SingleChildScrollView(
            physics: const AlwaysScrollableScrollPhysics(),
            padding: const EdgeInsets.all(16),
            child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
              _SummaryCards(stats: stats),
              const SectionHeader(title: 'BAYESIANISCHE POSTERIORS'),
              _PosteriorsSection(posteriors: stats.posteriors),
              if (stats.completedCasesDetail.isNotEmpty) ...[
                const SectionHeader(title: 'ABGESCHLOSSENE FÄLLE'),
                _CompletedCasesSection(cases: stats.completedCasesDetail),
              ],
              const SizedBox(height: 80),
            ]),
          ),
        ),
      ),
    );
  }

  Future<void> _handleAdminAction(BuildContext context, WidgetRef ref, String action) async {
    final svc = StatisticsService();
    try {
      if (action == 'seed') {
        await svc.seedData(force: false);
        if (context.mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('Seed-Daten erstellt'), backgroundColor: AppTheme.success),
          );
        }
      } else if (action == 'seed_force') {
        await svc.seedData(force: true);
        if (context.mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('Seed-Daten neu erstellt'), backgroundColor: AppTheme.success),
          );
        }
      } else if (action == 'update_priors') {
        await svc.updatePriors();
        if (context.mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('Priors aktualisiert'), backgroundColor: AppTheme.success),
          );
          ref.invalidate(_overviewProvider);
        }
      }
    } catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Fehler: $e'), backgroundColor: AppTheme.danger),
        );
      }
    }
  }
}

class _SummaryCards extends StatelessWidget {
  final StatisticsOverview stats;
  const _SummaryCards({required this.stats});

  @override
  Widget build(BuildContext context) {
    final cards = [
      ('Fälle gesamt', stats.totalCases.toString(), Icons.folder_outlined, AppTheme.primary),
      ('Abgeschlossen', stats.completedCases.toString(), Icons.check_circle_outline, AppTheme.success),
      ('Erfolgsquote', '${(stats.successRate * 100).toStringAsFixed(0)}%', Icons.trending_up, AppTheme.warning),
      ('⌀ Ertrag', '${stats.avgRecovery.toStringAsFixed(0)} €', Icons.euro_outlined, AppTheme.primary),
    ];
    return GridView.count(
      crossAxisCount: 2,
      mainAxisSpacing: 10,
      crossAxisSpacing: 10,
      childAspectRatio: 1.5,
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      children: List.generate(cards.length, (i) {
        final (label, value, icon, color) = cards[i];
        return Card(
          child: Padding(
            padding: const EdgeInsets.all(14),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Icon(icon, color: color, size: 22),
              const Spacer(),
              Text(value,
                  style: TextStyle(fontSize: 22, fontWeight: FontWeight.w800, color: color)),
              Text(label, style: const TextStyle(fontSize: 11, color: Colors.grey)),
            ]),
          ),
        ).animate().fadeIn(delay: (i * 80).ms).scale(begin: const Offset(0.95, 0.95));
      }),
    );
  }
}

class _PosteriorsSection extends StatelessWidget {
  final List<PosteriorItem> posteriors;
  const _PosteriorsSection({required this.posteriors});

  static const _labels = {
    'valid': 'Anspruchs-Gültigkeit',
    'provable': 'Beweisbarkeit',
    'payment': 'Zahlungseingang',
  };

  @override
  Widget build(BuildContext context) {
    return Column(
      children: posteriors.asMap().entries.map((e) {
        final i = e.key;
        final p = e.value;
        return Card(
          margin: const EdgeInsets.only(bottom: 10),
          child: Padding(
            padding: const EdgeInsets.all(14),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(_labels[p.name] ?? p.label,
                  style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w700)),
              const SizedBox(height: 8),
              LinearPercentIndicator(
                percent: p.mean.clamp(0.0, 1.0),
                lineHeight: 10,
                backgroundColor: Colors.grey.shade200,
                progressColor: AppTheme.primary,
                animation: true,
                animationDuration: 800,
                barRadius: const Radius.circular(5),
                padding: EdgeInsets.zero,
              ),
              const SizedBox(height: 8),
              Row(children: [
                Text('${(p.mean * 100).toStringAsFixed(1)}%',
                    style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w800, color: AppTheme.primary)),
                const SizedBox(width: 8),
                Text(
                  'KI: ${(p.ciLow * 100).toStringAsFixed(0)}% – ${(p.ciHigh * 100).toStringAsFixed(0)}%',
                  style: const TextStyle(fontSize: 11, color: Colors.grey),
                ),
                const Spacer(),
                Text('n=${p.trials}', style: const TextStyle(fontSize: 11, color: Colors.grey)),
              ]),
              const SizedBox(height: 4),
              Text(
                'Prior α=${p.priorAlpha.toStringAsFixed(0)} β=${p.priorBeta.toStringAsFixed(0)} → Post α=${p.postAlpha.toStringAsFixed(0)} β=${p.postBeta.toStringAsFixed(0)}',
                style: const TextStyle(fontSize: 10, color: Colors.grey, fontFamily: 'monospace'),
              ),
            ]),
          ),
        ).animate().fadeIn(delay: (100 + i * 100).ms);
      }).toList(),
    );
  }
}

class _CompletedCasesSection extends StatelessWidget {
  final List<CompletedCaseDetail> cases;
  const _CompletedCasesSection({required this.cases});

  @override
  Widget build(BuildContext context) {
    return Column(
      children: cases.map((c) => Card(
        margin: const EdgeInsets.only(bottom: 8),
        child: ListTile(
          dense: true,
          leading: CircleAvatar(
            radius: 16,
            backgroundColor: c.outcomeSuccess ? AppTheme.success.withOpacity(0.12) : AppTheme.danger.withOpacity(0.12),
            child: Icon(
              c.outcomeSuccess ? Icons.check : Icons.close,
              size: 14,
              color: c.outcomeSuccess ? AppTheme.success : AppTheme.danger,
            ),
          ),
          title: Text(c.title, style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600),
              maxLines: 1, overflow: TextOverflow.ellipsis),
          subtitle: Text(
            c.claimAmount != null ? '${c.claimAmount!.toStringAsFixed(2)} ${c.claimCurrency ?? 'EUR'}' : '—',
            style: const TextStyle(fontSize: 11),
          ),
          trailing: c.pCashSuccess != null
              ? Text('${(c.pCashSuccess! * 100).toStringAsFixed(0)}%',
                  style: TextStyle(
                      fontSize: 13,
                      fontWeight: FontWeight.w700,
                      color: c.pCashSuccess! >= 0.5 ? AppTheme.success : AppTheme.danger))
              : null,
        ),
      )).toList(),
    );
  }
}
