import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:percent_indicator/circular_percent_indicator.dart';
import '../../models/case.dart';
import '../../models/process_score.dart';
import '../../providers/cases_provider.dart';
import '../../providers/auth_provider.dart';
import '../../services/statistics_service.dart';
import '../../theme.dart';
import '../../widgets/common.dart';

class CaseDetailScreen extends ConsumerWidget {
  final String caseId;
  const CaseDetailScreen({super.key, required this.caseId});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final caseAsync = ref.watch(singleCaseProvider(caseId));
    final scoreAsync = ref.watch(scoreProvider(caseId));
    final isAdmin = ref.watch(authProvider).valueOrNull?.isAdmin ?? false;

    return Scaffold(
      backgroundColor: AppTheme.surface,
      appBar: AppBar(
        title: caseAsync.when(
          data: (c) => Text(c.title, overflow: TextOverflow.ellipsis),
          loading: () => const Text('Fall'),
          error: (_, __) => const Text('Fall'),
        ),
        actions: [
          if (isAdmin)
            IconButton(
              icon: const Icon(Icons.analytics_outlined),
              tooltip: 'Erwarteter Wert',
              onPressed: () => _showExpectedValue(context, isAdmin),
            ),
        ],
      ),
      body: caseAsync.when(
        loading: () => const LoadingCenter(),
        error: (e, _) => ErrorCenter(error: e, onRetry: () => ref.invalidate(singleCaseProvider(caseId))),
        data: (c) => _CaseDetailBody(c: c, scoreAsync: scoreAsync, isAdmin: isAdmin),
      ),
    );
  }

  Future<void> _showExpectedValue(BuildContext context, bool isAdmin) async {
    if (!isAdmin) return;
    showDialog(
      context: context,
      builder: (_) => _ExpectedValueDialog(caseId: caseId),
    );
  }
}

class _CaseDetailBody extends StatelessWidget {
  final Case c;
  final AsyncValue<ProcessScore?> scoreAsync;
  final bool isAdmin;
  const _CaseDetailBody({required this.c, required this.scoreAsync, required this.isAdmin});

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        // Status + progress
        Card(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Row(children: [
                StatusBadge(status: c.status),
                const Spacer(),
                if (c.claimAmount != null)
                  Text(c.formattedAmount,
                      style: const TextStyle(
                          fontSize: 16, fontWeight: FontWeight.w800, color: AppTheme.primary)),
              ]),
              const SizedBox(height: 14),
              CaseStepProgress(status: c.status),
            ]),
          ),
        ).animate().fadeIn(),
        const SizedBox(height: 12),

        // Action buttons
        Row(children: [
          Expanded(
            child: FilledButton.icon(
              onPressed: c.status.canChat ? () => context.push('/cases/${c.id}/chat') : null,
              icon: const Icon(Icons.chat_outlined, size: 18),
              label: const Text('Chat öffnen'),
            ),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: OutlinedButton.icon(
              onPressed: () => context.push('/cases/${c.id}/documents'),
              icon: const Icon(Icons.description_outlined, size: 18),
              label: const Text('Dokumente'),
            ),
          ),
        ]).animate().fadeIn(delay: 100.ms),
        const SizedBox(height: 16),

        // Score section
        scoreAsync.when(
          loading: () => const Card(child: Padding(padding: EdgeInsets.all(24), child: LoadingCenter())),
          error: (e, _) => const SizedBox.shrink(),
          data: (score) => score == null
              ? const SizedBox.shrink()
              : _ScoreSection(score: score, successProbability: c.successProbability),
        ),

        const SectionHeader(title: 'FALLDETAILS'),
        Card(
          child: Padding(
            padding: const EdgeInsets.all(14),
            child: Column(children: [
              InfoTile(label: 'Kläger', value: c.claimantName),
              if (c.claimantCountry != null) InfoTile(label: 'Kläger-Land', value: c.claimantCountry),
              const Divider(),
              InfoTile(label: 'Beklagter', value: c.defendantName),
              if (c.defendantCountry != null) InfoTile(label: 'Beklagter-Land', value: c.defendantCountry),
              const Divider(),
              InfoTile(label: 'Forderungsbetrag', value: c.formattedAmount),
              InfoTile(label: 'Grenzüberschreitend', value: c.isCrossBorder == true ? 'Ja' : 'Nein'),
              if (c.claimDescription != null) ...[
                const Divider(),
                Align(
                  alignment: Alignment.centerLeft,
                  child: Text('Beschreibung', style: TextStyle(fontSize: 12, color: Colors.grey.shade600)),
                ),
                const SizedBox(height: 4),
                Text(c.claimDescription!, style: const TextStyle(fontSize: 13)),
              ],
            ]),
          ),
        ).animate().fadeIn(delay: 200.ms),

        if (c.assessmentSummary != null) ...[
          const SectionHeader(title: 'BEWERTUNG'),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(14),
              child: Text(c.assessmentSummary!, style: const TextStyle(fontSize: 13, height: 1.5)),
            ),
          ).animate().fadeIn(delay: 250.ms),
        ],
        const SizedBox(height: 80),
      ]),
    );
  }
}

