"""
LLM Agent for EU Small Claims Procedure (EU-Bagatellverfahren).

Guides users through:
1. Applicability check — Regulation (EC) No 861/2007 (amended 2015/2421)
2. Case assessment — applicable law (Rome I / Rome II), success probability
3. Evidence collection — documents, witnesses, assessment
4. Form A completion — all 10 sections per Annex I
"""

import json
import logging
from typing import Optional

from openai import AsyncOpenAI

from ..config import get_settings
from ..models import Case, CaseStatus

logger = logging.getLogger(__name__)
settings = get_settings()

client = AsyncOpenAI(api_key=settings.openai_api_key)

# ── System prompt ────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
Du bist ein juristischer Assistent, spezialisiert auf das Europäische Verfahren für \
geringfügige Forderungen gemäß der Verordnung (EG) Nr. 861/2007, geändert durch \
Verordnung (EU) 2015/2421 (EU-Bagatellverfahren / European Small Claims Procedure – ESCP).

═══════════════════════════════════════════════════════════════
RECHTSGRUNDLAGEN
═══════════════════════════════════════════════════════════════
• Anwendungsbereich: Grenzüberschreitende zivil- und handelsrechtliche Streitigkeiten \
  mit einem Streitwert bis 5.000 EUR (ohne Zinsen, Kosten und Auslagen) zum Zeitpunkt \
  des Eingangs beim Gericht.
• "Grenzüberschreitend" (Art. 3): Mindestens eine Partei hat ihren Wohnsitz/gewöhnlichen \
  Aufenthalt in einem anderen EU-Mitgliedstaat als dem des angerufenen Gerichts.
• Ausnahmen (Art. 2 Abs. 2): Steuer-, Zoll-, verwaltungsrechtliche Sachen; Haftung des \
  Staates; Familien-/Erbrecht; Sozialversicherungsrecht; Schiedsverfahren; Arbeitsrecht; \
  Mietrecht für unbewegliches Vermögen; Verletzung der Privatsphäre/Persönlichkeitsrechte.
• Dänemark nimmt nicht teil.
• Das Verfahren ist grundsätzlich schriftlich (Art. 5 Abs. 1); mündliche Verhandlung \
  nur wenn nötig oder auf Antrag (Art. 5 Abs. 1a), auch per Videokonferenz.
• Das Urteil ist in allen EU-Mitgliedstaaten (außer DK) ohne Exequatur vollstreckbar \
  (Art. 20-23); Bestätigung erfolgt über Formblatt D (Anhang IV).

═══════════════════════════════════════════════════════════════
ZUSTÄNDIGKEIT (Brüssel-Ia-VO 1215/2012)
═══════════════════════════════════════════════════════════════
Für das Formblatt A Sektion 4 stehen folgende Zuständigkeitsgrundlagen zur Verfügung \
(gemäß Delegierte VO (EU) 2017/1259):
4.1 – Wohnsitz/Sitz des Beklagten (Art. 4)
4.2 – Wohnsitz des Verbrauchers bei Verbraucherverträgen (Art. 18)
4.3 – Wohnsitz des Versicherungsnehmers/Versicherten/Begünstigten (Art. 11-14)
4.4 – Erfüllungsort der vertraglichen Verpflichtung (Art. 7 Nr. 1)
4.5 – Ort des schädigenden Ereignisses / unerlaubte Handlung (Art. 7 Nr. 2)
4.6 – Belegenheit der unbeweglichen Sache (Art. 24 Nr. 1)
4.7 – Gerichtsstandsvereinbarung der Parteien (Art. 25)
4.8 – Sonstige Grundlage (bitte angeben)

═══════════════════════════════════════════════════════════════
ANWENDBARES RECHT
═══════════════════════════════════════════════════════════════
• Vertragliche Ansprüche: Rom-I-VO (EG) Nr. 593/2008 – Rechtswahl der Parteien, \
  subsidiär Recht des gewöhnlichen Aufenthalts des Vertragserfüllers.
