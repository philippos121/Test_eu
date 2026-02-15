"""
PDF Form Generator for EU Small Claims Procedure.

Fills in the official Form A (Klageformblatt / Claim Form) PDF template
(SC_A_15022026_DE.pdf) published on the European e-Justice Portal.

The template has 160 fillable text fields (field0–field159).
Small 9×9 pt fields act as checkboxes — we write "X" to check them.
"""

import os
import uuid
from datetime import date
from pathlib import Path

from pypdf import PdfReader, PdfWriter

from ..config import get_settings
from ..models import Case

settings = get_settings()

# Path to the official PDF template
_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"
_TEMPLATE_PATH = _TEMPLATE_DIR / "SC_A_15022026_DE.pdf"

# ── Helpers ──────────────────────────────────────────────────────────────────

EU_COUNTRIES = {
    "AT": "Österreich", "BE": "Belgien", "BG": "Bulgarien",
    "HR": "Kroatien", "CY": "Zypern", "CZ": "Tschechien",
    "DK": "Dänemark", "EE": "Estland", "FI": "Finnland",
    "FR": "Frankreich", "DE": "Deutschland", "GR": "Griechenland",
    "HU": "Ungarn", "IE": "Irland", "IT": "Italien",
    "LV": "Lettland", "LT": "Litauen", "LU": "Luxemburg",
    "MT": "Malta", "NL": "Niederlande", "PL": "Polen",
    "PT": "Portugal", "RO": "Rumänien", "SK": "Slowakei",
    "SI": "Slowenien", "ES": "Spanien", "SE": "Schweden",
}


def _v(val, fallback: str = "") -> str:
    """Return string value or fallback."""
    if val is None or val == "":
        return fallback
    return str(val)


def _country(code: str | None) -> str:
    if not code:
        return ""
    return EU_COUNTRIES.get(code.upper(), code)


def _x(condition: bool) -> str:
    """Return 'X' for checked checkbox fields, '' otherwise."""
    return "X" if condition else ""


def _split_date(date_str: str | None) -> tuple[str, str, str]:
    """Split a date string (DD/MM/YYYY, DD.MM.YYYY, YYYY-MM-DD) into (day, month, year)."""
    if not date_str:
        return ("", "", "")
    s = str(date_str).strip()
    if "-" in s:  # YYYY-MM-DD
        parts = s.split("-")
        if len(parts) == 3:
            return (parts[2], parts[1], parts[0])
    elif "/" in s:  # DD/MM/YYYY
        parts = s.split("/")
        if len(parts) == 3:
            return (parts[0], parts[1], parts[2])
    elif "." in s:  # DD.MM.YYYY
        parts = s.split(".")
        if len(parts) == 3:
            return (parts[0], parts[1], parts[2])
    return (s, "", "")


# ── Field mapping ────────────────────────────────────────────────────────────
#
# Complete mapping of field0–field159 to the official Form A sections.
# See SC_A_15022026_DE.pdf (9 pages, 160 AcroForm text widgets).
#
# PAGE 1 (5 fields): Aktenzeichen + Section 1 Court
# PAGE 2 (10 fields): Section 2 Claimant (2.1–2.9) + Section 3 start (3.1)
# PAGE 3 (17 fields): Section 3 cont. (3.2–3.9) + Section 4 Jurisdiction + Section 5 start
# PAGE 4 (9 fields): Section 5 cont. + Section 6 Bank
# PAGE 5 (49 fields): Section 7 Claim (7.1–7.4.1)
# PAGE 6 (29 fields): Section 7 cont. (7.4.2–7.5) + Section 8
# PAGE 7 (26 fields): Section 9 + 10 + 11 (start)
# PAGE 8 (12 fields): Section 11 cont. + Section 12
# PAGE 9 (3 fields): Anlage