class _ScoreSection extends StatelessWidget {
  final ProcessScore score;
  final double? successProbability;
  const _ScoreSection({required this.score, required this.successProbability});

  @override
  Widget build(BuildContext context) {
    final p = successProbability ?? score.pCashSuccess ?? 0.0;
    return Column(children: [
      const SectionHeader(title: 'ERFOLGSWAHRSCHEINLICHKEIT'),
      Card(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(children: [
            Row(mainAxisAlignment: MainAxisAlignment.center, children: [
              CircularPercentIndicator(
                radius: 56,
                lineWidth: 10,
                percent: p.clamp(0.0, 1.0),
                center: Column(mainAxisSize: MainAxisSize.min, children: [
                  Text(
                    '${(p * 100).toStringAsFixed(0)}%',
                    style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w800),
                  ),
                  const Text('Erfolg', style: TextStyle(fontSize: 10, color: Colors.grey)),
                ]),
                progressColor: p >= 0.65 ? AppTheme.success : p >= 0.35 ? AppTheme.warning : AppTheme.danger,
                backgroundColor: Colors.grey.shade200,
                animation: true,
                animationDuration: 800,
              ),
              const SizedBox(width: 24),
              Expanded(
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  if (score.nnWeight > 0) ...[
                    Text('NN-Blend: ${score.nnWeightLabel}',
                        style: const TextStyle(fontSize: 12, color: Colors.grey)),
                    const SizedBox(height: 4),
                  ],
                  if (score.modelVersion != null)
                    Text('Modell: ${score.modelVersion}',
                        style: const TextStyle(fontSize: 12, color: Colors.grey)),
                ]),
              ),
            ]),
            const SizedBox(height: 16),
            const Divider(),
            const SizedBox(height: 12),
            if (score.pClaimValid != null)
              PillarCard(
                title: 'Anspruch gültig',
                value: score.pClaimValid,
                description: 'P(entstanden · nicht untergegangen · durchsetzbar)',
              ),
            if (score.pClaimProvable != null)
              PillarCard(
                title: 'Beweisbarkeit',
                value: score.pClaimProvable,
                description: 'P(beweisbar | gültig)',
              ),
            if (score.pPayment != null)
              PillarCard(
                title: 'Zahlung erhalten',
                value: score.pPayment,
                description: 'P(Zahlung | Urteil)',
              ),
          ]),
        ),
      ).animate().fadeIn(delay: 150.ms),
      if (score.topDrivers.isNotEmpty) ...[
        const SectionHeader(title: 'TREIBER'),
        Card(
          child: Column(
            children: score.topDrivers.map((d) => ListTile(
              dense: true,
              leading: Icon(
                d.isPositive ? Icons.arrow_upward : Icons.arrow_downward,
                color: d.isPositive ? AppTheme.success : AppTheme.danger,
                size: 18,
              ),
              title: Text(d.label, style: const TextStyle(fontSize: 13)),
              trailing: Text(
                '${d.delta >= 0 ? '+' : ''}${(d.delta * 100).toStringAsFixed(1)}pp',
                style: TextStyle(
                  fontSize: 12,
                  fontWeight: FontWeight.w600,
                  color: d.isPositive ? AppTheme.success : AppTheme.danger,
                ),
              ),
            )).toList(),
          ),
        ).animate().fadeIn(delay: 200.ms),
      ],
    ]);
  }
}

