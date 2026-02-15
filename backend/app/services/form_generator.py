"""
PDF Form Generator for EU Small Claims Procedure.

Generates Form A (Klageformblatt / Claim Form) per Annex I of
Regulation (EC) No 861/2007 as amended by Regulation (EU) 2015/2421,
with updated annexes from Delegated Regulation (EU) 2017/1259.

This generator reproduces the EXACT structure of the official form
as published on the European e-Justice Portal.
"""

import os
import uuid
from datetime import date

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
    PageBreak,
    KeepTogether,
)

from ..config import get_settings
from ..models import Case

settings = get_settings()

# ── Styles ───────────────────────────────────────────────────────────────────

def _get_styles():
    base = getSampleStyleSheet()
    return {
        "main_title": ParagraphStyle(
            "FMainTitle", parent=base["Heading1"], fontSize=12,
            alignment=TA_CENTER, spaceAfter=1 * mm, spaceBefore=0,
            fontName="Helvetica-Bold",
        ),
        "sub_title": ParagraphStyle(
            "FSubTitle", parent=base["Heading2"], fontSize=11,
            alignment=TA_CENTER, spaceAfter=1 * mm, spaceBefore=0,
            fontName="Helvetica-Bold",
        ),
        "regulation_ref": ParagraphStyle(
            "FRegRef", parent=base["Normal"], fontSize=8,
            alignment=TA_CENTER, spaceAfter=4 * mm,
        ),
        "section_header": ParagraphStyle(
            "FSecHead", parent=base["Normal"], fontSize=10,
            spaceBefore=6 * mm, spaceAfter=2 * mm,
            fontName="Helvetica-Bold",
        ),
        "section_header_italic": ParagraphStyle(
            "FSecHeadIt", parent=base["Normal"], fontSize=10,
            spaceBefore=6 * mm, spaceAfter=2 * mm,
            fontName="Helvetica-Oblique",
        ),
        "instruction": ParagraphStyle(
            "FInstr", parent=base["Normal"], fontSize=8, leading=10,
            spaceAfter=3 * mm, fontName="Helvetica-Oblique",
        ),
        "normal": ParagraphStyle(
            "FNorm", parent=base["Normal"], fontSize=9, leading=12,
        ),
        "normal_bold": ParagraphStyle(
            "FNormBold", parent=base["Normal"], fontSize=9, leading=12,
            fontName="Helvetica-Bold",
        ),
        "field_label": ParagraphStyle(
            "FLabel", parent=base["Normal"], fontSize=9, leading=12,
        ),
        "field_value": ParagraphStyle(
            "FValue", parent=base["Normal"], fontSize=9, leading=12,
            fontName="Helvetica-Bold",
        ),
        "small": ParagraphStyle(
            "FSmall", parent=base["Normal"], fontSize=7.5, leading=10,
            textColor=colors.HexColor("#555555"),
        ),
        "footer": ParagraphStyle(
            "FFoot", parent=base["Normal"], fontSize=7,
            textColor=colors.grey, alignment=TA_CENTER,
        ),
        "box_header": ParagraphStyle(
            "FBoxHead", parent=base["Normal"], fontSize=9, leading=12,
            fontName="Helvetica-BoldOblique",
        ),
        "important_header": ParagraphStyle(
            "FImpHead", parent=base["Normal"], fontSize=9,
            alignment=TA_CENTER, spaceAfter=2 * mm, spaceBefore=4 * mm,
            fontName="Helvetica-Bold",
        ),
    }


def _val(v, fallback: str = "") -> str:
    if v is None or v == "":
        return fallback
    return str(v)


def _checkbox(checked: bool) -> str:
    return "\u2611" if checked else "\u2610"


def _bordered_box(content_elements: list, S: dict) -> Table:
    """Wrap content elements in a bordered box like the official form."""
    inner = []
    for el in content_elements:
        inner.append([el])
    t = Table(inner, colWidths=[170 * mm])
    t.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.5, colors.black),
        ("LEFTPADDING", (0, 0), (-1, -1), 4 * mm),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4 * mm),
        ("TOPPADDING", (0, 0), (0, 0), 3 * mm),
        ("BOTTOMPADDING", (0, -1), (-1, -1), 3 * mm),
        ("TOPPADDING", (0, 1), (-1, -1), 1 * mm),
        ("BOTTOMPADDING", (0, 0), (-1, -2), 1 * mm),
    ]))
    return t


def _field_row(label: str, value: str, S: dict) -> Paragraph:
    """Single field: label + value on one line."""
    return Paragraph(f"{label} <b>{value}</b>", S["normal"])


def _field_with_space(label: str, value: str, S: dict) -> list:
    """Field label followed by value, with blank space below."""
    return [
        Paragraph(label, S["field_label"]),
        Paragraph(f"<b>{value}</b>" if value else "&nbsp;", S["field_value"]),
        Spacer(1, 2 * mm),
    ]


def _checkbox_row(label: str, checked: bool, S: dict) -> Paragraph:
    """A checkbox row."""
    return Paragraph(f"{_checkbox(checked)} {label}", S["normal"])


# ── Country helpers ──────────────────────────────────────────────────────────

