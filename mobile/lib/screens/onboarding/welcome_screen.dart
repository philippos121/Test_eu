import 'dart:math' as math;
import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:go_router/go_router.dart';
import '../../theme.dart';

class WelcomeScreen extends StatefulWidget {
  const WelcomeScreen({super.key});
  @override
  State<WelcomeScreen> createState() => _WelcomeScreenState();
}

class _WelcomeScreenState extends State<WelcomeScreen>
    with SingleTickerProviderStateMixin {
  late final AnimationController _starCtrl;

  @override
  void initState() {
    super.initState();
    _starCtrl = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 24),
    )..repeat();
  }

  @override
  void dispose() {
    _starCtrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppTheme.primary,
      body: SafeArea(
        child: Column(children: [
          // ── Hero ───────────────────────────────────────────────────────────
          Expanded(
            flex: 5,
            child: Stack(alignment: Alignment.center, children: [
              // Subtle radial glow behind the flag
              Container(
                width: 280,
                height: 280,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  gradient: RadialGradient(colors: [
                    Colors.white.withOpacity(0.08),
                    Colors.transparent,
                  ]),
                ),
              ),
              // Rotating EU star ring
              AnimatedBuilder(
                animation: _starCtrl,
                builder: (_, __) => CustomPaint(
                  size: const Size(200, 200),
                  painter: _EUFlagPainter(_starCtrl.value),
                ),
              ),
              // Centre wordmark
              Column(mainAxisSize: MainAxisSize.min, children: [
                Text(
                  'EU',
                  style: TextStyle(
                    fontSize: 32,
                    fontWeight: FontWeight.w900,
                    color: Colors.white,
                    letterSpacing: 6,
                  ),
                ),
                Text(
                  'Forderungen',
                  style: TextStyle(
                    fontSize: 13,
                    fontWeight: FontWeight.w400,
                    color: AppTheme.accent,
                    letterSpacing: 2,
                  ),
                ),
              ]),
            ]),
          ),

          // ── White card section ────────────────────────────────────────────
          Expanded(
            flex: 7,
            child: Container(
              width: double.infinity,
              decoration: const BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.vertical(top: Radius.circular(32)),
              ),
              padding: const EdgeInsets.fromLTRB(24, 32, 24, 16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'Geringfügige Forderungen\ndurchsetzen — einfach.',
                    style: TextStyle(
                      fontSize: 22,
                      fontWeight: FontWeight.w800,
                      color: AppTheme.primary,
                      height: 1.25,
                    ),
                  ).animate().fadeIn(delay: 200.ms).slideY(begin: 0.1),
                  const SizedBox(height: 6),
                  Text(
                    'EU-Verordnung 861/2007 · Forderungen bis EUR 5.000 · grenzüberschreitend',
                    style: TextStyle(fontSize: 12, color: Colors.grey.shade600, height: 1.4),
                  ).animate().fadeIn(delay: 300.ms),
                  const SizedBox(height: 22),

                  // Value proposition chips
                  Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: const [
                      _ValueChip(icon: Icons.psychology_outlined, label: 'KI-Assistent'),
                      _ValueChip(icon: Icons.gavel_outlined, label: 'Juristisch geprüft'),
                      _ValueChip(icon: Icons.public, label: '27 EU-Staaten'),
                      _ValueChip(icon: Icons.description_outlined, label: 'Formular A auto'),
                    ],
                  ).animate().fadeIn(delay: 380.ms),
                  const SizedBox(height: 20),

                  // How-it-works link
                  GestureDetector(
                    onTap: () => context.push('/how-it-works'),
                    child: Container(
                      padding: const EdgeInsets.all(14),
                      decoration: BoxDecoration(
                        color: AppTheme.primary.withOpacity(0.04),
                        borderRadius: BorderRadius.circular(12),
                        border: Border.all(color: AppTheme.primary.withOpacity(0.12)),
                      ),
                      child: Row(children: [
                        const Icon(Icons.auto_awesome_outlined,
                            color: AppTheme.primary, size: 20),
                        const SizedBox(width: 10),
                        Expanded(
                          child: Text(
                            'KI-Scoring, Regelwerk & Neuronales Netz im Einsatz',
                            style: TextStyle(
                                fontSize: 13,
                                color: AppTheme.primary,
                                fontWeight: FontWeight.w500),
                          ),
                        ),
                        const Icon(Icons.chevron_right,
                            color: AppTheme.primary, size: 18),
                      ]),
                    ),
                  ).animate().fadeIn(delay: 450.ms),

                  const Spacer(),

                  // CTA buttons
                  FilledButton(
                    onPressed: () => context.go('/auth/register'),
                    child: const Text('Kostenlos starten'),
                  ).animate().fadeIn(delay: 520.ms).slideY(begin: 0.15),
                  const SizedBox(height: 10),
                  OutlinedButton(
                    onPressed: () => context.go('/auth/login'),
                    child: const Text('Bereits registriert? Anmelden'),
                  ).animate().fadeIn(delay: 560.ms),
                  const SizedBox(height: 14),
                  Center(
                    child: GestureDetector(
                      onTap: () => context.push('/agb'),
                      child: Text(
                        'AGB & Datenschutz lesen',
                        style: TextStyle(
                          fontSize: 12,
                          color: Colors.grey.shade500,
                          decoration: TextDecoration.underline,
                        ),
                      ),
                    ),
                  ).animate().fadeIn(delay: 600.ms),
                  const SizedBox(height: 8),
                ],
              ),
            ),
          ),
        ]),
      ),
    );
  }
}

