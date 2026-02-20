import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';
import 'package:open_filex/open_filex.dart';
import 'package:path_provider/path_provider.dart';
import 'package:toastification/toastification.dart';
import '../../models/document.dart';
import '../../providers/cases_provider.dart';
import '../../services/case_service.dart';
import '../../services/api_client.dart';
import '../../theme.dart';
import '../../widgets/common.dart';

// ── Provider ─────────────────────────────────────────────────────────────────

final _documentsProvider = FutureProvider.family<List<CaseDocument>, String>(
    (ref, caseId) => CaseService().getDocuments(caseId));

// ── Screen ───────────────────────────────────────────────────────────────────

class DocumentsScreen extends ConsumerWidget {
  final String caseId;
  const DocumentsScreen({super.key, required this.caseId});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final docsAsync = ref.watch(_documentsProvider(caseId));
    final caseAsync = ref.watch(singleCaseProvider(caseId));

    final canGenerateFormA = caseAsync.valueOrNull?.status.name == 'form_generation' ||
        caseAsync.valueOrNull?.status.name == 'completed';

    return Scaffold(
      backgroundColor: AppTheme.surface,
      appBar: AppBar(title: const Text('Dokumente')),
      floatingActionButton: canGenerateFormA
          ? FloatingActionButton.extended(
              backgroundColor: AppTheme.primary,
              foregroundColor: Colors.white,
              icon: const Icon(Icons.picture_as_pdf),
              label: const Text('Formular A'),
              onPressed: () => _generateFormA(context, ref),
            )
          : null,
      body: docsAsync.when(
        loading: () => const LoadingCenter(),
        error: (e, _) =>
            ErrorCenter(error: e, onRetry: () => ref.invalidate(_documentsProvider(caseId))),
        data: (docs) {
          if (docs.isEmpty) {
            return const EmptyState(
              icon: Icons.insert_drive_file_outlined,
              message: 'Noch keine Dokumente.\nGenerieren Sie Formular A oder laden Sie Unterlagen hoch.',
            );
          }
          return RefreshIndicator(
            onRefresh: () async => ref.invalidate(_documentsProvider(caseId)),
            color: AppTheme.primary,
            child: ListView.builder(
              padding: const EdgeInsets.all(16),
              itemCount: docs.length,
              itemBuilder: (_, i) =>
                  _DocumentTile(doc: docs[i], caseId: caseId).animate().fadeIn(delay: (i * 60).ms),
            ),
          );
        },
      ),
    );
  }

  Future<void> _generateFormA(BuildContext context, WidgetRef ref) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Formular A generieren'),
        content: const Text('Soll das EU-Klageformular A (VO 861/2007) für diesen Fall generiert werden?'),
        actions: [
          TextButton(onPressed: () => ctx.pop(false), child: const Text('Abbrechen')),
          FilledButton(
            onPressed: () => ctx.pop(true),
            style: FilledButton.styleFrom(minimumSize: Size.zero, padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10)),
            child: const Text('Generieren'),
          ),
        ],
      ),
    );
    if (confirmed != true || !context.mounted) return;

    try {
      await CaseService().generateFormA(caseId);
      ref.invalidate(_documentsProvider(caseId));
      if (context.mounted) {
        toastification.show(
          context: context,
          title: const Text('Formular A erfolgreich erstellt'),
          type: ToastificationType.success,
        );
      }
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

class _DocumentTile extends StatefulWidget {
  final CaseDocument doc;
  final String caseId;
  const _DocumentTile({required this.doc, required this.caseId});
  @override
  State<_DocumentTile> createState() => _DocumentTileState();
}

class _DocumentTileState extends State<_DocumentTile> {
  bool _downloading = false;

  Future<void> _download() async {
    setState(() => _downloading = true);
    try {
      final url = await CaseService().getDocumentDownloadUrl(widget.caseId, widget.doc.id);
      final dir = await getTemporaryDirectory();
      final savePath = '${dir.path}/${widget.doc.filename}';
      await ApiClient.instance.download(url, savePath);
      if (mounted) {
        await OpenFilex.open(savePath);
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Download-Fehler: $e'), backgroundColor: AppTheme.danger),
        );
      }
    } finally {
      if (mounted) setState(() => _downloading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final doc = widget.doc;
    return Card(
      margin: const EdgeInsets.only(bottom: 10),
      child: ListTile(
        leading: CircleAvatar(
          backgroundColor: doc.isFormA ? AppTheme.primary.withOpacity(0.12) : Colors.orange.shade50,
          child: Icon(
            doc.isFormA ? Icons.article_outlined : Icons.upload_file_outlined,
            color: doc.isFormA ? AppTheme.primary : Colors.orange,
            size: 22,
          ),
        ),
        title: Text(doc.filename, style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600)),
        subtitle: Text(
          '${doc.typeLabel} · ${DateFormat('dd.MM.yyyy').format(doc.createdAt)}',
          style: const TextStyle(fontSize: 11),
        ),
        trailing: _downloading
            ? const SizedBox(
                width: 20, height: 20,
                child: CircularProgressIndicator(strokeWidth: 2, color: AppTheme.primary),
              )
            : IconButton(
                icon: const Icon(Icons.download_outlined),
                color: AppTheme.primary,
                onPressed: _download,
              ),
      ),
    );
  }
}