EU_COUNTRIES = {
    "AT": "Österreich", "BE": "Belgien", "BG": "Bulgarien",
    "HR": "Kroatien", "CY": "Zypern", "CZ": "Tschechien",
    "EE": "Estland", "FI": "Finnland", "FR": "Frankreich",
    "DE": "Deutschland", "GR": "Griechenland", "HU": "Ungarn",
    "IE": "Irland", "IT": "Italien", "LV": "Lettland",
    "LT": "Litauen", "LU": "Luxemburg", "MT": "Malta",
    "NL": "Niederlande", "PL": "Polen", "PT": "Portugal",
    "RO": "Rumänien", "SK": "Slowakei", "SI": "Slowenien",
    "ES": "Spanien", "SE": "Schweden",
}


def _country(code: str | None) -> str:
    if not code:
        return ""
    return EU_COUNTRIES.get(code.upper(), code)


# ── Main generator ───────────────────────────────────────────────────────────

def generate_form_a(case: Case) -> tuple[str, str]:
    """
    Generate Form A (Klageformblatt) as PDF matching the official EU form.
    Returns (filename, filepath).
    """
    os.makedirs(settings.generated_forms_dir, exist_ok=True)
    filename = f"Formblatt_A_{uuid.uuid4().hex[:8]}.pdf"
    filepath = os.path.join(settings.generated_forms_dir, filename)

    doc = SimpleDocTemplate(
        filepath, pagesize=A4,
        topMargin=15 * mm, bottomMargin=15 * mm,
        leftMargin=18 * mm, rightMargin=18 * mm,
    )
    S = _get_styles()
    el: list = []

    # =====================================================================
    # PAGE 1: Title + Important Information + Section 1 + Section 2 start
    # =====================================================================

    # ── Header ──
    el.append(Paragraph(
        "EUROPÄISCHES VERFAHREN FÜR GERINGFÜGIGE FORDERUNGEN",
        S["main_title"],
    ))
    el.append(Paragraph("FORMBLATT A", S["sub_title"]))
    el.append(Paragraph("KLAGEFORMBLATT", S["sub_title"]))
    el.append(Paragraph(
        "(Artikel 4 Absatz 1 der Verordnung (EG) Nr. 861/2007 des Europäischen "
        "Parlaments und des Rates zur Einführung eines europäischen Verfahrens "
        "für geringfügige Forderungen)",
        S["regulation_ref"],
    ))

    # ── Aktenzeichen box ──
    el.append(_bordered_box([
        Paragraph("<b>Aktenzeichen (*):</b>", S["normal"]),
        Spacer(1, 3 * mm),
        Paragraph("<b>Eingang bei Gericht __/__/____ (*)</b>", S["normal"]),
        Paragraph("(*) Vom Gericht auszufüllen.", S["small"]),
    ], S))

    el.append(Spacer(1, 4 * mm))

    # ── Important Information ──
    el.append(Paragraph("WICHTIGE INFORMATIONEN", S["important_header"]))
    el.append(Paragraph(
        "<b>BITTE LESEN SIE DIE ANLEITUNG ZU BEGINN JEDES ABSCHNITTS — "
        "SIE ERLEICHTERT IHNEN DAS AUSFÜLLEN DIESES FORMBLATTS</b>",
        S["small"],
    ))
    el.append(Spacer(1, 2 * mm))

    # ── Section 1: Gericht ──
    el.append(Paragraph("1. Gericht", S["section_header"]))
    el.append(Paragraph(
        "In diesem Feld ist das Gericht anzugeben, bei dem Sie Ihre Klage "
        "einreichen. Bei der Auswahl des Gerichts ist auf die Zuständigkeit "
        "des Gerichts zu achten. In Abschnitt 4 finden Sie eine nicht "
        "abschließende Aufzählung von Kriterien, auf die sich die gerichtliche "
        "Zuständigkeit gründen kann.",
        S["instruction"],
    ))

    court_box = []
    court_box.append(Paragraph(
        "<i>1. Bei welchem Gericht reichen Sie die Klage ein?</i>",
        S["box_header"],
    ))
    court_box.extend(_field_with_space(
        "1.1. Name:", _val(case.court_name), S
    ))
    court_box.extend(_field_with_space(
        "1.2. Straße und Hausnummer/Postfach:", _val(case.court_address), S
    ))
    court_box.extend(_field_with_space(
        "1.3. Postleitzahl und Ort:", _val(case.claimant_city if not case.court_address else ""), S
    ))
    court_box.extend(_field_with_space(
        "1.4. Land:",
        _country(case.court_country or case.court_member_state),
        S,
    ))
    el.append(_bordered_box(court_box, S))

    # ── Section 2: Kläger ──
    el.append(Paragraph("2. Kläger", S["section_header"]))
    el.append(Paragraph(
        "In diesem Feld sind Sie als Kläger und gegebenenfalls Ihr Vertreter "
        "anzugeben. Sie sind nicht verpflichtet, sich durch einen Rechtsanwalt "
        "oder sonstigen Rechtsbeistand vertreten zu lassen.",
        S["instruction"],
    ))

    el.append(PageBreak())

    # =====================================================================
    # PAGE 2: Section 2 (continued) + Section 3 start
    # =====================================================================

    claimant_box = []
    claimant_box.append(Paragraph(
        "<i>2. Angaben zum Kläger</i>", S["box_header"],
    ))
    claimant_box.extend(_field_with_space(
        "2.1. Nachname, Vorname/Name des Unternehmens oder der Organisation:",
        _val(case.claimant_name), S,
    ))
    claimant_box.extend(_field_with_space(
        "2.2. Persönliche Identifikationsnummer oder Passnummer/Registrierungsnummer:",
        _val(case.claimant_id_number), S,
    ))
    claimant_box.extend(_field_with_space(
        "2.3. Straße und Hausnummer/Postfach:",
        _val(case.claimant_address), S,
    ))
    claimant_box.extend(_field_with_space(
        "2.4. Postleitzahl und Ort:",
        _val(case.claimant_city), S,
    ))
    claimant_box.extend(_field_with_space(
        "2.5. Land:", _country(case.claimant_country), S,
    ))
    claimant_box.extend(_field_with_space(
        "2.6. Telefon (*):", _val(case.claimant_phone), S,
    ))
    claimant_box.extend(_field_with_space(
        "2.7. E-Mail (*):", _val(case.claimant_email), S,
    ))
    claimant_box.extend(_field_with_space(
        "2.8. Ggf. Vertreter des Klägers und Kontaktadresse(*):",
        _val(case.claimant_representative), S,
    ))
    claimant_box.extend(_field_with_space(
        "2.9. Sonstige Angaben (*):", _val(case.claimant_other), S,
    ))
    el.append(_bordered_box(claimant_box, S))

    # ── Section 3: Beklagter ──
    el.append(Spacer(1, 4 * mm))
    el.append(Paragraph("3. Beklagter", S["section_header"]))
    el.append(Paragraph(
        "Geben Sie in diesem Feld bitte den Beklagten und, falls bekannt, "
        "seinen Vertreter an. Auch der Beklagte ist nicht verpflichtet, sich "
        "durch einen Rechtsanwalt oder sonstigen Rechtsbeistand vertreten zu lassen.",
        S["instruction"],
    ))

    defendant_box = []
    defendant_box.append(Paragraph(
        "<i>3. Angaben zum Beklagten</i>", S["box_header"],
    ))
    defendant_box.extend(_field_with_space(
        "3.1. Nachname, Vorname/Name des Unternehmens oder der Organisation:",
        _val(case.defendant_name), S,
    ))
    defendant_box.extend(_field_with_space(
        "3.2. Persönliche Identifikationsnummer oder Passnummer/Registrierungsnummer:",
        _val(case.defendant_id_number), S,
    ))

    el.append(_bordered_box(defendant_box, S))

    el.append(PageBreak())

    # =====================================================================
    # PAGE 3: Section 3 (cont.) + Section 4 + Section 5
    # =====================================================================

    defendant_box2 = []
    defendant_box2.extend(_field_with_space(
        "3.3. Straße und Hausnummer/Postfach:",
        _val(case.defendant_address), S,
    ))
    defendant_box2.extend(_field_with_space(
        "3.4. Postleitzahl und Ort:", _val(case.defendant_city), S,
    ))
    defendant_box2.extend(_field_with_space(
        "3.5. Land:", _country(case.defendant_country), S,
    ))
    defendant_box2.extend(_field_with_space(
        "3.6. Telefon (*):", _val(case.defendant_phone), S,
    ))
    defendant_box2.extend(_field_with_space(
        "3.7. E-Mail (*):", _val(case.defendant_email), S,
    ))
    defendant_box2.extend(_field_with_space(
        "3.8. Vertreter des Beklagten, falls bekannt, und Kontaktdaten(*):",
        _val(case.defendant_representative), S,
    ))
    defendant_box2.extend(_field_with_space(
        "3.9. Sonstige Angaben (*):", _val(case.defendant_other), S,
    ))
    el.append(_bordered_box(defendant_box2, S))

    el.append(Paragraph("(*) Fakultativ.", S["small"]))

    # ── Section 4: Gerichtliche Zuständigkeit ──
    el.append(Spacer(1, 4 * mm))
    el.append(Paragraph(
        "<i>4. Gerichtliche Zuständigkeit</i>", S["section_header_italic"],
    ))
    el.append(Paragraph(
        "Die Klage ist bei dem Gericht einzureichen, das für ihre Bearbeitung "
        "zuständig ist. Das Gericht muss nach den Vorschriften der Verordnung "
        "(EU) Nr. 1215/2012 des Europäischen Parlaments und des Rates zuständig sein.",
        S["instruction"],
    ))

    jb = case.jurisdiction_basis or ""

    jurisdiction_box = []
    jurisdiction_box.append(Paragraph(
        "<i>4. Nach welchem Kriterium ist das Gericht Ihres Erachtens zuständig?</i>",
        S["box_header"],
    ))
    jurisdiction_items = [
        ("4.1", "Wohnsitz des Beklagten"),
        ("4.2", "Wohnsitz des Verbrauchers"),
        ("4.3", "In Versicherungssachen, Wohnsitz des Versicherungsnehmers, "
                "des Versicherten oder des Begünstigten"),
        ("4.4", "Leistungsort"),
        ("4.5", "Ort des schädigenden Ereignisses"),
        ("4.6", "Ort, an dem die unbewegliche Sache belegen ist"),
        ("4.7", "Gerichtsstandsvereinbarung zwischen den Parteien"),
        ("4.8", "Sonstiges (bitte angeben)"),
    ]
    for code, label in jurisdiction_items:
        checked = jb.startswith(code)
        jurisdiction_box.append(Paragraph(
            f"{_checkbox(checked)} {code}. {label}", S["normal"],
        ))

    if case.jurisdiction_details:
        jurisdiction_box.append(Spacer(1, 2 * mm))
        jurisdiction_box.append(Paragraph(
            f"Erläuterung: <b>{case.jurisdiction_details}</b>", S["normal"],
        ))

    el.append(_bordered_box(jurisdiction_box, S))

    # ── Section 5: Grenzüberschreitende Rechtssache ──
    el.append(Spacer(1, 4 * mm))
    el.append(Paragraph(
        "<i>5. Grenzüberschreitende Rechtssache</i>",
        S["section_header_italic"],
    ))
    el.append(Paragraph(
        "Sie können das europäische Verfahren für geringfügige Forderungen "
        "nur in Anspruch nehmen, wenn Ihre Rechtssache einen Auslandsbezug "
        "aufweist. Dies ist der Fall, wenn mindestens eine der Parteien ihren "
        "Wohnsitz oder gewöhnlichen Aufenthalt in einem anderen Mitgliedstaat "
        "als dem des Gerichts hat.",
        S["instruction"],
    ))

    cross_border_box = []
    cross_border_box.append(Paragraph(
        "<i>5. Grenzüberschreitender Sachverhalt</i>", S["box_header"],
    ))
    cross_border_box.extend(_field_with_space(
        "5.1. Staat des Wohnsitzes oder gewöhnlichen Aufenthalts des Klägers:",
        _country(case.claimant_domicile_country or case.claimant_country),
        S,
    ))
    cross_border_box.extend(_field_with_space(
        "5.2. Staat des Wohnsitzes oder gewöhnlichen Aufenthalts des Beklagten:",
        _country(case.defendant_domicile_country or case.defendant_country),
        S,
    ))
    cross_border_box.extend(_field_with_space(
        "5.3. Mitgliedstaat des Gerichts:",
        _country(case.court_member_state or case.court_country),
        S,
    ))
    el.append(_bordered_box(cross_border_box, S))

    el.append(Paragraph("(*) Fakultativ.", S["small"]))

    el.append(PageBreak())

    # =====================================================================
    # PAGE 4: Section 6 + Section 7 intro
    # =====================================================================

    # ── Section 6: Bankverbindung ──
    el.append(Paragraph(
        "<i>6. Bankverbindung (fakultativ)</i>", S["section_header_italic"],
    ))
    el.append(Paragraph(
        "Unter Nummer 6.1 können Sie dem Gericht mitteilen, wie Sie die "
        "Gerichtsgebühr entrichten wollen. Unter Nummer 6.2 können Sie angeben, "
        "wie der Beklagte zahlen soll.",
        S["instruction"],
    ))

    fee_method = _val(case.bank_fee_payment_method, "").lower()
    bank_box = []
    bank_box.append(Paragraph(
        "<i>6. Bankverbindung</i>", S["box_header"],
    ))
    bank_box.append(Paragraph(
        "6.1. Wie werden Sie die Gerichtsgebühren begleichen?", S["normal"],
    ))
    bank_box.append(_checkbox_row(
        "6.1.1. Überweisung", "überweisung" in fee_method, S,
    ))
    bank_box.append(_checkbox_row(
        "6.1.2. Kreditkarte (bitte Anlage ausfüllen)",
        "kreditkarte" in fee_method or "credit" in fee_method, S,
    ))
    bank_box.append(_checkbox_row(
        "6.1.3. Einzug mittels Lastschrift von Ihrem Bankkonto (bitte Anlage ausfüllen)",
        "lastschrift" in fee_method or "einzug" in fee_method, S,
    ))
    bank_box.extend(_field_with_space(
        "6.1.4. Andere Zahlungsmethode (bitte angeben):",
        _val(case.bank_fee_payment_method)
        if fee_method and "überweisung" not in fee_method
        and "kreditkarte" not in fee_method
        and "lastschrift" not in fee_method
        else "",
        S,
    ))
    bank_box.append(Spacer(1, 3 * mm))
    bank_box.append(Paragraph(
        "6.2. Auf welches Konto soll der Beklagte den geforderten bzw. "
        "zuerkannten Betrag überweisen?",
        S["normal"],
    ))
    bank_box.extend(_field_with_space(
        "6.2.1. Kontoinhaber:",
        _val(getattr(case, "bank_account_holder", None)),
        S,
    ))
    bank_box.extend(_field_with_space(
        "6.2.2. Name der Bank, BIC oder andere Bankkennung:",
        _val(getattr(case, "bank_name_bic", None)),
        S,
    ))
    bank_box.extend(_field_with_space(
        "6.2.3. Kontonummer/IBAN:",
        _val(getattr(case, "bank_iban", None)),
        S,
    ))
    el.append(_bordered_box(bank_box, S))

    # ── Section 7: Forderung ──
    el.append(Spacer(1, 4 * mm))
    el.append(Paragraph("7. Forderung", S["section_header"]))
    el.append(Paragraph(
        "<b>Anwendungsbereich</b>: Beachten Sie bitte, dass das europäische "
        "Verfahren für geringfügige Forderungen einen begrenzten "
        "Anwendungsbereich hat. Über Klagen, deren Streitwert 5000 EUR "
        "überschreitet oder deren Gegenstand in Artikel 2 der Verordnung (EG) "
        "Nr. 861/2007 aufgeführt ist, kann im Rahmen dieses Verfahrens nicht "
        "verhandelt werden.",
        S["instruction"],
    ))
    el.append(Paragraph(
        "<b>Geldforderung oder andere Forderung</b>: Geben Sie bitte an, ob "
        "Sie eine Geldforderung und/oder eine andere (nicht auf eine "
        "Geldzahlung gerichtete) Forderung geltend machen, und füllen Sie "
        "dann Nummer 7.1 und/oder Nummer 7.2 aus.",
        S["instruction"],
    ))

    el.append(PageBreak())

    # =====================================================================
    # PAGE 5: Section 7 form fields
    # =====================================================================

    currency = _val(case.claim_currency, "EUR")
    has_monetary = bool(case.claim_amount)
    has_non_monetary = bool(case.claim_non_monetary)

    claim_box = []
    claim_box.append(Paragraph(
        "<i>7. Ihre Forderung</i>", S["box_header"],
    ))

    # 7.1 Geldforderung
    claim_box.append(_checkbox_row(
        "7.1. Geldforderung", has_monetary, S,
    ))
    claim_box.extend(_field_with_space(
        "   7.1.1. Hauptforderung (ohne Zinsen und Kosten):",
        f"{case.claim_amount:,.2f}" if case.claim_amount else "",
        S,
    ))
    claim_box.append(Paragraph("   7.1.2. Währung", S["normal"]))

    # Currency checkboxes
    currencies = [
        ("EUR", "Euro (EUR)"), ("BGN", "bulgarischer Lev (BGN)"),
        ("HRK", "Kroatische Kuna (HRK)"), ("CZK", "tschechische Krone (CZK)"),
        ("HUF", "ungarischer Forint (HUF)"), ("GBP", "Pfund Sterling (GBP)"),
        ("PLN", "polnischer Zloty (PLN)"), ("RON", "rumänischer Leu (RON)"),
        ("SEK", "schwedische Krone (SEK)"),
    ]
    currency_lines = []
    line = []
    for code, label in currencies:
        line.append(f"{_checkbox(currency == code)} {label}")
        if len(line) == 3:
            currency_lines.append("&nbsp;&nbsp;&nbsp;".join(line))
            line = []
    if line:
        currency_lines.append("&nbsp;&nbsp;&nbsp;".join(line))
    for cl in currency_lines:
        claim_box.append(Paragraph(f"   {cl}", S["normal"]))

    claim_box.append(Spacer(1, 3 * mm))

    # 7.2 Andere Forderung
    claim_box.append(_checkbox_row(
        "7.2. Andere Forderung:", has_non_monetary, S,
    ))
    claim_box.extend(_field_with_space(
        "   7.2.1. Geben Sie bitte genau an, was Sie fordern:",
        _val(case.claim_non_monetary), S,
    ))
    claim_box.extend(_field_with_space(
        "   7.2.2. Geschätzter Wert der Forderung:",
        f"{case.claim_non_monetary_value:,.2f}" if getattr(case, "claim_non_monetary_value", None) else "",
        S,
    ))

    claim_box.append(Spacer(1, 3 * mm))

    # 7.3 Verfahrenskosten
    request_costs = getattr(case, "claim_request_costs", None)
    claim_box.append(Paragraph(
        "7.3. Fordern Sie die Erstattung der Verfahrenskosten?", S["normal"],
    ))
    claim_box.append(_checkbox_row(
        "7.3.1. Ja", bool(request_costs or case.claim_costs), S,
    ))
    claim_box.append(_checkbox_row(
        "7.3.2. Nein", not (request_costs or case.claim_costs), S,
    ))
    claim_box.extend(_field_with_space(
        "7.3.3. Falls ja, machen Sie bitte genaue Angaben zur Art der Kosten "
        "und zur Höhe der Forderung bzw. der bisher entstandenen Kosten:",
        _val(case.claim_costs), S,
    ))

    el.append(_bordered_box(claim_box, S))

    el.append(Spacer(1, 3 * mm))

    # 7.4 Zinsen
    has_interest = bool(case.claim_interest_rate)
    is_contractual = case.claim_interest_type == "contractual"
    is_statutory = case.claim_interest_type == "statutory"

    interest_box = []
    interest_box.append(Paragraph("7.4. Fordern Sie Zinsen?", S["normal"]))
    interest_box.append(_checkbox_row("Ja", has_interest, S))
    interest_box.append(_checkbox_row("Nein", not has_interest, S))

    if has_interest:
        interest_box.append(Paragraph("Wenn ja,", S["normal"]))
        interest_box.append(_checkbox_row(
            "Vertraglicher Zinssatz? Wenn ja, gehen Sie zu Nummer 7.4.1.",
            is_contractual, S,
        ))
        interest_box.append(_checkbox_row(
            "gesetzlicher Zinssatz? Wenn ja, gehen Sie zu Nummer 7.4.2.",
            is_statutory, S,
        ))

        if is_contractual:
            interest_box.append(Paragraph(
                "7.4.1. im Falle eines vertraglichen Zinssatzes", S["normal"],
            ))
            interest_box.append(Paragraph(
                f"   1. der Zinssatz beträgt: <b>{case.claim_interest_rate}%</b>",
                S["normal"],
            ))
        else:
            interest_box.append(Paragraph(
                "7.4.2. Zinsen im Falle eines gesetzlichen:", S["normal"],
            ))

        interest_box.append(Paragraph(
            f"   2. Zinsen ab: <b>{_val(case.claim_interest_from_date, '(Datum)')}</b>",
            S["normal"],
        ))
        interest_to = _val(getattr(case, "claim_interest_to_date", None))
        if interest_to:
            interest_box.append(Paragraph(
                f"   bis: <b>{interest_to}</b>", S["normal"],
            ))
        else:
            interest_box.append(_checkbox_row(
                "bis zum Tag der Erfüllung der Hauptforderung", True, S,
            ))

    # 7.5 Zinsen auf Kosten
    interest_box.append(Spacer(1, 2 * mm))
    interest_on_costs = getattr(case, "claim_interest_on_costs", False)
    interest_box.append(Paragraph(
        "7.5. Fordern Sie Zinsen auf die Kosten?", S["normal"],
    ))
    interest_box.append(_checkbox_row("Ja", bool(interest_on_costs), S))
    interest_box.append(_checkbox_row("Nein", not bool(interest_on_costs), S))

    el.append(_bordered_box(interest_box, S))

    el.append(PageBreak())

    # =====================================================================
    # PAGE 6: Section 8 + Section 9
    # =====================================================================

    # ── Section 8: Einzelheiten zur Klage ──
    el.append(Paragraph(
        "<i>8. Einzelheiten zur Klage</i>", S["section_header_italic"],
    ))
    el.append(Paragraph(
        "Unter Nummer 8.1 sollten Sie kurz den Gegenstand Ihrer Klage "
        "beschreiben. Unter Nummer 8.2 sollten Sie etwaige Beweismittel "
        "beschreiben. Dabei kann es sich beispielsweise um schriftliche "
        "Beweismittel (Verträge, Quittungen usw.) oder um mündliche oder "
        "schriftliche Zeugenaussagen handeln.",
        S["instruction"],
    ))

    details_box = []
    details_box.append(Paragraph(
        "<i>8. Einzelheiten zur Klage</i>", S["box_header"],
    ))
    details_box.append(Paragraph(
        "8.1. Bitte begründen Sie Ihre Klage; geben Sie beispielsweise an, "
        "was wann und wo passiert ist.",
        S["normal"],
    ))
    details_box.append(Spacer(1, 2 * mm))

    desc = _val(case.claim_description)
    if desc:
        for para in desc.split("\n"):
            if para.strip():
                details_box.append(Paragraph(f"<b>{para.strip()}</b>", S["normal"]))
    else:
        details_box.append(Spacer(1, 10 * mm))

    # Legal basis (part of 8.1 description)
    if case.claim_basis:
        details_box.append(Spacer(1, 2 * mm))
        details_box.append(Paragraph(
            f"<b>Rechtliche Grundlage:</b> {case.claim_basis}", S["normal"],
        ))

    # Applicable law
    if case.applicable_law:
        details_box.append(Paragraph(
            f"<b>Anwendbares Recht:</b> {case.applicable_law}", S["normal"],
        ))

    details_box.append(Spacer(1, 4 * mm))

    # 8.2 Beweismittel
    details_box.append(Paragraph(
        "8.2. Beschreiben Sie bitte, welche Beweismittel Sie zur Begründung "
        "Ihrer Klage vorlegen möchten, und geben Sie bitte an, welche Aspekte "
        "der Klage dadurch begründet werden.",
        S["normal"],
    ))
    details_box.append(Spacer(1, 2 * mm))

    has_evidence = bool(case.claim_evidence)
    details_box.append(_checkbox_row(
        "8.2.1. Urkundenbeweis — bitte unten näher ausführen",
        has_evidence, S,
    ))
    details_box.append(_checkbox_row(
        "8.2.2. Zeugenbeweis — bitte unten näher ausführen", False, S,
    ))
    details_box.append(_checkbox_row(
        "8.2.3. Sonstiges Beweismittel — bitte unten näher ausführen", False, S,
    ))

    if has_evidence:
        details_box.append(Spacer(1, 2 * mm))
        for para in case.claim_evidence.split("\n"):
            if para.strip():
                details_box.append(Paragraph(
                    f"<b>{para.strip()}</b>", S["normal"],
                ))

    el.append(_bordered_box(details_box, S))

    # ── Section 9: Mündliche Verhandlung ──
    el.append(Spacer(1, 4 * mm))
    el.append(Paragraph(
        "<i>9. Mündliche Verhandlung</i>", S["section_header_italic"],
    ))
    el.append(Paragraph(
        "Beachten Sie bitte, dass das europäische Verfahren für geringfügige "
        "Forderungen ein schriftliches Verfahren ist. Das Gericht kann jedoch "
        "beschließen, eine mündliche Verhandlung anzuberaumen, wenn eine "
        "Entscheidung auf der Grundlage der schriftlichen Beweismittel seines "
        "Erachtens nicht möglich ist.",
        S["instruction"],
    ))

    hearing_box = []
    oral = bool(case.request_oral_hearing)
    hearing_box.append(Paragraph(
        "9.1. Wünschen Sie eine mündliche Verhandlung?", S["normal"],
    ))
    hearing_box.append(_checkbox_row("Ja", oral, S))
    hearing_box.append(_checkbox_row("Nein", not oral, S))

    reasons = _val(getattr(case, "oral_hearing_reasons", None))
    if reasons:
        hearing_box.append(Paragraph(
            f"Wenn ja, führen Sie bitte die Gründe an(*): <b>{reasons}</b>",
            S["normal"],
        ))

    el.append(_bordered_box(hearing_box, S))

    el.append(Spacer(1, 3 * mm))

    attendance_box = []
    personal = bool(getattr(case, "request_personal_attendance", False))
    attendance_box.append(Paragraph(
        "9.2 Falls das Gericht beschließt, eine mündliche Verhandlung "
        "anzuberaumen, wollen Sie persönlich teilnehmen?",
        S["normal"],
    ))
    attendance_box.append(_checkbox_row("Ja", personal, S))
    attendance_box.append(_checkbox_row("Nein", not personal, S))
    att_reasons = _val(getattr(case, "personal_attendance_reasons", None))
    if att_reasons:
        attendance_box.append(Paragraph(
            f"Geben Sie bitte die Gründe an(*): <b>{att_reasons}</b>",
            S["normal"],
        ))
    el.append(_bordered_box(attendance_box, S))

    el.append(PageBreak())

    # =====================================================================
    # PAGE 7: Section 10 + Section 11
    # =====================================================================

    # ── Section 10: Zustellung ──
    el.append(Paragraph(
        "<i>10. Zustellung von Schriftstücken und Kommunikation mit dem Gericht</i>",
        S["section_header_italic"],
    ))
    el.append(Paragraph(
        "Verfahrensschriftstücke wie Ihre Klage, die Erwiderung des Beklagten, "
        "eine etwaige Widerklage und das Urteil können den Parteien per Post "
        "oder auf elektronischem Wege zugestellt werden, wenn das Gericht über "
        "entsprechende technische Mittel verfügt und dies nach dem "
        "Verfahrensrecht des Mitgliedstaats zulässig ist.",
        S["instruction"],
    ))

    e_service = bool(getattr(case, "consent_electronic_service", False))
    e_comm = bool(getattr(case, "consent_electronic_communication", False))

    service_box = []
    service_box.append(Paragraph(
        "10.1. Stimmen Sie dem Einsatz elektronischer Kommunikationsmittel "
        "für die Zustellung der Erwiderung des Beklagten, einer etwaigen "
        "Widerklage und des Urteils zu?",
        S["normal"],
    ))
    service_box.append(_checkbox_row("Ja", e_service, S))
    service_box.append(_checkbox_row("Nein", not e_service, S))
    service_box.append(Spacer(1, 2 * mm))
    service_box.append(Paragraph(
        "10.2. Stimmen Sie dem Einsatz elektronischer Kommunikationsmittel "
        "für die Übermittlung anderer schriftlicher Mitteilungen als der "
        "unter Nummer 10.1 genannten Schriftstücke zu?",
        S["normal"],
    ))
    service_box.append(_checkbox_row("Ja", e_comm, S))
    service_box.append(_checkbox_row("Nein", not e_comm, S))

    el.append(_bordered_box(service_box, S))

    # ── Section 11: Bestätigung ──
    el.append(Spacer(1, 4 * mm))
    el.append(Paragraph(
        "<i>11. Bestätigung</i>", S["section_header_italic"],
    ))
    el.append(Paragraph(
        "Ein in einem Mitgliedstaat im Rahmen des europäischen Verfahrens für "
        "geringfügige Forderungen erlassenes Urteil kann in einem anderen "
        "Mitgliedstaat anerkannt und vollstreckt werden. Haben Sie die Absicht, "
        "die Anerkennung und Vollstreckung in einem anderen Mitgliedstaat als "
        "dem des Gerichts zu beantragen, so können Sie in diesem Formblatt das "
        "Gericht darum ersuchen, nach Erlass eines Urteils zu Ihren Gunsten "
        "eine Bestätigung dieses Urteils auszustellen.",
        S["instruction"],
    ))

    cert = case.request_enforcement_certificate in (True, None)
    cert_box = []
    cert_box.append(Paragraph(
        "<i>11.1 Bestätigung</i>", S["box_header"],
    ))
    cert_box.append(Paragraph(
        f"{_checkbox(cert)} Ich bitte das Gericht um Ausstellung einer "
        "Bestätigung des Urteils.",
        S["normal"],
    ))
    el.append(_bordered_box(cert_box, S))

    el.append(Spacer(1, 3 * mm))

    # 11.2 Language
    cert_lang = _val(getattr(case, "certificate_language", None))
    lang_box = []
    lang_box.append(Paragraph(
        "11.2 Ich bitte das Gericht um Ausstellung einer Bestätigung in "
        "einer anderen Sprache als der Verfahrenssprache, nämlich:",
        S["normal"],
    ))

    eu_languages = [
        "Bulgarisch", "Spanisch", "Tschechisch",
        "Deutsch", "Estnisch", "Griechisch",
        "Englisch", "Französisch", "Kroatisch",
        "Italienisch", "Lettisch", "Litauisch",
        "Ungarisch", "Maltesisch", "Niederländisch",
        "Polnisch", "Portugiesisch", "Rumänisch",
        "Slowakisch", "Slowenisch", "Finnisch",
        "Schwedisch",
    ]

    lang_lines = []
    line = []
    for lang in eu_languages:
        checked = cert_lang.lower() == lang.lower() if cert_lang else False
        line.append(f"{_checkbox(checked)} {lang}")
        if len(line) == 3:
            lang_lines.append("&nbsp;&nbsp;&nbsp;".join(line))
            line = []
    if line:
        lang_lines.append("&nbsp;&nbsp;&nbsp;".join(line))
    for ll in lang_lines:
        lang_box.append(Paragraph(ll, S["normal"]))

    el.append(_bordered_box(lang_box, S))

    el.append(PageBreak())

    # =====================================================================
    # PAGE 8: Section 12 — Date and Signature
    # =====================================================================

    el.append(Paragraph(
        "<i>12. Datum und Unterschrift</i>", S["section_header_italic"],
    ))
    el.append(Paragraph(
        "Vergessen Sie bitte nicht, auf der letzten Seite des Formblatts "
        "Ihren Namen deutlich lesbar einzutragen und die Klage zu "
        "unterzeichnen und zu datieren.",
        S["instruction"],
    ))

    sig_box = []
    sig_box.append(Paragraph(
        "<i>12. Datum und Unterschrift</i>", S["box_header"],
    ))
    sig_box.append(Paragraph(
        "Ich beantrage hiermit den Erlass eines Urteils gegen den Beklagten "
        "auf der Grundlage meiner Klage.",
        S["normal"],
    ))
    sig_box.append(Paragraph(
        "Ich erkläre, dass ich die vorstehenden Angaben nach meinem bestem "
        "Wissen und Gewissen gemacht habe.",
        S["normal"],
    ))
    sig_box.append(Spacer(1, 4 * mm))
    sig_box.extend(_field_with_space("Ort:", "", S))
    sig_box.append(Spacer(1, 2 * mm))
    sig_box.extend(_field_with_space(
        "Datum:", date.today().strftime("%d/%m/%Y"), S,
    ))
    sig_box.append(Spacer(1, 6 * mm))
    sig_box.extend(_field_with_space(
        "Name und Unterschrift:", _val(case.claimant_name), S,
    ))
    el.append(_bordered_box(sig_box, S))

    # =====================================================================
    # PAGE 9: Anlage — Bank details for court fee
    # =====================================================================

    el.append(PageBreak())

    el.append(Paragraph(
        "<b><i>Anlage zum Klageformblatt (Formblatt A)</i></b>",
        ParagraphStyle(
            "AnlageTitle", parent=S["normal"], fontSize=11,
            alignment=TA_CENTER, fontName="Helvetica-BoldOblique",
            spaceAfter=2 * mm,
        ),
    ))
    el.append(Paragraph(
        "Bankverbindung* für die Entrichtung der Gerichtsgebühr",
        ParagraphStyle(
            "AnlageSub", parent=S["normal"], fontSize=9,
            alignment=TA_CENTER, spaceAfter=4 * mm,
        ),
    ))

    anlage_box = []
    anlage_box.extend(_field_with_space(
        "Kontoinhaber/Kreditkarteninhaber:", "", S,
    ))
    anlage_box.append(Spacer(1, 4 * mm))
    anlage_box.extend(_field_with_space(
        "Bankadresse, BIC oder andere einschlägige Bankkennung (BLZ)/"
        "Kreditkartenunternehmen:",
        "", S,
    ))
    anlage_box.append(Spacer(1, 4 * mm))
    anlage_box.extend(_field_with_space(
        "Kontonummer oder IBAN-/Kreditkarten-Nummer, Gültigkeit und "
        "Kartenprüfnummer der Kreditkarte:",
        "", S,
    ))
    el.append(_bordered_box(anlage_box, S))

    # ── Footer ──
    el.append(Spacer(1, 10 * mm))
    el.append(Paragraph(
        "Dieses Formular wurde automatisch auf Grundlage der vom Nutzer "
        "gemachten Angaben erstellt. Bitte prüfen Sie alle Angaben sorgfältig "
        "vor Einreichung beim zuständigen Gericht.",
        S["footer"],
    ))

    doc.build(el)
    return filename, filepath