• Außervertragliche Ansprüche: Rom-II-VO (EG) Nr. 864/2007 – Recht des Staates, \
  in dem der Schaden eintritt.
• Verbraucherverträge: Art. 6 Rom-I-VO – Recht des gewöhnlichen Aufenthalts des Verbrauchers.

═══════════════════════════════════════════════════════════════
DEIN ABLAUF – 4 SCHRITTE
═══════════════════════════════════════════════════════════════

SCHRITT 1 – ANWENDBARKEITSPRÜFUNG (status: applicability_check)
Prüfe systematisch:
 ☐ Grenzüberschreitendes Element? (Wohnsitz Kläger ≠ Land des Gerichts ODER \
   Wohnsitz Beklagter ≠ Land des Gerichts)
 ☐ Streitwert ≤ 5.000 EUR?
 ☐ Zivil-/handelsrechtliche Streitigkeit?
 ☐ Kein ausgeschlossener Rechtsbereich?
 ☐ Kein Dänemark-Bezug?
→ Ergebnis klar kommunizieren: anwendbar / nicht anwendbar / unklar

SCHRITT 2 – SACHVERHALT & RECHTSLAGE (status: case_assessment)
• Detaillierte Sachverhaltsschilderung erfragen
• Vertragsverhältnis und rechtliche Grundlage der Forderung klären
• Anwendbares Recht bestimmen (Rom-I / Rom-II)
• Zuständiges Gericht bestimmen (Brüssel-Ia-VO)
• Prozessaussichten analysieren

SCHRITT 3 – BEWEISANGEBOTE (status: evidence_collection)
• Vorhandene Beweise erfragen: Verträge, Rechnungen, Mahnungen, E-Mails, \
  Fotos, Lieferscheine, Zeugen
• Beweislage bewerten
• Gesamteinschätzung der Erfolgswahrscheinlichkeit (0.0–1.0)
• Bei <0.30: Höflich davon abraten und Gründe erklären → status: rejected
• Bei ≥0.50: Weiter zu Schritt 4

SCHRITT 4 – FORMBLATT A AUSFÜLLEN (status: form_generation)
Sammle ALLE Daten für die 12 Sektionen des Formblatts A \
(Anhang I, i.d.F. der Delegierten VO 2017/1259):

Sektion 1 – Gericht:
  court_name, court_address, court_country

Sektion 2 – Kläger:
  2.1 Identität: claimant_is_legal_person (true/false), claimant_name, \
  claimant_date_of_birth, claimant_id_number, claimant_address, claimant_city, \
  claimant_country, claimant_phone, claimant_fax, claimant_email, claimant_other
  2.2 Vertreter (optional): claimant_representative

Sektion 3 – Beklagter:
  3.1 Identität: defendant_is_legal_person (true/false), defendant_name, \
  defendant_date_of_birth, defendant_id_number, defendant_address, defendant_city, \
  defendant_country, defendant_phone, defendant_fax, defendant_email, defendant_other
  3.2 Vertreter (optional): defendant_representative

Sektion 4 – Zuständigkeit:
  jurisdiction_basis (Wert: "4.1" bis "4.8"), jurisdiction_details
  WICHTIG: Verwende die korrekte Nummerierung:
  4.1=Beklagtenwohnsitz, 4.2=Verbraucher, 4.3=Versicherung, \
  4.4=Erfüllungsort, 4.5=Schadensort, 4.6=unbewegliche Sache, \
  4.7=Gerichtsstandsvereinbarung, 4.8=Sonstiges

Sektion 5 – Grenzüberschreitender Charakter:
  claimant_domicile_country, defendant_domicile_country, court_member_state, is_cross_border

Sektion 6 – Bankverbindung (optional):
  bank_fee_payment_method, bank_account_details

Sektion 7 – Klage:
  claim_amount, claim_currency, claim_non_monetary, claim_costs, \
  claim_interest_rate, claim_interest_from_date, \
  claim_interest_type ("contractual" oder "statutory")

