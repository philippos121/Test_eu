import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:go_router/go_router.dart';
import '../../theme.dart';

class AgbScreen extends StatefulWidget {
  /// If [requireAccept] is true (default false), an "Accept" button appears
  /// and the callback [onAccepted] is called when the user taps it.
  final bool requireAccept;
  final VoidCallback? onAccepted;

  const AgbScreen({super.key, this.requireAccept = false, this.onAccepted});

  @override
  State<AgbScreen> createState() => _AgbScreenState();
}

class _AgbScreenState extends State<AgbScreen> {
  final _scrollCtrl = ScrollController();
  bool _hasScrolledToBottom = false;

  @override
  void initState() {
    super.initState();
    if (widget.requireAccept) {
      _scrollCtrl.addListener(_onScroll);
    }
  }

  void _onScroll() {
    if (_scrollCtrl.position.pixels >=
        _scrollCtrl.position.maxScrollExtent - 80) {
      if (!_hasScrolledToBottom) setState(() => _hasScrolledToBottom = true);
    }
  }

  @override
  void dispose() {
    _scrollCtrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppTheme.surface,
      appBar: AppBar(
        title: const Text('AGB & Datenschutz'),
        leading: BackButton(
          onPressed: () => context.canPop() ? context.pop() : context.go('/'),
        ),
      ),
      body: Column(
        children: [
          Expanded(
            child: SingleChildScrollView(
              controller: _scrollCtrl,
              padding: const EdgeInsets.fromLTRB(20, 20, 20, 40),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // ── Header ───────────────────────────────────────────────
                  _HeaderBanner().animate().fadeIn(duration: 400.ms),
                  const SizedBox(height: 28),

                  // ── Sections ─────────────────────────────────────────────
                  ..._sections.asMap().entries.map((e) =>
                      _AgbSection(section: e.value)
                          .animate()
                          .fadeIn(delay: (100 + e.key * 60).ms)
                          .slideY(begin: 0.04)),

                  const SizedBox(height: 8),

                  // ── Footer note ───────────────────────────────────────────
                  Container(
                    padding: const EdgeInsets.all(16),
                    decoration: BoxDecoration(
                      color: AppTheme.primary.withOpacity(0.04),
                      borderRadius: BorderRadius.circular(12),
                      border: Border.all(
                          color: AppTheme.primary.withOpacity(0.12)),
                    ),
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Icon(Icons.info_outline,
                            color: AppTheme.primary, size: 18),
                        const SizedBox(width: 10),
                        Expanded(
                          child: Text(
                            'Stand: Januar 2025. Diese AGB gelten für die Nutzung '
                            'des EU-Bagatellverfahren-Portals und der zugehörigen '
                            'mobilen Anwendung. Gerichtsstand ist München.',
                            style: TextStyle(
                                fontSize: 11,
                                color: Colors.grey.shade600,
                                height: 1.5),
                          ),
                        ),
                      ],
                    ),
                  ).animate().fadeIn(delay: 700.ms),
                ],
              ),
            ),
          ),

          // ── Accept button (optional) ────────────────────────────────────
          if (widget.requireAccept) _AcceptBar(
            enabled: _hasScrolledToBottom,
            onAccepted: widget.onAccepted,
          ),
        ],
      ),
    );
  }
}

// ── Header banner ─────────────────────────────────────────────────────────────

class _HeaderBanner extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        gradient: const LinearGradient(
          colors: [AppTheme.primary, Color(0xFF1565C0)],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
        borderRadius: BorderRadius.circular(16),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            const Icon(Icons.balance, color: AppTheme.accent, size: 22),
            const SizedBox(width: 10),
            const Text('Allgemeine Geschäftsbedingungen',
                style: TextStyle(
                    color: Colors.white,
                    fontSize: 15,
                    fontWeight: FontWeight.w800)),
          ]),
          const SizedBox(height: 8),
          Text(
            'EU-Bagatellverfahren-Portal · Version 1.0',
            style: TextStyle(color: Colors.white.withOpacity(0.75), fontSize: 12),
          ),
          const SizedBox(height: 4),
          Text(
            'Bitte lesen Sie diese Bedingungen sorgfältig durch.',
            style: TextStyle(color: Colors.white.withOpacity(0.65), fontSize: 11),
          ),
        ],
      ),
    );
  }
}

// ── Accept bar ────────────────────────────────────────────────────────────────

class _AcceptBar extends StatelessWidget {
  final bool enabled;
  final VoidCallback? onAccepted;

