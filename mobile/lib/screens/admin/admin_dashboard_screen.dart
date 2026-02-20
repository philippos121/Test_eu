import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';
import '../../providers/auth_provider.dart';
import '../../services/statistics_service.dart';
import '../../theme.dart';
import '../../widgets/common.dart';

final _adminCasesProvider = FutureProvider<List<Map<String, dynamic>>>((ref) {
  return StatisticsService().getAdminCases();
});

class AdminDashboardScreen extends ConsumerWidget {
  const AdminDashboardScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final user = ref.watch(authProvider).valueOrNull;
    if (!(user?.isAdmin ?? false)) {
      return Scaffold(
        appBar: AppBar(title: const Text('Admin')),
        body: const Center(
          child: Text('Nur für Administratoren.',
              style: TextStyle(color: AppTheme.danger, fontSize: 16)),
        ),
      );
    }

    final casesAsync = ref.watch(_adminCasesProvider);

    return Scaffold(
      backgroundColor: AppTheme.surface,
      appBar: AppBar(
        title: const Text('Admin Dashboard'),
        actions: [
          IconButton(
            icon: const Icon(Icons.memory_outlined),
            tooltip: 'Neuronales Netz',
            onPressed: () => context.push('/admin/nn'),
          ),
        ],
      ),
      body: casesAsync.when(
        loading: () => const LoadingCenter(),
        error: (e, _) =>
            ErrorCenter(error: e, onRetry: () => ref.invalidate(_adminCasesProvider)),
        data: (cases) => RefreshIndicator(
          onRefresh: () async => ref.invalidate(_adminCasesProvider),
          color: AppTheme.primary,
          child: Column(children: [
            // Summary bar
            Container(
              color: Colors.white,
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
              child: Row(children: [
                _SummaryChip(
                    label: '${cases.length} Fälle',
                    color: AppTheme.primary,
                    icon: Icons.folder),
                const SizedBox(width: 8),
                _SummaryChip(
                    label: '${cases.where((c) => c['status'] == 'completed').length} Abgeschlossen',
                    color: AppTheme.success,
                    icon: Icons.check_circle),
                const SizedBox(width: 8),
                _SummaryChip(
                    label: '${cases.where((c) => c['status'] == 'rejected').length} Abgelehnt',
                    color: AppTheme.danger,
                    icon: Icons.cancel),
              ]),
            ),
            const Divider(height: 1),
            Expanded(
              child: ListView.builder(
                padding: const EdgeInsets.all(12),
                itemCount: cases.length,
                itemBuilder: (_, i) =>
                    _AdminCaseTile(data: cases[i]).animate().fadeIn(delay: (i * 40).ms),
              ),
            ),
          ]),
        ),
      ),
    );
  }
}

class _SummaryChip extends StatelessWidget {
  final String label;
  final Color color;
  final IconData icon;
  const _SummaryChip({required this.label, required this.color, required this.icon});

  @override
  Widget build(BuildContext context) => Chip(
        avatar: Icon(icon, size: 14, color: color),
        label: Text(label, style: TextStyle(fontSize: 11, color: color, fontWeight: FontWeight.w600)),
        backgroundColor: color.withOpacity(0.08),
        padding: const EdgeInsets.symmetric(horizontal: 4),
        visualDensity: VisualDensity.compact,
      );
}

class _AdminCaseTile extends StatelessWidget {
  final Map<String, dynamic> data;
  const _AdminCaseTile({required this.data});

  @override
  Widget build(BuildContext context) {
    final status = data['status'] as String? ?? '';
    final prob = (data['success_probability'] as num?)?.toDouble();
    final pCash = (data['p_cash_success'] as num?)?.toDouble();
    final amount = (data['claim_amount'] as num?)?.toDouble();
    final currency = data['claim_currency'] as String? ?? 'EUR';
    final userEmail = data['user_email'] as String? ?? '';
    final createdAt = data['created_at'] as String?;

    Color statusColor;
    switch (status) {
      case 'completed': statusColor = AppTheme.success; break;
      case 'rejected': statusColor = AppTheme.danger; break;
      default: statusColor = Colors.orange;
    }

    return Card(
      margin: const EdgeInsets.only(bottom: 8),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            Expanded(
              child: Text(data['title'] as String? ?? '—',
                  maxLines: 1, overflow: TextOverflow.ellipsis,
                  style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w700)),
            ),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
              decoration: BoxDecoration(
                color: statusColor.withOpacity(0.1),
                borderRadius: BorderRadius.circular(5),
              ),
              child: Text(status, style: TextStyle(fontSize: 10, color: statusColor, fontWeight: FontWeight.w600)),
            ),
          ]),
          const SizedBox(height: 6),
          Row(children: [
            if (data['claimant_name'] != null)
              Expanded(
                child: Text(
                  '${data['claimant_name']} → ${data['defendant_name'] ?? '—'}',
                  style: const TextStyle(fontSize: 11, color: Colors.grey),
                  maxLines: 1, overflow: TextOverflow.ellipsis,
                ),
              ),
            if (amount != null)
              Text('${amount.toStringAsFixed(2)} $currency',
                  style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: AppTheme.primary)),
          ]),
          const SizedBox(height: 6),
          Row(children: [
            if (prob != null) ...[
              Text('LLM: ${(prob * 100).toStringAsFixed(0)}%',
                  style: TextStyle(
                      fontSize: 11,
                      color: prob >= 0.65 ? AppTheme.success : prob >= 0.35 ? AppTheme.warning : AppTheme.danger,
                      fontWeight: FontWeight.w600)),
              const SizedBox(width: 10),
            ],
            if (pCash != null)
              Text('p(cash): ${(pCash * 100).toStringAsFixed(0)}%',
                  style: TextStyle(
                      fontSize: 11,
                      color: pCash >= 0.5 ? AppTheme.success : AppTheme.danger,
                      fontWeight: FontWeight.w600)),
            const Spacer(),
            Text(userEmail, style: const TextStyle(fontSize: 10, color: Colors.grey)),
          ]),
          if (createdAt != null)
            Text(
              DateFormat('dd.MM.yyyy').format(DateTime.parse(createdAt)),
              style: const TextStyle(fontSize: 10, color: Colors.grey),
            ),
        ]),
      ),
    );
  }
}
