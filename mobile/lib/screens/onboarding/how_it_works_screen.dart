import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:go_router/go_router.dart';
import '../../theme.dart';

class HowItWorksScreen extends StatelessWidget {
  const HowItWorksScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppTheme.surface,
      appBar: AppBar(
        title: const Text('So funktioniert es'),
        leading: BackButton(
          onPressed: () => context.canPop() ? context.pop() : context.go('/'),
        ),
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(20),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [

          // ── Intro ──────────────────────────────────────────────────────────
          _SectionTitle('Das Verfahren'),
          const SizedBox(height: 6),
          Text(
            'In 5 einfachen Schritten reichen Sie Ihre Forderung nach der EU-Verordnung '
            '861/2007 ein — vollständig geführt durch unseren KI-Assistenten.',
            style: TextStyle(fontSize: 14, color: Colors.grey.shade700, height: 1.5),
          ).animate().fadeIn(delay: 100.ms),
          const SizedBox(height: 24),

          // ── Process Steps ──────────────────────────────────────────────────
          ..._processSteps.asMap().entries.map((e) =>
              _ProcessStep(step: e.value, index: e.key)
                  .animate().fadeIn(delay: (100 + e.key * 80).ms).slideX(begin: -0.05)),

          const SizedBox(height: 32),
          const Divider(),
          const SizedBox(height: 24),

          // ── Scoring Section ────────────────────────────────────────────────
          _SectionTitle('Unser Scoring-System'),
          const SizedBox(height: 8),
          Text(
            'Drei unabhängige Technologien berechnen Ihre Erfolgswahrscheinlichkeit.',
            style: TextStyle(fontSize: 13, color: Colors.grey.shade600, height: 1.4),
          ).animate().fadeIn(delay: 200.ms),
          const SizedBox(height: 20),

          ..._pillars.asMap().entries.map((e) =>
              _PillarCard(pillar: e.value)
                  .animate().fadeIn(delay: (250 + e.key * 100).ms).slideY(begin: 0.05)),

          const SizedBox(height: 28),

          // ── Formula card ───────────────────────────────────────────────────
          _FormulaCard().animate().fadeIn(delay: 600.ms),

          const SizedBox(height: 28),

          // ── Commission note ────────────────────────────────────────────────
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: AppTheme.success.withOpacity(0.06),
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: AppTheme.success.withOpacity(0.2)),
            ),
            child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
              const Icon(Icons.euro_outlined, color: AppTheme.success, size: 22),
              const SizedBox(width: 12),
              Expanded(
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  const Text('Nur im Erfolgsfall',
                      style: TextStyle(
                          fontWeight: FontWeight.w700, color: AppTheme.success, fontSize: 14)),
                  const SizedBox(height: 4),
                  Text(
                    '30% Provision des eingeklagten Betrags — ausschließlich bei '
                    'erfolgreicher Durchsetzung. Kein Erfolg, keine Kosten.',
                    style: TextStyle(fontSize: 12, color: Colors.grey.shade700, height: 1.4),
                  ),
                ]),
              ),
            ]),
          ).animate().fadeIn(delay: 650.ms),

          const SizedBox(height: 28),

          // ── CTA ────────────────────────────────────────────────────────────
          FilledButton.icon(
            onPressed: () => context.go('/auth/register'),
            icon: const Icon(Icons.arrow_forward),
            label: const Text('Jetzt loslegen'),
          ).animate().fadeIn(delay: 700.ms),
          const SizedBox(height: 8),
          OutlinedButton(
            onPressed: () => context.canPop() ? context.pop() : context.go('/'),
            child: const Text('Zurück'),
          ).animate().fadeIn(delay: 720.ms),
          const SizedBox(height: 40),
        ]),
      ),
    );
  }
}

// ── Data ─────────────────────────────────────────────────────────────────────