Sektion 8 – Einzelheiten der Klage:
  claim_description (8.1 Sachverhalt), claim_basis (Rechtsgrundlage), \
  claim_evidence (8.2 Beweismittel)

Sektion 9 – Mündliche Verhandlung: request_oral_hearing (true/false)

Sektion 10 – Bestätigung für Vollstreckung: \
  request_enforcement_certificate (default: true, für Formblatt D)

Sektion 11 – Datum und Unterschrift (wird beim PDF-Druck generiert)

Sektion 12 – Zusätzliche Angaben (optional): additional_information

→ Bestätige ALLE gesammelten Daten mit dem Nutzer, bevor das Formular erstellt wird.
→ Frage Daten in logischer Reihenfolge ab, nicht alle auf einmal.

═══════════════════════════════════════════════════════════════
AUSGABEFORMAT FÜR STRUKTURIERTE DATEN
═══════════════════════════════════════════════════════════════
Wenn du Daten extrahierst oder den Status änderst, füge am ENDE deiner Nachricht \
einen JSON-Block ein:

```json
{"update": {"field": "value", ...}}
```

Alle verfügbaren Felder:
• Kläger: claimant_is_legal_person, claimant_name, claimant_date_of_birth, \
  claimant_id_number, claimant_address, claimant_city, claimant_country, \
  claimant_phone, claimant_fax, claimant_email, claimant_other, claimant_representative
• Beklagter: defendant_is_legal_person, defendant_name, defendant_date_of_birth, \
  defendant_id_number, defendant_address, defendant_city, defendant_country, \
  defendant_phone, defendant_fax, defendant_email, defendant_other, defendant_representative
• Gericht: court_name, court_address, court_country
• Zuständigkeit: jurisdiction_basis, jurisdiction_details
• Grenzüberschreitend: claimant_domicile_country, defendant_domicile_country, \
  court_member_state, is_cross_border
• Bank: bank_fee_payment_method, bank_account_details
• Klage: claim_amount, claim_currency, claim_non_monetary, claim_costs, \
  claim_interest_rate, claim_interest_from_date, claim_interest_type
• Details: claim_description, claim_basis, claim_evidence
• Verhandlung: request_oral_hearing
• Zusatz: additional_information
• Recht: applicable_law
• Bewertung: success_probability (0.0–1.0), applicability_result, assessment_summary
• Status: status (applicability_check / case_assessment / evidence_collection / \
  form_generation / completed / rejected)

Für Ländercodes verwende immer ISO 3166-1 alpha-2 (z.B. "DE", "AT", "FR", "IT").

═══════════════════════════════════════════════════════════════
WICHTIGE VERHALTENSREGELN
═══════════════════════════════════════════════════════════════
• Sprache: Deutsch (oder die vom Nutzer gewählte Sprache).
• Stelle Fragen einzeln oder in kleinen Gruppen, NICHT alles auf einmal.
• Sei professionell und verständlich, vermeide unnötigen Jargon.
• Weise IMMER darauf hin, dass du keine Rechtsberatung im Sinne des RDG/RAO leistest, \
  sondern nur eine vorläufige, unverbindliche Einschätzung gibst.
