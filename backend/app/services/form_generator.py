"""
PDF Form Generator for EU Small Claims Procedure.

Generates Form A (Klageformblatt / Claim Form) per Annex I of
Regulation (EC) No 861/2007 as amended by Regulation (EU) 2015/2421.

Form A structure (10 sections):
  1. Court/Tribunal
  2. Claimant details (2.1–2.9)
  3. Defendant details (3.1–3.9)
  4. Jurisdiction basis (4.1–4.8)
  5. Cross-border nature (5.1–5.3)
  6. Bank details — optional (6.1–6.2)
  7. Claim — monetary / non-monetary (7.1–7.3 + interest)
  8. Details of claim — substance, evidence, hearing (8.1–8.2)
  9. Certificate request for cross-border enforcement
 10. Date, place, signature & declaration
"""

import os
import uuid
from datetime import date

from reportlab.lib import colors
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
)

from ..config import get_settings
from ..models import Case

settings = get_settings()

# ── EU Member States participating in the ESCP (Denmark excluded) ────────
EU_COUNTRIES = {
    "AT": "Österreich / Austria",
    "BE": "Belgien / Belgium",
    "BG": "Bulgarien / Bulgaria",
    "HR": "Kroatien / Croatia",
    "CY": "Zypern / Cyprus",
    "CZ": "Tschechien / Czech Republic",
    "EE": "Estland / Estonia",
    "FI": "Finnland / Finland",
    "FR": "Frankreich / France",
    "DE": "Deutschland / Germany",
    "GR": "Griechenland / Greece",
    "HU": "Ungarn / Hungary",
    "IE": "Irland / Ireland",
    "IT": "Italien / Italy",
    "LV": "Lettland / Latvia",
    "LT": "Litauen / Lithuania",
    "LU": "Luxemburg / Luxembourg",
    "MT": "Malta",
    "NL": "Niederlande / Netherlands",
    "PL": "Polen / Poland",
    "PT": "Portugal",
    "RO": "Rumänien / Romania",
    "SK": "Slowakei / Slovakia",
    "SI": "Slowenien / Slovenia",
    "ES": "Spanien / Spain",
    "SE": "Schweden / Sweden",
}

JURISDICTION_BASES = {
    "4.1": "Wohnsitz/Sitz des Beklagten (Art. 4 Brüssel-Ia-VO)",
    "4.2": "Erfüllungsort der vertraglichen Verpflichtung (Art. 7 Nr. 1 Brüssel-Ia-VO)",
    "4.3": "Ort des schädigenden Ereignisses (Art. 7 Nr. 2 Brüssel-Ia-VO)",
    "4.4": "Wohnsitz des Verbrauchers (Art. 18 Brüssel-Ia-VO)",
    "4.5": "Niederlassung/Zweigniederlassung (Art. 7 Nr. 5 Brüssel-Ia-VO)",
    "4.6": "Arbeitsort (Art. 21 Brüssel-Ia-VO)",
    "4.7": "Gerichtsstandsvereinbarung der Parteien (Art. 25 Brüssel-Ia-VO)",
    "4.8": "Sonstige Grundlage (bitte angeben)",
}


def _country(code: str | None) -> str:
    if not code:
        return "—"
    return EU_COUNTRIES.get(code.upper(), code)


def _val(v, fallback: str = "—") -> str:
    return str(v) if v else fallback


def _checkbox(checked: bool) -> str:
    return "[X]" if checked else "[  ]"


# ── Styles ───────────────────────────────────────────────────────────────────

def _get_styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "FTitle", parent=base["Heading1"], fontSize=14, alignment=1,
            spaceAfter=2 * mm, textColor=colors.HexColor("#1a237e"),
        ),
        "subtitle": ParagraphStyle(
            "FSub", parent=base["Heading2"], fontSize=10, alignment=1,
            spaceAfter=5 * mm, textColor=colors.HexColor("#37474f"),
        ),
        "section": ParagraphStyle(
            "FSec", parent=base["Heading2"], fontSize=11, spaceBefore=7 * mm,
            spaceAfter=3 * mm, textColor=colors.HexColor("#1a237e"),
        ),
        "normal": ParagraphStyle(
            "FNorm", parent=base["Normal"], fontSize=9, leading=13,
        ),
        "small": ParagraphStyle(
            "FSmall", parent=base["Normal"], fontSize=7.5, leading=10,
            textColor=colors.HexColor("#757575"),
        ),
        "footer": ParagraphStyle(
            "FFoot", parent=base["Normal"], fontSize=7, textColor=colors.grey,
            alignment=1,
        ),
    }