  const _AcceptBar({required this.enabled, this.onAccepted});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.fromLTRB(20, 12, 20, 24),
      decoration: BoxDecoration(
        color: Colors.white,
        border: Border(top: BorderSide(color: Colors.grey.shade200)),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withOpacity(0.06),
            blurRadius: 12,
            offset: const Offset(0, -4),
          ),
        ],
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (!enabled)
            Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: Text(
                'Bitte scrollen Sie zum Ende, um zuzustimmen.',
                style: TextStyle(fontSize: 11, color: Colors.grey.shade500),
              ),
            ),
          SizedBox(
            width: double.infinity,
            child: FilledButton.icon(
              onPressed: enabled ? onAccepted : null,
              icon: const Icon(Icons.check_circle_outline),
              label: const Text('Ich stimme den AGB zu'),
              style: FilledButton.styleFrom(
                padding: const EdgeInsets.symmetric(vertical: 14),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

// ── Collapsible section ───────────────────────────────────────────────────────

class _AgbSection extends StatefulWidget {
  final _Section section;
  const _AgbSection({required this.section});

  @override
  State<_AgbSection> createState() => _AgbSectionState();
}

class _AgbSectionState extends State<_AgbSection> {
  bool _expanded = false;

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
            color: _expanded
                ? AppTheme.primary.withOpacity(0.25)
                : Colors.grey.shade200),
        boxShadow: _expanded
            ? [
                BoxShadow(
                    color: AppTheme.primary.withOpacity(0.06),
                    blurRadius: 8,
                    offset: const Offset(0, 3))
              ]
            : [],
      ),
      child: Column(
        children: [
          InkWell(
            borderRadius: BorderRadius.circular(12),
            onTap: () => setState(() => _expanded = !_expanded),
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Row(children: [
                Container(
                  width: 32,
                  height: 32,
                  decoration: BoxDecoration(
                    color: widget.section.color.withOpacity(0.1),
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Icon(widget.section.icon,
                      size: 16, color: widget.section.color),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Text(
                    widget.section.title,
                    style: TextStyle(
                        fontSize: 14,
                        fontWeight: FontWeight.w700,
                        color: _expanded ? AppTheme.primary : Colors.grey.shade800),
                  ),
                ),
                Icon(
                  _expanded ? Icons.expand_less : Icons.expand_more,
                  color: Colors.grey.shade400,
                  size: 20,
                ),
              ]),
            ),
          ),
          if (_expanded)
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Divider(color: Colors.grey.shade100, height: 1),
                  const SizedBox(height: 12),
                  Text(
                    widget.section.content,
                    style: TextStyle(
                        fontSize: 12.5,
                        color: Colors.grey.shade700,
                        height: 1.6),
                  ),
                ],
              ),
            ),
        ],
      ),
    );
  }
}

// ── Data ──────────────────────────────────────────────────────────────────────

class _Section {
  final String title;
  final String content;
  final IconData icon;
  final Color color;
  const _Section({
    required this.title,
    required this.content,
    required this.icon,
    required this.color,
  });
}