const _processSteps = [
  _Step(
    number: '1',
    title: 'Aufnahme',
    description: 'Schildern Sie Ihren Fall im Chat. Der Assistent stellt gezielte Fragen und füllt das Formular automatisch aus.',
    icon: Icons.chat_bubble_outline,
    color: Color(0xFF003399),
  ),
  _Step(
    number: '2',
    title: 'Anwendbarkeitsprüfung',
    description: 'Wir prüfen automatisch, ob EU-VO 861/2007 anwendbar ist — Betrag, grenzüberschreitender Bezug, Zuständigkeit.',
    icon: Icons.rule_outlined,
    color: Color(0xFF1565C0),
  ),
  _Step(
    number: '3',
    title: 'Fallbewertung',
    description: 'KI-Analyse des Sachverhalts: Beweise, Rechtslage, Gegnerposition. Erfolgswahrscheinlichkeit wird berechnet.',
    icon: Icons.psychology_outlined,
    color: Color(0xFF0277BD),
  ),
  _Step(
    number: '4',
    title: 'Beweisaufnahme',
    description: 'Laden Sie Rechnungen, Verträge, Liefernachweise und Mahnungen direkt in der App hoch.',
    icon: Icons.upload_file_outlined,
    color: Color(0xFF00695C),
  ),
  _Step(
    number: '5',
    title: 'Formular A',
    description: 'Das standardisierte EU-Klageformular A (VO 861/2007) wird automatisch ausgefüllt und als PDF bereitgestellt.',
    icon: Icons.picture_as_pdf_outlined,
    color: Color(0xFF1B5E20),
  ),
];

const _pillars = [
  _Pillar(
    emoji: '🤖',
    title: '100% KI-Assistent',
    subtitle: 'Large Language Model',
    description: 'GPT-basiertes Modell bewertet Gültigkeit, Beweisbarkeit und Zahlungswahrscheinlichkeit aus dem Falltext.',
    color: Color(0xFF003399),
  ),
  _Pillar(
    emoji: '⚖️',
    title: '100% Regelwerk',
    subtitle: 'Juristische Logik',
    description: 'Deterministische Regeln prüfen EU-Verordnung, Zuständigkeit, Fristen und Formvorschriften.',
    color: Color(0xFF6A0DAD),
  ),
  _Pillar(
    emoji: '🧠',
    title: '≤30% Neuronales Netz',
    subtitle: '40 Features → 32 → 16 → 3',
    description: 'Trainiert auf abgeschlossenen Fällen. Klassen: Vollerfolg / Teilerfolg / Misserfolg. Gewicht wächst mit Datenmenge.',
    color: Color(0xFF00695C),
  ),
];

// ── Formula Card ──────────────────────────────────────────────────────────────

class _FormulaCard extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: AppTheme.primary,
        borderRadius: BorderRadius.circular(16),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          const Icon(Icons.functions, color: AppTheme.accent, size: 18),
          const SizedBox(width: 8),
          Text('Scoring-Formel v4',
              style: TextStyle(
                  color: AppTheme.accent,
                  fontSize: 12,
                  fontWeight: FontWeight.w700,
                  letterSpacing: 0.5)),
        ]),
        const SizedBox(height: 14),
        _formulaLine('p_cash', 'p_valid × p_provable × p_payment'),
        const SizedBox(height: 6),
        _formulaLine('p_final', '(1 − w_NN) × p_cash  +  w_NN × p_NN'),
        const SizedBox(height: 6),
        _formulaLine('w_NN', '0.30 × (1 − e^(−n/25))  ≤ 30%'),
        const SizedBox(height: 14),
        Row(children: [
          _LegendDot(color: Colors.white70),
          Text('  p_valid  ', style: TextStyle(color: Colors.white70, fontSize: 11)),
          _LegendDot(color: Colors.white70),
          Text('  p_provable  ', style: TextStyle(color: Colors.white70, fontSize: 11)),
          _LegendDot(color: Colors.white70),
          Text('  p_payment', style: TextStyle(color: Colors.white70, fontSize: 11)),
        ]),
        const SizedBox(height: 4),
        Text('← alle drei aus LLM-Analyse · n = Anzahl Trainingsfälle',
            style: TextStyle(color: Colors.white38, fontSize: 10)),
      ]),
    );
  }

  Widget _formulaLine(String lhs, String rhs) => RichText(
        text: TextSpan(children: [
          TextSpan(
              text: '$lhs  =  ',
              style: TextStyle(
                  color: AppTheme.accent,
                  fontSize: 13,
                  fontWeight: FontWeight.w700,
                  fontFamily: 'monospace')),
          TextSpan(
              text: rhs,
              style: const TextStyle(
                  color: Colors.white,
                  fontSize: 13,
                  fontFamily: 'monospace')),
        ]),
      );
}