def _field_table(rows: list[list[str]]) -> Table:
    """Two-column label-value table."""
    t = Table(rows, colWidths=[50 * mm, 120 * mm])
    t.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("LINEBELOW", (1, 0), (1, -1), 0.4, colors.HexColor("#e0e0e0")),
    ]))
    return t


# ── Main generator ───────────────────────────────────────────────────────────

def generate_form_a(case: Case) -> tuple[str, str]:
    """
    Generate Form A (Klageformblatt / Claim Form) as PDF.
    Follows the official 10-section structure of Annex I,
    Regulation (EC) No 861/2007 as amended by Regulation (EU) 2015/2421.
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

    # ── Header ───────────────────────────────────────────────────────────
    el.append(Paragraph("FORMBLATT A — KLAGEFORMBLATT", S["title"]))
    el.append(Paragraph(
        "EUROPÄISCHES VERFAHREN FÜR GERINGFÜGIGE FORDERUNGEN<br/>"
        "Verordnung (EG) Nr. 861/2007, geändert durch Verordnung (EU) 2015/2421<br/>"
        "EUROPEAN SMALL CLAIMS PROCEDURE — FORM A (Claim Form, Annex I)",
        S["subtitle"],
    ))

    # ── Section 1: Gericht / Court ───────────────────────────────────────
    el.append(Paragraph("1. Gericht / Court/Tribunal", S["section"]))
    el.append(Paragraph(
        "<i>Name und Anschrift des Gerichts, bei dem die Klage eingereicht wird "
        "(vom Kläger auszufüllen, sofern bekannt).</i>",
        S["small"],
    ))
    el.append(_field_table([
        ["1.1 Name des Gerichts:", _val(case.court_name)],
        ["1.2 Anschrift:", _val(case.court_address)],
        ["1.3 Mitgliedstaat:", _country(case.court_country or case.court_member_state)],
    ]))

    # ── Section 2: Kläger / Claimant ─────────────────────────────────────
    el.append(Paragraph("2. Angaben zum Kläger / Claimant", S["section"]))
    el.append(_field_table([
        ["2.1 Name:", _val(case.claimant_name)],
        ["2.2 Ausweis-/Pass-/Reg.Nr.:", _val(case.claimant_id_number)],
        ["2.3 Straße und Nr.:", _val(case.claimant_address)],
        ["2.4 Ort und PLZ:", _val(case.claimant_city)],
        ["2.5 Land:", _country(case.claimant_country)],
        ["2.6 Telefon:", _val(case.claimant_phone)],
        ["2.7 E-Mail:", _val(case.claimant_email)],
        ["2.8 Vertreter (ggf.):", _val(case.claimant_representative)],
        ["2.9 Sonstiges:", _val(case.claimant_other)],
    ]))

    # ── Section 3: Beklagter / Defendant ─────────────────────────────────
    el.append(Paragraph("3. Angaben zum Beklagten / Defendant", S["section"]))
    el.append(_field_table([
        ["3.1 Name:", _val(case.defendant_name)],
        ["3.2 Ausweis-/Pass-/Reg.Nr.:", _val(case.defendant_id_number)],
        ["3.3 Straße und Nr.:", _val(case.defendant_address)],
        ["3.4 Ort und PLZ:", _val(case.defendant_city)],
        ["3.5 Land:", _country(case.defendant_country)],
        ["3.6 Telefon:", _val(case.defendant_phone)],
        ["3.7 E-Mail:", _val(case.defendant_email)],
        ["3.8 Vertreter (ggf.):", _val(case.defendant_representative)],
        ["3.9 Sonstiges:", _val(case.defendant_other)],
    ]))

    # ── Section 4: Zuständigkeit / Jurisdiction ──────────────────────────
    el.append(Paragraph(
        "4. Zuständigkeit des Gerichts / Basis for jurisdiction", S["section"]
    ))
    el.append(Paragraph(
        "<i>Bitte kreuzen Sie die zutreffende Grundlage der gerichtlichen Zuständigkeit an "
        "(gemäß Verordnung (EU) Nr. 1215/2012 — Brüssel-Ia-VO):</i>",
        S["small"],
    ))
    jb = case.jurisdiction_basis or ""
    for code, label in JURISDICTION_BASES.items():
        checked = _checkbox(jb == code)
        el.append(Paragraph(f"&nbsp;&nbsp;{checked} <b>{code}</b> — {label}", S["normal"]))

    if case.jurisdiction_details:
        el.append(Spacer(1, 2 * mm))
        el.append(Paragraph(
            f"<b>Erläuterung:</b> {case.jurisdiction_details}", S["normal"]
        ))

    # ── Section 5: Grenzüberschreitender Charakter ───────────────────────
    el.append(Paragraph(
        "5. Grenzüberschreitender Charakter / Cross-border nature", S["section"]
    ))
    el.append(Paragraph(
        "<i>Damit das EU-Bagatellverfahren anwendbar ist, muss mindestens eine Partei "
        "ihren Wohnsitz/Sitz in einem anderen Mitgliedstaat als dem des angerufenen "
        "Gerichts haben.</i>",
        S["small"],
    ))
    el.append(_field_table([
        ["5.1 Wohnsitzland Kläger:", _country(
            case.claimant_domicile_country or case.claimant_country
        )],
        ["5.2 Wohnsitzland Beklagter:", _country(
            case.defendant_domicile_country or case.defendant_country
        )],
        ["5.3 Mitgliedstaat Gericht:", _country(
            case.court_member_state or case.court_country
        )],
    ]))
    cross = "JA / YES" if case.is_cross_border else "NEIN / NO"
    el.append(Paragraph(f"<b>Grenzüberschreitend:</b> {cross}", S["normal"]))

    # ── Section 6: Bankverbindung / Bank details ─────────────────────────
    el.append(Paragraph(
        "6. Bankverbindung (fakultativ) / Bank details (optional)", S["section"]
    ))
    el.append(_field_table([
        ["6.1 Zahlung Gerichtsgebühr:", _val(case.bank_fee_payment_method)],
        ["6.2 Empfang Zahlung v. Bekl.:", _val(case.bank_account_details)],
    ]))

    el.append(PageBreak())

    # ── Section 7: Klage / Claim ─────────────────────────────────────────
    el.append(Paragraph("7. Klage / Claim", S["section"]))
    el.append(Paragraph(
        "<i>Der Streitwert darf 5.000 EUR (ohne Zinsen, Kosten und Auslagen) "
        "zum Zeitpunkt des Eingangs beim Gericht nicht übersteigen.</i>",
        S["small"],
    ))

    # 7.1 Monetary
    el.append(Paragraph("<b>7.1 Geldforderung / Monetary claim</b>", S["normal"]))
    if case.claim_amount:
        el.append(Paragraph(
            f"&nbsp;&nbsp;Betrag: <b>{case.claim_amount:,.2f} "
            f"{case.claim_currency or 'EUR'}</b>",
            S["normal"],
        ))
    else:
        el.append(Paragraph("&nbsp;&nbsp;(Kein Geldbetrag angegeben)", S["normal"]))

    # 7.2 Non-monetary
    el.append(Spacer(1, 2 * mm))
    el.append(Paragraph(
        "<b>7.2 Nicht-monetäre Forderung / Non-monetary claim</b>", S["normal"]
    ))
    el.append(Paragraph(
        f"&nbsp;&nbsp;{_val(case.claim_non_monetary, '(Keine)')}", S["normal"]
    ))

    # 7.3 Costs
    el.append(Spacer(1, 2 * mm))
    el.append(Paragraph(
        "<b>7.3 Sonstige Kosten / Other costs</b>", S["normal"]
    ))
    el.append(Paragraph(
        f"&nbsp;&nbsp;{_val(case.claim_costs, '(Keine)')}", S["normal"]
    ))

    # Interest
    el.append(Spacer(1, 2 * mm))
    el.append(Paragraph("<b>Zinsen / Interest</b>", S["normal"]))
    if case.claim_interest_rate:
        itype = "Vertragszins" if case.claim_interest_type == "contractual" \
            else "Gesetzlicher Zins"
        el.append(Paragraph(
            f"&nbsp;&nbsp;{itype}: {case.claim_interest_rate}% "
            f"ab {_val(case.claim_interest_from_date, '(Datum nicht angegeben)')}",
            S["normal"],
        ))
    else:
        el.append(Paragraph("&nbsp;&nbsp;(Keine Zinsen beantragt)", S["normal"]))

    # ── Section 8: Einzelheiten / Details of claim ───────────────────────
    el.append(Paragraph(
        "8. Einzelheiten der Klage / Details of claim", S["section"]
    ))

    # 8.1 Substance
    el.append(Paragraph(
        "<b>8.1 Sachverhalt / Description of circumstances</b>", S["normal"]
    ))
    el.append(Spacer(1, 1 * mm))
    desc = case.claim_description or "(Kein Sachverhalt geschildert)"
    for para in desc.split("\n"):
        if para.strip():
            el.append(Paragraph(para.strip(), S["normal"]))
    el.append(Spacer(1, 2 * mm))

    # Legal basis
    el.append(Paragraph(
        "<b>Rechtliche Grundlage / Legal basis of claim</b>", S["normal"]
    ))
    el.append(Paragraph(_val(case.claim_basis, "(Keine Angabe)"), S["normal"]))
    el.append(Spacer(1, 2 * mm))

    # Applicable law
    if case.applicable_law:
        el.append(Paragraph(
            "<b>Anwendbares Recht / Applicable law</b>", S["normal"]
        ))
        el.append(Paragraph(case.applicable_law, S["normal"]))
        el.append(Spacer(1, 2 * mm))

    # 8.2 Evidence
    el.append(Paragraph("<b>8.2 Beweismittel / Evidence</b>", S["normal"]))
    el.append(Paragraph(
        "<i>Folgende Beweismittel werden dem Klageformblatt beigefügt bzw. "
        "zur Unterstützung der Klage angeboten:</i>",
        S["small"],
    ))
    evidence = case.claim_evidence or "(Keine Beweismittel angegeben)"
    for para in evidence.split("\n"):
        if para.strip():
            el.append(Paragraph(f"&nbsp;&nbsp;- {para.strip()}", S["normal"]))
    el.append(Spacer(1, 2 * mm))

    # Hearing preference
    hearing = _checkbox(bool(case.request_oral_hearing))
    el.append(Paragraph(
        f"{hearing} Ich beantrage eine mündliche Verhandlung / "
        f"I request an oral hearing",
        S["normal"],
    ))
    el.append(Paragraph(
        "<i>(Gemäß Art. 5 Abs. 1a der VO ist das Verfahren grundsätzlich "
        "schriftlich; eine mündliche Verhandlung findet nur statt, wenn das "
        "Gericht dies für erforderlich hält oder eine Partei dies beantragt "
        "und das Gericht dem zustimmt.)</i>",
        S["small"],
    ))

    # ── Section 9: Bestätigung / Certificate ─────────────────────────────
    el.append(Paragraph(
        "9. Bestätigung / Certificate for enforcement", S["section"]
    ))
    cert = _checkbox(case.request_enforcement_certificate in (True, None))
    el.append(Paragraph(
        f"{cert} Ich beantrage die Ausstellung einer Bestätigung gemäß "
        f"Art. 20 Abs. 2 der Verordnung (EG) Nr. 861/2007 für die "
        f"grenzüberschreitende Vollstreckung des Urteils.<br/>"
        f"<i>I request a certificate pursuant to Article 20(2) of "
        f"Regulation (EC) No 861/2007 for the cross-border enforcement "
        f"of the judgment (Form D, Annex IV).</i>",
        S["normal"],
    ))

    # ── Section 10: Datum und Unterschrift / Date and Signature ──────────
    el.append(Paragraph(
        "10. Datum und Unterschrift / Date and signature", S["section"]
    ))
    el.append(Paragraph(
        "Ich erkläre, dass die vorstehenden Angaben meines Wissens "
        "wahrheitsgemäß und vollständig sind. Ich bin mir bewusst, dass "
        "unwahre Angaben rechtliche Konsequenzen haben können.<br/>"
        "<i>I declare that the information given above is true and complete "
        "to the best of my knowledge and belief.</i>",
        S["normal"],
    ))
    el.append(Spacer(1, 5 * mm))
    el.append(_field_table([
        ["Ort / Place:", "___________________________________"],
        ["Datum / Date:", date.today().strftime("%d.%m.%Y")],
        ["", ""],
        ["Unterschrift / Signature:", "___________________________________"],
    ]))

    # ── Footer / Disclaimer ──────────────────────────────────────────────
    el.append(Spacer(1, 10 * mm))
    el.append(Paragraph(
        "Dieses Formular wurde automatisch auf Grundlage der vom Nutzer "
        "gemachten Angaben erstellt. Es orientiert sich am Formblatt A "
        "(Anhang I) der Verordnung (EG) Nr. 861/2007 in der Fassung der "
        "Verordnung (EU) 2015/2421. Bitte prüfen Sie alle Angaben "
        "sorgfältig vor Einreichung beim zuständigen Gericht. "
        "Dieses Dokument ersetzt keine Rechtsberatung. "
        "Das offizielle Formular ist unter https://e-justice.europa.eu "
        "verfügbar.",
        S["footer"],
    ))

    doc.build(el)
    return filename, filepath