// ── EU Flag Painter ────────────────────────────────────────────────────────────

class _EUFlagPainter extends CustomPainter {
  final double progress;
  const _EUFlagPainter(this.progress);

  @override
  void paint(Canvas canvas, Size size) {
    final cx = size.width / 2;
    final cy = size.height / 2;
    final R = size.width * 0.38;
    final starR = size.width * 0.055;

    final goldPaint = Paint()..color = AppTheme.accent;
    final glowPaint = Paint()
      ..color = AppTheme.accent.withOpacity(0.18)
      ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 8);

    for (int k = 0; k < 12; k++) {
      // Slight slow rotation
      final angle = (k * 30 - 90 + progress * 5) * math.pi / 180;
      final sx = cx + R * math.cos(angle);
      final sy = cy + R * math.sin(angle);

      // Glow
      canvas.drawCircle(Offset(sx, sy), starR * 1.8, glowPaint);
      // Star dot
      _drawStar(canvas, Offset(sx, sy), starR, goldPaint);
    }
  }

  void _drawStar(Canvas canvas, Offset center, double r, Paint p) {
    final path = Path();
    for (int i = 0; i < 5; i++) {
      final outer = (i * 72 - 90) * math.pi / 180;
      final inner = ((i * 72 + 36) - 90) * math.pi / 180;
      final ox = center.dx + r * math.cos(outer);
      final oy = center.dy + r * math.sin(outer);
      final ix = center.dx + r * 0.4 * math.cos(inner);
      final iy = center.dy + r * 0.4 * math.sin(inner);
      if (i == 0) path.moveTo(ox, oy); else path.lineTo(ox, oy);
      path.lineTo(ix, iy);
    }
    path.close();
    canvas.drawPath(path, p);
  }

  @override
  bool shouldRepaint(_EUFlagPainter old) => old.progress != progress;
}

// ── Value Chip ─────────────────────────────────────────────────────────────────

class _ValueChip extends StatelessWidget {
  final IconData icon;
  final String label;
  const _ValueChip({required this.icon, required this.label});

  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
        decoration: BoxDecoration(
          color: AppTheme.primary.withOpacity(0.06),
          borderRadius: BorderRadius.circular(20),
          border: Border.all(color: AppTheme.primary.withOpacity(0.15)),
        ),
        child: Row(mainAxisSize: MainAxisSize.min, children: [
          Icon(icon, size: 14, color: AppTheme.primary),
          const SizedBox(width: 5),
          Text(label,
              style: const TextStyle(
                  fontSize: 12, color: AppTheme.primary, fontWeight: FontWeight.w500)),
        ]),
      );
}