const _sections = [
  _Section(
    title: '§ 1 Geltungsbereich und Anbieter',
    icon: Icons.gavel,
    color: Color(0xFF003399),
    content: 'Diese Allgemeinen Geschäftsbedingungen (AGB) regeln die Nutzung des '
        'EU-Bagatellverfahren-Portals und der zugehörigen mobilen Anwendung '
        '(nachfolgend „Dienst"). Anbieter ist die EU Portal GmbH, München '
        '(nachfolgend „wir" oder „Anbieter").\n\n'
        'Der Dienst richtet sich an natürliche und juristische Personen, die '
        'Forderungen nach der EU-Verordnung 861/2007 (Europäisches Verfahren '
        'für geringfügige Forderungen) einreichen möchten.',
  ),
  _Section(
    title: '§ 2 Leistungsbeschreibung',
    icon: Icons.description_outlined,
    color: Color(0xFF1565C0),
    content: 'Der Dienst bietet:\n\n'
        '• KI-gestützte Aufnahme und Prüfung von Forderungen nach VO (EG) 861/2007\n'
        '• Automatische Bewertung der Erfolgswahrscheinlichkeit (Scoring-System v4)\n'
        '• Ausfüllung des standardisierten EU-Klageformulars A\n'
        '• Verwaltung von Beweisdokumenten\n'
        '• Kommunikation zwischen Nutzer und KI-Assistent\n\n'
        'Der Dienst ist kein Rechtsanwalt und ersetzt keine anwaltliche Beratung. '
        'Das Scoring-System ist ein Hilfsmittel; eine Erfolgsgarantie wird nicht gegeben.',
  ),
  _Section(
    title: '§ 3 Registrierung und Nutzerkonto',
    icon: Icons.person_outlined,
    color: Color(0xFF0277BD),
    content: 'Zur Nutzung des Dienstes ist eine Registrierung erforderlich. '
        'Sie sind verpflichtet:\n\n'
        '• Wahrheitsgemäße und vollständige Angaben zu machen\n'
        '• Ihre Zugangsdaten geheim zu halten\n'
        '• Uns unverzüglich über eine unbefugte Nutzung zu informieren\n\n'
        'Wir behalten uns vor, Konten bei Verstößen gegen diese AGB oder bei '
        'Verdacht auf missbräuchliche Nutzung zu sperren oder zu löschen.',
  ),
  _Section(
    title: '§ 4 Provision und Vergütung',
    icon: Icons.euro_outlined,
    color: Color(0xFF00695C),
    content: 'Unser Dienst ist grundsätzlich kostenlos nutzbar. Im Erfolgsfall — '
        'd.h. bei erfolgreicher Durchsetzung der eingereichten Forderung — '
        'erheben wir eine Provision in Höhe von 30 % des eingezogenen Betrags.\n\n'
        'Definition „Erfolg": Eine Zahlung des Schuldners oder ein rechtskräftiges '
        'Urteil zu Ihren Gunsten, das zu einer tatsächlichen Einziehung geführt hat.\n\n'
        'Kein Erfolg bedeutet keine Kosten für Sie. Die Provisionsabrechnung erfolgt '
        'durch separate schriftliche Vereinbarung.',
  ),
  _Section(
    title: '§ 5 Pflichten der Nutzer',
    icon: Icons.rule_outlined,
    color: Color(0xFF6A0DAD),
    content: 'Sie verpflichten sich:\n\n'
        '• Ausschließlich wahrheitsgemäße Informationen einzugeben\n'
        '• Keine gefälschten oder manipulierten Dokumente hochzuladen\n'
        '• Den Dienst nicht für rechtsmissbräuchliche Zwecke zu nutzen\n'
        '• Die EU-Verordnung 861/2007 und nationale Verfahrensgesetze einzuhalten\n'
        '• Uns über wesentliche Änderungen des Falles unverzüglich zu informieren\n\n'
        'Bei Verstößen haften Sie für alle entstehenden Schäden.',
  ),
  _Section(
    title: '§ 6 Datenschutz (DSGVO)',
    icon: Icons.privacy_tip_outlined,
    color: Color(0xFF1B5E20),
    content: 'Wir verarbeiten Ihre personenbezogenen Daten gemäß der '
        'EU-Datenschutz-Grundverordnung (DSGVO) 2016/679.\n\n'
        'Verarbeitete Datenkategorien:\n'
        '• Stammdaten (Name, E-Mail, Land)\n'
        '• Falldaten (Forderungsbetrag, Sachverhalt, Gegner)\n'
        '• Dokumente (Rechnungen, Verträge, Beweise)\n'
        '• Nutzungsdaten (Logs, KI-Interaktionen)\n\n'
        'Rechtsgrundlage: Art. 6 Abs. 1 lit. b DSGVO (Vertragserfüllung).\n\n'
        'Ihre Rechte: Auskunft, Berichtigung, Löschung, Einschränkung, '
        'Datenübertragbarkeit, Widerspruch (Art. 15–21 DSGVO).\n\n'
        'Kontakt Datenschutzbeauftragter: datenschutz@eu-portal.eu',
  ),
  _Section(
    title: '§ 7 Haftungsausschluss',
    icon: Icons.shield_outlined,
    color: Color(0xFF37474F),
    content: 'Wir haften nicht für:\n\n'
        '• Den Ausgang eines gerichtlichen Verfahrens\n'
        '• Fehler in der KI-Analyse, die auf unvollständigen Nutzereingaben basieren\n'
        '• Technische Störungen von Drittanbietern (Gerichte, Behörden)\n'
        '• Verluste durch fehlerhafte oder gefälschte Nutzereingaben\n\n'
        'Unsere Haftung ist in jedem Fall auf die Höhe der von Ihnen gezahlten '
        'Vergütung begrenzt, soweit gesetzlich zulässig.',
  ),
  _Section(
    title: '§ 8 Anwendbares Recht und Gerichtsstand',
    icon: Icons.account_balance_outlined,
    color: Color(0xFF003399),
    content: 'Es gilt deutsches Recht unter Ausschluss des UN-Kaufrechts (CISG).\n\n'
        'Gerichtsstand für alle Streitigkeiten aus oder im Zusammenhang mit '
        'diesen AGB ist München, sofern Sie Kaufmann, juristische Person des '
        'öffentlichen Rechts oder öffentlich-rechtliches Sondervermögen sind.\n\n'
        'Für Verbraucher gelten die gesetzlichen Gerichtsstände.\n\n'
        'EU-Streitschlichtung: Die Europäische Kommission stellt unter '
        'https://ec.europa.eu/consumers/odr eine Online-Plattform zur '
        'Streitbeilegung (OS-Plattform) bereit.',
  ),
];
