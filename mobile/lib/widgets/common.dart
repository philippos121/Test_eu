import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';
import '../models/case.dart';
import '../theme.dart';

// ── Loading / Error helpers ──────────────────────────────────────────────────

class LoadingCenter extends StatelessWidget {
  const LoadingCenter({super.key});
  @override
  Widget build(BuildContext context) => const Center(
        child: CircularProgressIndicator(color: AppTheme.primary),
      );
}

class ErrorCenter extends StatelessWidget {
  final Object error;
  final VoidCallback? onRetry;
  const ErrorCenter({super.key, required this.error, this.onRetry});
  @override
  Widget build(BuildContext context) => Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            const Icon(Icons.error_outline, color: AppTheme.danger, size: 48),
            const SizedBox(height: 12),
            Text(error.toString(),
                textAlign: TextAlign.center,
                style: const TextStyle(color: AppTheme.danger)),
            if (onRetry != null) ...[
              const SizedBox(height: 16),
              OutlinedButton.icon(
                  onPressed: onRetry,
                  icon: const Icon(Icons.refresh),
                  label: const Text('Erneut versuchen')),
            ],
          ]),
        ),
      );
}

// ── Status Badge ─────────────────────────────────────────────────────────────

class StatusBadge extends StatelessWidget {
  final CaseStatus status;
  const StatusBadge({super.key, required this.status});

  Color get _bg {
    switch (status) {
      case CaseStatus.completed: return AppTheme.success.withOpacity(0.12);
      case CaseStatus.rejected: return AppTheme.danger.withOpacity(0.12);
      case CaseStatus.formGeneration: return AppTheme.primary.withOpacity(0.12);
      default: return Colors.orange.withOpacity(0.12);
    }
  }

  Color get _fg {
    switch (status) {
      case CaseStatus.completed: return AppTheme.success;
      case CaseStatus.rejected: return AppTheme.danger;
      case CaseStatus.formGeneration: return AppTheme.primary;
      default: return Colors.orange.shade800;
    }
  }

  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
        decoration: BoxDecoration(
          color: _bg,
          borderRadius: BorderRadius.circular(6),
        ),
        child: Text(
          status.label,
          style: TextStyle(color: _fg, fontSize: 11, fontWeight: FontWeight.w600),
        ),
      );
}

// ── Probability Indicator ────────────────────────────────────────────────────

class ProbabilityBar extends StatelessWidget {
  final double value; // 0..1
  final String? label;
  const ProbabilityBar({super.key, required this.value, this.label});

  Color get _color {
    if (value >= 0.65) return AppTheme.success;
    if (value >= 0.35) return AppTheme.warning;
    return AppTheme.danger;
  }

  @override
  Widget build(BuildContext context) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (label != null) ...[
            Text(label!, style: const TextStyle(fontSize: 12, color: Colors.grey)),
            const SizedBox(height: 4),
          ],
          ClipRRect(
            borderRadius: BorderRadius.circular(4),
            child: LinearProgressIndicator(
              value: value.clamp(0.0, 1.0),
              minHeight: 8,
              backgroundColor: Colors.grey.shade200,
              valueColor: AlwaysStoppedAnimation(_color),
            ),
          ),
          const SizedBox(height: 2),
          Text('${(value * 100).toStringAsFixed(0)}%',
              style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: _color)),
        ],
      );
}

// ── Score Pillar Card ────────────────────────────────────────────────────────

class PillarCard extends StatelessWidget {
  final String title;
  final double? value;
  final String description;
  const PillarCard({super.key, required this.title, required this.value, required this.description});

  @override
  Widget build(BuildContext context) {
    final v = value ?? 0.0;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(title, style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w700)),
          const SizedBox(height: 10),
          ProbabilityBar(value: v),
          const SizedBox(height: 8),
          Text(description, style: const TextStyle(fontSize: 11, color: Colors.grey)),
        ]),
      ),
    ).animate().fadeIn(duration: 300.ms).slideY(begin: 0.1);
  }
}

// ── Section Header ───────────────────────────────────────────────────────────