def _build_field_values(case: Case) -> dict[str, str]:
    """Build {field_name: value} dict for all 160 form fields."""

    jb = _v(case.jurisdiction_basis)
    currency = _v(case.claim_currency, "EUR").upper()
    has_monetary = bool(case.claim_amount)
    has_non_monetary = bool(case.claim_non_monetary)
    interest_type = _v(case.claim_interest_type)
    has_interest = bool(case.claim_interest_rate) or interest_type in ("contractual", "statutory")
    is_contractual = interest_type == "contractual"
    is_statutory = interest_type == "statutory"
    request_costs = bool(getattr(case, "claim_request_costs", False) or case.claim_costs)

    # Interest dates
    from_d, from_m, from_y = _split_date(case.claim_interest_from_date)
    to_d, to_m, to_y = _split_date(getattr(case, "claim_interest_to_date", None))
    interest_to_judgment = not to_d  # If no end date specified, default to "until judgment"

    # Non-monetary currency
    nm_currency = _v(getattr(case, "claim_non_monetary_currency", None), currency).upper()

    # Today's date for Section 12
    today = date.today()

    # Certificate language
    cert_lang = _v(getattr(case, "certificate_language", None)).lower()

    # Language checkbox mapping (field130–field151)
    lang_map = {
        "field130": "bulgarisch", "field131": "spanisch", "field132": "tschechisch",
        "field133": "deutsch", "field134": "estnisch", "field135": "griechisch",
        "field136": "englisch", "field137": "französisch", "field138": "kroatisch",
        "field139": "italienisch", "field140": "lettisch", "field141": "litauisch",
        "field142": "ungarisch", "field143": "maltesisch", "field144": "niederländisch",
        "field145": "polnisch", "field146": "portugiesisch", "field147": "rumänisch",
        "field148": "slowakisch", "field149": "slowenisch", "field150": "finnisch",
        "field151": "schwedisch",
    }

    f: dict[str, str] = {}

    # ── PAGE 1: Aktenzeichen + Section 1 Court ──
    f["field0"] = ""  # Aktenzeichen — filled by court
    f["field1"] = _v(case.court_name)               # 1.1 Name
    f["field2"] = _v(case.court_address)             # 1.2 Straße
    f["field3"] = ""                                 # 1.3 PLZ und Ort
    f["field4"] = _country(case.court_country or case.court_member_state)  # 1.4 Land

    # ── PAGE 2: Section 2 Claimant + Section 3 start ──
    f["field5"] = _v(case.claimant_name)             # 2.1 Nachname/Firma
    f["field6"] = _v(case.claimant_id_number)        # 2.2 Persönliche ID
    f["field7"] = _v(case.claimant_address)          # 2.3 Straße
    f["field8"] = _v(case.claimant_city)             # 2.4 PLZ und Ort
    f["field9"] = _country(case.claimant_country)    # 2.5 Land
    f["field10"] = _v(case.claimant_phone)           # 2.6 Telefon
    f["field11"] = _v(case.claimant_email)           # 2.7 E-Mail
    f["field12"] = _v(case.claimant_representative)  # 2.8 Vertreter
    f["field13"] = _v(case.claimant_other)           # 2.9 Sonstige
    f["field14"] = _v(case.defendant_name)           # 3.1 Nachname/Firma

    # ── PAGE 3: Section 3 cont. (3.2–3.9) + Section 4 + Section 5 start ──
    f["field15"] = _v(case.defendant_id_number)      # 3.2 Persönliche ID
    f["field16"] = _v(case.defendant_address)        # 3.3 Straße
    f["field17"] = _v(case.defendant_city)           # 3.4 PLZ und Ort
    f["field18"] = _country(case.defendant_country)  # 3.5 Land
    f["field19"] = _v(case.defendant_phone)          # 3.6 Telefon
    f["field20"] = _v(case.defendant_email)          # 3.7 E-Mail
    f["field21"] = _v(case.defendant_representative) # 3.8 Vertreter
    f["field22"] = _v(case.defendant_other)          # 3.9 Sonstige

    # Section 4: Jurisdiction checkboxes (4.1–4.7)
    f["field23"] = _x(jb.startswith("4.1"))          # 4.1 Wohnsitz Beklagter
    f["field24"] = _x(jb.startswith("4.2"))          # 4.2 Wohnsitz Verbraucher
    f["field25"] = _x(jb.startswith("4.3"))          # 4.3 Versicherungssachen
    f["field26"] = _x(jb.startswith("4.4"))          # 4.4 Leistungsort
    f["field27"] = _x(jb.startswith("4.5"))          # 4.5 Schädigendes Ereignis
    f["field28"] = _x(jb.startswith("4.6"))          # 4.6 Unbewegliche Sache
    f["field29"] = _x(jb.startswith("4.7"))          # 4.7 Gerichtsstandsvereinbarung
    f["field30"] = _v(case.jurisdiction_details) if jb.startswith("4.8") else ""  # 4.8 Sonstiges

    # Section 5: Cross-border (5.1 on page 3)
    f["field31"] = _country(case.claimant_domicile_country or case.claimant_country)  # 5.1

    # ── PAGE 4: Section 5 cont. + Section 6 Bank ──
    f["field32"] = _country(case.defendant_domicile_country or case.defendant_country)  # 5.2
    f["field33"] = _country(case.court_member_state or case.court_country)  # 5.3

    # Section 6: Bank details
    fee_method = _v(case.bank_fee_payment_method, "").lower()
    f["field34"] = _x("überweisung" in fee_method)           # 6.1.1 Überweisung
    f["field35"] = _x("kreditkarte" in fee_method or "credit" in fee_method)  # 6.1.2 Kreditkarte
    f["field36"] = _x("lastschrift" in fee_method or "einzug" in fee_method)  # 6.1.3 Lastschrift
    f["field37"] = ""  # 6.1.4 Andere (text)
    f["field38"] = _v(getattr(case, "bank_account_holder", None))  # 6.2.1 Kontoinhaber
    f["field39"] = _v(getattr(case, "bank_name_bic", None))        # 6.2.2 Bank/BIC
    f["field40"] = _v(getattr(case, "bank_iban", None))            # 6.2.3 IBAN

    # ── PAGE 5: Section 7 Claim ──
    f["field41"] = _x(has_monetary)                  # 7.1 Geldforderung checkbox
    f["field42"] = f"{case.claim_amount:,.2f}" if case.claim_amount else ""  # 7.1.1 Betrag

    # 7.1.2 Currency checkboxes
    currency_fields = {
        "field43": "EUR", "field44": "BGN", "field45": "HRK",
        "field46": "CZK", "field47": "HUF", "field48": "GBP",
        "field49": "PLN", "field50": "RON", "field51": "SEK",
    }
    for fld, cur in currency_fields.items():
        f[fld] = _x(has_monetary and currency == cur)
    f["field52"] = _x(has_monetary and currency not in currency_fields.values())  # Sonstige
    f["field53"] = currency if (has_monetary and currency not in currency_fields.values()) else ""

    # 7.2 Andere Forderung
    f["field54"] = _x(has_non_monetary)              # 7.2 checkbox
    f["field55"] = _v(case.claim_non_monetary)       # 7.2.1 description
    nm_val = getattr(case, "claim_non_monetary_value", None)
    f["field56"] = f"{nm_val:,.2f}" if nm_val else ""  # 7.2.2 estimated value

    # 7.2.2 Currency checkboxes
    nm_currency_fields = {
        "field57": "EUR", "field58": "BGN", "field59": "HRK",
        "field60": "CZK", "field61": "HUF", "field62": "GBP",
        "field63": "PLN", "field64": "RON", "field65": "SEK",
    }
    for fld, cur in nm_currency_fields.items():
        f[fld] = _x(has_non_monetary and nm_currency == cur)
    f["field66"] = _x(has_non_monetary and nm_currency not in nm_currency_fields.values())
    f["field67"] = nm_currency if (has_non_monetary and nm_currency not in nm_currency_fields.values()) else ""

    # 7.3 Verfahrenskosten
    f["field68"] = _x(request_costs)                 # 7.3.1 Ja
    f["field69"] = _x(not request_costs)             # 7.3.2 Nein
    f["field70"] = _v(case.claim_costs)              # 7.3.3 Details

    # 7.4 Zinsen
    f["field71"] = _x(has_interest)                  # 7.4 Ja
    f["field72"] = _x(not has_interest)              # 7.4 Nein
    f["field73"] = _x(is_contractual)                # Vertraglicher Zinssatz
    f["field74"] = _x(is_statutory)                  # gesetzlicher Zinssatz

    # 7.4.1 Contractual interest details
    rate_str = f"{case.claim_interest_rate}" if case.claim_interest_rate else ""
    f["field75"] = _x(is_contractual and bool(rate_str))  # % checkbox
    f["field76"] = rate_str if is_contractual else ""      # rate value
    f["field77"] = ""  # % über Basiszinssatz (not used by default)
    f["field78"] = ""  # value above base rate
    f["field79"] = ""  # anderer Wert checkbox
    f["field80"] = ""  # other value text

    # 7.4.1 Dates (Zinsen ab / bis)
    if is_contractual:
        f["field81"] = from_d   # day
        f["field82"] = from_m   # month
        f["field83"] = from_y   # year
        f["field84"] = _x(bool(to_d))          # bis checkbox (specific date)
        f["field85"] = to_d                     # bis day
        f["field86"] = to_m                     # bis month
        f["field87"] = to_y                     # bis year
        f["field88"] = _x(not to_d and interest_to_judgment)  # bis Tag des Urteils
        f["field89"] = _x(not to_d and not interest_to_judgment)  # bis Erfüllung
    else:
        for fid in range(81, 90):
            f[f"field{fid}"] = ""

    # ── PAGE 6: Section 7 cont. (7.4.2 statutory) + 7.5 + Section 8 ──

    # 7.4.2 Statutory interest dates
    if is_statutory:
        f["field90"] = from_d   # day
        f["field91"] = from_m   # month
        f["field92"] = from_y   # year
        f["field93"] = _x(bool(to_d))          # bis checkbox
        f["field94"] = to_d
        f["field95"] = to_m
        f["field96"] = to_y
        f["field97"] = _x(not to_d and interest_to_judgment)  # bis Urteil
        f["field98"] = _x(not to_d and not interest_to_judgment)  # bis Erfüllung
    else:
        for fid in range(90, 99):
            f[f"field{fid}"] = ""

    # 7.5 Zinsen auf die Kosten
    interest_on_costs = bool(getattr(case, "claim_interest_on_costs", False))
    f["field99"] = _x(interest_on_costs)              # 7.5 Ja
    f["field100"] = _x(not interest_on_costs)         # 7.5 Nein
    # 7.5 details (dates / events) — leave empty for now
    for fid in range(101, 112):
        f[f"field{fid}"] = ""

    # Section 8: Einzelheiten zur Klage
    desc = _v(case.claim_description)
    if case.claim_basis:
        desc += f"\n\nRechtliche Grundlage: {case.claim_basis}"
    if case.applicable_law:
        desc += f"\nAnwendbares Recht: {case.applicable_law}"
    f["field112"] = desc                              # 8.1 Begründung

    has_evidence = bool(case.claim_evidence)
    f["field113"] = _x(has_evidence)                  # 8.2.1 Urkundenbeweis
    f["field114"] = _v(case.claim_evidence) if has_evidence else ""  # 8.2.1 details
    f["field115"] = ""                                # 8.2.2 Zeugenbeweis
    f["field116"] = ""                                # 8.2.2 details
    f["field117"] = ""                                # 8.2.3 Sonstiges
    f["field118"] = ""                                # 8.2.3 details

    # ── PAGE 7: Section 9 + 10 + 11 ──

    # Section 9: Mündliche Verhandlung
    oral = bool(case.request_oral_hearing)
    f["field119"] = _x(oral)                          # 9.1 Ja
    f["field120"] = _x(not oral)                      # 9.1 Nein
    f["field121"] = _v(getattr(case, "oral_hearing_reasons", None))  # 9.1 Gründe

    personal = bool(getattr(case, "request_personal_attendance", False))
    f["field122"] = _x(personal)                      # 9.2 Ja
    f["field123"] = _x(not personal)                  # 9.2 Nein
    f["field124"] = _v(getattr(case, "personal_attendance_reasons", None))  # 9.2 Gründe

    # Section 10: Zustellung
    e_service = bool(getattr(case, "consent_electronic_service", False))
    e_comm = bool(getattr(case, "consent_electronic_communication", False))
    f["field125"] = _x(e_service)                     # 10.1 Ja
    f["field126"] = _x(not e_service)                 # 10.1 Nein
    f["field127"] = _x(e_comm)                        # 10.2 Ja
    f["field128"] = _x(not e_comm)                    # 10.2 Nein

    # Section 11: Bestätigung
    cert = case.request_enforcement_certificate in (True, None)
    f["field129"] = _x(cert)                          # 11.1 checkbox

    # 11.2 Language checkboxes (field130–field151)
    for fld, lang in lang_map.items():
        f[fld] = _x(cert_lang == lang)

    # ── PAGE 8: Section 12 Date + Signature ──
    # (language fields field145–field151 already handled above)

    f["field152"] = ""                                # 12. Ort
    f["field153"] = str(today.day).zfill(2)           # 12. Datum day
    f["field154"] = str(today.month).zfill(2)         # 12. Datum month
    f["field155"] = str(today.year)                   # 12. Datum year
    f["field156"] = _v(case.claimant_name)            # 12. Name

    # ── PAGE 9: Anlage (bank details for court fee) ──
    f["field157"] = ""  # Kontoinhaber/Kreditkarteninhaber
    f["field158"] = ""  # Bankadresse/BIC
    f["field159"] = ""  # Kontonummer/IBAN

    return f


# ── Main generator ───────────────────────────────────────────────────────────

def generate_form_a(case: Case) -> tuple[str, str]:
    """
    Fill the official EU Form A PDF template with case data.
    Returns (filename, filepath).
    """
    os.makedirs(settings.generated_forms_dir, exist_ok=True)
    filename = f"Formblatt_A_{uuid.uuid4().hex[:8]}.pdf"
    filepath = os.path.join(settings.generated_forms_dir, filename)

    # Build field values from case data
    field_values = _build_field_values(case)

    # Read template and create writer
    reader = PdfReader(str(_TEMPLATE_PATH))
    writer = PdfWriter()
    writer.append(reader)

    # Fill form fields on each page
    for page_num in range(len(writer.pages)):
        writer.update_page_form_field_values(
            writer.pages[page_num],
            field_values,
            auto_regenerate=False,
        )

    # Write filled PDF
    with open(filepath, "wb") as out:
        writer.write(out)

    return filename, filepath