class _LegendDot extends StatelessWidget {
  final Color color;
  const _LegendDot({required this.color});
  @override
  Widget build(BuildContext context) =>
      Container(width: 8, height: 8, decoration: BoxDecoration(shape: BoxShape.circle, color: color));
}

// ── Sub-widgets ───────────────────────────────────────────────────────────────

class _SectionTitle extends StatelessWidget {
  final String text;
  const _SectionTitle(this.text);
  @override
  Widget build(BuildContext context) => Text(
        text,
        style: const TextStyle(
            fontSize: 17,
            fontWeight: FontWeight.w800,
            color: AppTheme.primary,
            letterSpacing: 0.2),
      );
}

class _Step {
  final String number, title, description;
  final IconData icon;
  final Color color;
  const _Step({required this.number, required this.title, required this.description, required this.icon, required this.color});
}

class _ProcessStep extends StatelessWidget {
  final _Step step;
  final int index;
  const _ProcessStep({required this.step, required this.index});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 16),
      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        // Number circle + connector line
        Column(children: [
          Container(
            width: 38, height: 38,
            decoration: BoxDecoration(color: step.color, shape: BoxShape.circle),
            child: Center(
              child: Text(step.number,
                  style: const TextStyle(
                      color: Colors.white, fontWeight: FontWeight.w800, fontSize: 15)),
            ),
          ),
          if (index < _processSteps.length - 1)
            Container(width: 2, height: 36, color: step.color.withOpacity(0.2)),
        ]),
        const SizedBox(width: 14),
        Expanded(
          child: Padding(
            padding: const EdgeInsets.only(top: 8),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Row(children: [
                Icon(step.icon, size: 16, color: step.color),
                const SizedBox(width: 6),
                Text(step.title,
                    style: TextStyle(
                        fontSize: 14, fontWeight: FontWeight.w700, color: step.color)),
              ]),
              const SizedBox(height: 4),
              Text(step.description,
                  style: TextStyle(
                      fontSize: 12, color: Colors.grey.shade600, height: 1.45)),
            ]),
          ),
        ),
      ]),
    );
  }
}

class _Pillar {
  final String emoji, title, subtitle, description;
  final Color color;
  const _Pillar({required this.emoji, required this.title, required this.subtitle, required this.description, required this.color});
}

class _PillarCard extends StatelessWidget {
  final _Pillar pillar;
  const _PillarCard({required this.pillar});

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: pillar.color.withOpacity(0.2)),
        boxShadow: [
          BoxShadow(color: pillar.color.withOpacity(0.06), blurRadius: 8, offset: const Offset(0, 3)),
        ],
      ),
      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Container(
          width: 46, height: 46,
          decoration: BoxDecoration(
            color: pillar.color.withOpacity(0.08),
            borderRadius: BorderRadius.circular(12),
          ),
          child: Center(child: Text(pillar.emoji, style: const TextStyle(fontSize: 22))),
        ),
        const SizedBox(width: 14),
        Expanded(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(pillar.title,
                style: TextStyle(
                    fontSize: 14, fontWeight: FontWeight.w700, color: pillar.color)),
            Text(pillar.subtitle,
                style: TextStyle(fontSize: 11, color: pillar.color.withOpacity(0.7))),
            const SizedBox(height: 6),
            Text(pillar.description,
                style: TextStyle(fontSize: 12, color: Colors.grey.shade600, height: 1.4)),
          ]),
        ),
      ]),
    );
  }
}