class SectionHeader extends StatelessWidget {
  final String title;
  final Widget? trailing;
  const SectionHeader({super.key, required this.title, this.trailing});

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.fromLTRB(0, 16, 0, 8),
        child: Row(children: [
          Text(title,
              style: const TextStyle(
                  fontSize: 13,
                  fontWeight: FontWeight.w700,
                  color: AppTheme.primary,
                  letterSpacing: 0.5)),
          const Spacer(),
          if (trailing != null) trailing!,
        ]),
      );
}

// ── Empty State ───────────────────────────────────────────────────────────────

class EmptyState extends StatelessWidget {
  final IconData icon;
  final String message;
  final String? buttonLabel;
  final VoidCallback? onButton;
  const EmptyState({super.key, required this.icon, required this.message, this.buttonLabel, this.onButton});

  @override
  Widget build(BuildContext context) => Center(
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          Icon(icon, size: 64, color: Colors.grey.shade300),
          const SizedBox(height: 16),
          Text(message,
              style: TextStyle(color: Colors.grey.shade500, fontSize: 15),
              textAlign: TextAlign.center),
          if (buttonLabel != null && onButton != null) ...[
            const SizedBox(height: 20),
            FilledButton(onPressed: onButton, child: Text(buttonLabel!)),
          ],
        ]),
      );
}

// ── Info Tile ─────────────────────────────────────────────────────────────────

class InfoTile extends StatelessWidget {
  final String label;
  final String? value;
  const InfoTile({super.key, required this.label, this.value});

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 6),
        child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          SizedBox(
            width: 130,
            child: Text(label,
                style: const TextStyle(fontSize: 13, color: Colors.grey, fontWeight: FontWeight.w500)),
          ),
          Expanded(
            child: Text(
              value ?? '—',
              style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w500),
            ),
          ),
        ]),
      );
}

// ── Step Progress ────────────────────────────────────────────────────────────

class CaseStepProgress extends StatelessWidget {
  final CaseStatus status;
  const CaseStepProgress({super.key, required this.status});

  static const _steps = [
    (CaseStatus.intake, 'Aufnahme'),
    (CaseStatus.applicabilityCheck, 'Anwendbarkeit'),
    (CaseStatus.caseAssessment, 'Prüfung'),
    (CaseStatus.evidenceCollection, 'Beweise'),
    (CaseStatus.formGeneration, 'Formular'),
    (CaseStatus.completed, 'Fertig'),
  ];

  @override
  Widget build(BuildContext context) {
    if (status == CaseStatus.rejected) {
      return Container(
        padding: const EdgeInsets.all(10),
        decoration: BoxDecoration(
          color: AppTheme.danger.withOpacity(0.08),
          borderRadius: BorderRadius.circular(8),
        ),
        child: const Row(children: [
          Icon(Icons.cancel_outlined, color: AppTheme.danger, size: 16),
          SizedBox(width: 8),
          Text('Abgelehnt', style: TextStyle(color: AppTheme.danger, fontWeight: FontWeight.w600)),
        ]),
      );
    }
    final idx = _steps.indexWhere((s) => s.$1 == status);
    final done = idx < 0 ? _steps.length - 1 : idx;
    return Row(
      children: List.generate(_steps.length, (i) {
        final active = i == done;
        final past = i < done;
        return Expanded(
          child: Row(children: [
            Column(children: [
              Container(
                width: 22, height: 22,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: past || active ? AppTheme.primary : Colors.grey.shade200,
                ),
                child: Icon(
                  past ? Icons.check : Icons.circle,
                  size: 14,
                  color: past || active ? Colors.white : Colors.grey.shade400,
                ),
              ),
              const SizedBox(height: 4),
              if (active)
                Text(_steps[i].$2,
                    style: const TextStyle(
                        fontSize: 9, color: AppTheme.primary, fontWeight: FontWeight.w600)),
            ]),
            if (i < _steps.length - 1)
              Expanded(
                child: Container(
                  height: 2,
                  color: i < done ? AppTheme.primary : Colors.grey.shade200,
                ),
              ),
          ]),
        );
      }),
    );
  }
}
