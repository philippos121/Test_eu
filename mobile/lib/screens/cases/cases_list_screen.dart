import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';
import 'package:toastification/toastification.dart';
import '../../models/case.dart';
import '../../providers/auth_provider.dart';
import '../../providers/cases_provider.dart';
import '../../theme.dart';
import '../../widgets/common.dart';

class CasesListScreen extends ConsumerWidget {
  const CasesListScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final casesAsync = ref.watch(casesProvider);
    final user = ref.watch(authProvider).valueOrNull;

    return Scaffold(
      backgroundColor: AppTheme.surface,
      appBar: AppBar(
        title: const Text('Meine Fälle'),
        actions: [
          if (user != null)
            Padding(
              padding: const EdgeInsets.only(right: 8),
              child: CircleAvatar(
                backgroundColor: AppTheme.accent,
                radius: 18,
                child: Text(
                  user.initials,
                  style: const TextStyle(
                      color: AppTheme.primary, fontWeight: FontWeight.w800, fontSize: 12),
                ),
              ),
            ),
        ],
      ),
      floatingActionButton: FloatingActionButton.extended(
        backgroundColor: AppTheme.primary,
        foregroundColor: Colors.white,
        icon: const Icon(Icons.add),
        label: const Text('Neuer Fall'),
        onPressed: () => _createCase(context, ref),
      ),
      body: casesAsync.when(
        loading: () => const LoadingCenter(),
        error: (e, _) => ErrorCenter(
          error: e,
          onRetry: () => ref.invalidate(casesProvider),
        ),
        data: (cases) {
          if (cases.isEmpty) {
            return EmptyState(
              icon: Icons.folder_open_outlined,
              message: 'Noch keine Fälle.\nErstellen Sie Ihren ersten Fall!',
              buttonLabel: 'Neuen Fall erstellen',
              onButton: () => _createCase(context, ref),
            );
          }
          return RefreshIndicator(
            onRefresh: () => ref.read(casesProvider.notifier).refresh(),
            color: AppTheme.primary,
            child: ListView.builder(
              padding: const EdgeInsets.fromLTRB(16, 8, 16, 96),
              itemCount: cases.length,
              itemBuilder: (ctx, i) =>
                  _CaseTile(c: cases[i], index: i).animate().fadeIn(delay: (i * 50).ms),
            ),
          );
        },
      ),
    );
  }

  Future<void> _createCase(BuildContext context, WidgetRef ref) async {
    final titleCtrl = TextEditingController();
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Neuen Fall erstellen'),
        content: TextField(
          controller: titleCtrl,
          autofocus: true,
          decoration: const InputDecoration(labelText: 'Fallbezeichnung', hintText: 'z.B. Müller GmbH vs. Fischer'),
          textCapitalization: TextCapitalization.sentences,
        ),
        actions: [
          TextButton(onPressed: () => ctx.pop(false), child: const Text('Abbrechen')),
          FilledButton(
            onPressed: () => ctx.pop(true),
            style: FilledButton.styleFrom(minimumSize: Size.zero, padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10)),
            child: const Text('Erstellen'),
          ),
        ],
      ),
    );
    if (confirmed != true || titleCtrl.text.trim().isEmpty) return;
    try {
      final c = await ref.read(casesProvider.notifier).createCase(titleCtrl.text.trim());
      if (context.mounted) context.push('/cases/${c.id}');
    } catch (e) {
      if (context.mounted) {
        toastification.show(
          context: context,
          title: const Text('Fehler'),
          description: Text(e.toString()),
          type: ToastificationType.error,
        );
      }
    }
  }
}

class _CaseTile extends StatelessWidget {
  final Case c;
  final int index;
  const _CaseTile({required this.c, required this.index});

  @override
  Widget build(BuildContext context) {
    final prob = c.successProbability;
    return Card(
      margin: const EdgeInsets.only(bottom: 10),
      child: InkWell(
        borderRadius: BorderRadius.circular(12),
        onTap: () => context.push('/cases/${c.id}'),
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Row(children: [
              Expanded(
                child: Text(c.title,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w700)),
              ),
              const SizedBox(width: 8),
              StatusBadge(status: c.status),
            ]),
            const SizedBox(height: 10),
            Row(children: [
              Expanded(
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  if (c.claimantName != null)
                    Text(c.claimantName!,
                        style: const TextStyle(fontSize: 12, color: Colors.grey)),
                  if (c.claimAmount != null) ...[
                    const SizedBox(height: 2),
                    Text(c.formattedAmount,
                        style: const TextStyle(
                            fontSize: 13, fontWeight: FontWeight.w600, color: AppTheme.primary)),
                  ],
                ]),
              ),
              if (prob != null)
                Column(crossAxisAlignment: CrossAxisAlignment.end, children: [
                  Text(
                    '${(prob * 100).toStringAsFixed(0)}%',
                    style: TextStyle(
                      fontSize: 18,
                      fontWeight: FontWeight.w800,
                      color: prob >= 0.65
                          ? AppTheme.success
                          : prob >= 0.35
                              ? AppTheme.warning
                              : AppTheme.danger,
                    ),
                  ),
                  const Text('Erfolg', style: TextStyle(fontSize: 10, color: Colors.grey)),
                ]),
            ]),
            const SizedBox(height: 10),
            Row(children: [
              const Icon(Icons.access_time, size: 12, color: Colors.grey),
              const SizedBox(width: 4),
              Text(
                DateFormat('dd.MM.yyyy').format(c.updatedAt),
                style: const TextStyle(fontSize: 11, color: Colors.grey),
              ),
              const Spacer(),
              const Icon(Icons.chevron_right, size: 16, color: Colors.grey),
            ]),
          ]),
        ),
      ),
    );
  }
}