class _ExpectedValueDialog extends StatefulWidget {
  final String caseId;
  const _ExpectedValueDialog({required this.caseId});
  @override
  State<_ExpectedValueDialog> createState() => _ExpectedValueDialogState();
}

class _ExpectedValueDialogState extends State<_ExpectedValueDialog> {
  Map<String, dynamic>? _data;
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final d = await StatisticsService().getExpectedValue(widget.caseId);
      if (mounted) setState(() { _data = d; _loading = false; });
    } catch (e) {
      if (mounted) setState(() { _error = e.toString(); _loading = false; });
    }
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('Erwarteter Netto-Ertrag'),
      content: SizedBox(
        width: 300,
        child: _loading
            ? const Center(child: CircularProgressIndicator())
            : _error != null
                ? Text(_error!, style: const TextStyle(color: AppTheme.danger))
                : _EVContent(data: _data!),
      ),
      actions: [TextButton(onPressed: () => Navigator.pop(context), child: const Text('Schließen'))],
    );
  }
}

class _EVContent extends StatelessWidget {
  final Map<String, dynamic> data;
  const _EVContent({required this.data});

  @override
  Widget build(BuildContext context) {
    final rec = data['recommendation'] as String? ?? '';
    final netEv = (data['net_expected_value'] as num?)?.toDouble() ?? 0;
    final recColor = rec == 'empfohlen'
        ? AppTheme.success
        : rec == 'riskant'
            ? AppTheme.warning
            : AppTheme.danger;

    return SingleChildScrollView(
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Container(
          width: double.infinity,
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(
            color: recColor.withOpacity(0.1),
            borderRadius: BorderRadius.circular(8),
          ),
          child: Column(children: [
            Text(rec.toUpperCase(),
                style: TextStyle(color: recColor, fontWeight: FontWeight.w800, fontSize: 14)),
            Text(
              '${netEv >= 0 ? '+' : ''}${netEv.toStringAsFixed(2)} EUR',
              style: TextStyle(color: recColor, fontSize: 20, fontWeight: FontWeight.w800),
            ),
          ]),
        ),
        const SizedBox(height: 12),
        Text(data['recommendation_reason'] as String? ?? '',
            style: const TextStyle(fontSize: 12, color: Colors.grey)),
        const SizedBox(height: 12),
        _row('P(Gewinn)', '${((data['p_win'] as num?)?.toDouble() ?? 0) * 100:.0f}%'),
        _row('Provision', '${(data['expected_commission'] as num?)?.toDouble()?.toStringAsFixed(2)} EUR'),
        _row('Gerichtskosten', '${(data['court_fees'] as num?)?.toDouble()?.toStringAsFixed(2)} EUR'),
        _row('Anwaltskosten', '${(data['attorney_costs'] as num?)?.toDouble()?.toStringAsFixed(2)} EUR'),
        _row('Servicegebühr', '${(data['service_fees'] as num?)?.toDouble()?.toStringAsFixed(2)} EUR'),
      ]),
    );
  }

  Widget _row(String label, String value) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 3),
        child: Row(children: [
          Expanded(child: Text(label, style: const TextStyle(fontSize: 12, color: Colors.grey))),
          Text(value, style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600)),
        ]),
      );
}

extension on double {
  String toStringAsFixed0() => toStringAsFixed(0);
}