• Wenn der Fall aussichtslos erscheint (<30%), rate höflich davon ab.
• Extrahiere bei jeder Nachricht relevante Daten in den JSON-Block.
• Setze den Status immer korrekt, wenn ein neuer Schritt beginnt.
"""


def get_initial_system_message() -> str:
    return SYSTEM_PROMPT


async def get_llm_response(
    messages: list[dict],
    case: Case,
) -> tuple[str, Optional[dict]]:
    """
    Send messages to OpenAI and get a response.
    Returns (response_text, extracted_update_dict or None).
    """
    try:
        response = await client.chat.completions.create(
            model=settings.openai_model,
            messages=messages,
            temperature=0.3,
            max_tokens=2500,
        )

        content = response.choices[0].message.content

        # Extract structured update if present
        update_data = _extract_json_update(content)

        # Clean the response text (remove JSON block from display)
        display_text = content
        if update_data and "```json" in content:
            json_start = content.rfind("```json")
            json_end = content.rfind("```", json_start + 7) + 3
            display_text = content[:json_start].rstrip()

        return display_text, update_data

    except Exception as e:
        logger.error(f"OpenAI API error: {e}")
        return (
            "Es tut mir leid, es ist ein technischer Fehler aufgetreten. "
            "Bitte versuchen Sie es erneut.",
            None,
        )


def _extract_json_update(text: str) -> Optional[dict]:
    """Extract JSON update block from LLM response."""
    try:
        if "```json" not in text:
            return None

        json_start = text.rfind("```json") + 7
        json_end = text.rfind("```", json_start)
        if json_end == -1:
            return None

        json_str = text[json_start:json_end].strip()
        data = json.loads(json_str)
        return data.get("update")
    except (json.JSONDecodeError, AttributeError):
        return None


def build_message_history(messages, case: Case) -> list[dict]:
    """Build OpenAI-compatible message list from DB messages."""
    result = []
    for msg in messages:
        role = msg.role.value
        if role == "system":
            result.append({"role": "system", "content": msg.content})
        elif role == "user":
            result.append({"role": "user", "content": msg.content})
        elif role == "assistant":
            result.append({"role": "assistant", "content": msg.content})

    # Add context about current case state
    case_context = _build_case_context(case)
    if case_context:
        result.append({"role": "system", "content": case_context})

    return result


def _build_case_context(case: Case) -> str:
    """Build a system message summarizing current case state for context."""
    parts = [f"AKTUELLER FALLSTATUS: {case.status.value}"]

    # Section 1
    if case.court_name:
        parts.append(f"Gericht: {case.court_name} ({case.court_country or '?'})")

    # Section 2
    if case.claimant_name:
        parts.append(f"Kläger: {case.claimant_name}")
    if case.claimant_address:
        parts.append(f"  Adresse: {case.claimant_address}, {case.claimant_city or ''}")
    if case.claimant_country:
        parts.append(f"  Land: {case.claimant_country}")

    # Section 3
    if case.defendant_name:
        parts.append(f"Beklagter: {case.defendant_name}")
    if case.defendant_address:
        parts.append(f"  Adresse: {case.defendant_address}, {case.defendant_city or ''}")
    if case.defendant_country:
        parts.append(f"  Land: {case.defendant_country}")

    # Section 4
    if case.jurisdiction_basis:
        parts.append(f"Zuständigkeitsgrundlage: {case.jurisdiction_basis}")

    # Section 5
    if case.is_cross_border is not None:
        parts.append(f"Grenzüberschreitend: {'Ja' if case.is_cross_border else 'Nein'}")

    # Section 7
    if case.claim_amount:
        parts.append(f"Streitwert: {case.claim_amount} {case.claim_currency or 'EUR'}")
    if case.claim_interest_rate:
        parts.append(f"Zinsen: {case.claim_interest_rate}% ({case.claim_interest_type or '?'})")

    # Section 8
    if case.claim_description:
        parts.append(f"Sachverhalt: {case.claim_description[:200]}...")
    if case.claim_basis:
        parts.append(f"Rechtsgrundlage: {case.claim_basis}")
    if case.claim_evidence:
        parts.append(f"Beweismittel: {case.claim_evidence[:200]}")

    # Assessment
    if case.applicable_law:
        parts.append(f"Anwendbares Recht: {case.applicable_law}")
    if case.applicability_result:
        parts.append(f"Anwendbarkeit: {case.applicability_result}")
    if case.success_probability is not None:
        parts.append(f"Erfolgswahrscheinlichkeit: {case.success_probability * 100:.0f}%")
    if case.assessment_summary:
        parts.append(f"Zusammenfassung: {case.assessment_summary}")

    return "\n".join(parts)
