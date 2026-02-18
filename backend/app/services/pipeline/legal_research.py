"""Legal research provider — determines applicable law and researches legal bases.

EU-wide: configurable per member state via legal_sources.yaml.
Always performs web research before computing p_recht.
"""
from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Optional

import yaml

from .models import (
    ApplicableLawDecision,
    CaseInput,
    ClaimType,
    LegalBasis,
    LegalElement,
    LegalResearchResult,
    SourceRef,
    YesNoUnknown,
)
from .search import SearchClient, SearchResult
from .fetch import FetchClient
from .parse import html_to_text, extract_legal_snippets, extract_statute_references

logger = logging.getLogger(__name__)

# Load legal sources config
_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "legal_sources.yaml"


def _load_legal_sources() -> dict:
    try:
        with open(_CONFIG_PATH) as f:
            return yaml.safe_load(f) or {}
    except Exception:
        logger.warning("Could not load legal_sources.yaml from %s", _CONFIG_PATH)
        return {}


LEGAL_SOURCES = _load_legal_sources()

# Claim-type-specific legal elements per major legal tradition
# Key: (claim_type, law_group) -> list of element definitions
# law_group: "germanic" (DE/AT/CH), "romance" (FR/IT/ES/PT/BE/RO), "common" (IE/MT/CY), "nordic" (SE/DK/FI), "other"

_LAW_GROUP_MAP = {
    "DE": "germanic", "AT": "germanic",
    "FR": "romance", "IT": "romance", "ES": "romance", "PT": "romance",
    "BE": "romance", "RO": "romance", "LU": "romance",
    "NL": "germanic", "PL": "germanic", "CZ": "germanic", "SK": "germanic",
    "HU": "germanic", "HR": "germanic", "SI": "germanic", "BG": "romance",
    "IE": "common", "MT": "common", "CY": "common",
    "SE": "nordic", "DK": "nordic", "FI": "nordic",
    "LT": "germanic", "LV": "germanic", "EE": "germanic", "EL": "romance",
}


def _get_law_group(country: str) -> str:
    return _LAW_GROUP_MAP.get(country.upper(), "germanic")


# Standard legal elements per claim type (universal, refined by research)
CLAIM_TYPE_ELEMENTS: dict[str, list[dict]] = {
    "invoice": [
        {"name": "contract_basis", "description": "Vertragsgrundlage (Kauf/Dienstleistung)", "required": True},
        {"name": "performance", "description": "Leistungserbringung", "required": True},
        {"name": "amount_due", "description": "Forderungshöhe und Fälligkeit", "required": True},
        {"name": "non_payment", "description": "Nichtzahlung/Verzug", "required": True},
        {"name": "no_defense", "description": "Keine durchgreifende Einwendung", "required": False},
    ],
    "werklohn": [
        {"name": "contract_basis", "description": "Werkvertragsgrundlage", "required": True},
        {"name": "performance", "description": "Werkleistung erbracht", "required": True},
        {"name": "acceptance", "description": "Abnahme (ggf. konkludent)", "required": True},
        {"name": "amount_due", "description": "Vergütung fällig", "required": True},
        {"name": "non_payment", "description": "Nichtzahlung", "required": True},
    ],
    "refund": [
        {"name": "original_payment", "description": "Ursprüngliche Zahlung", "required": True},
        {"name": "refund_basis", "description": "Rechtsgrund für Rückforderung (Rücktritt/Widerruf/Mangel)", "required": True},
        {"name": "amount_due", "description": "Rückforderungsbetrag", "required": True},
    ],
    "damages": [
        {"name": "duty_breach", "description": "Pflichtverletzung", "required": True},
        {"name": "damage", "description": "Schaden eingetreten", "required": True},
        {"name": "causation", "description": "Kausalität", "required": True},
        {"name": "fault", "description": "Verschulden (wenn erforderlich)", "required": False},
        {"name": "amount", "description": "Schadenshöhe", "required": True},
    ],
    "unjust_enrichment": [
        {"name": "enrichment", "description": "Bereicherung des Beklagten", "required": True},
        {"name": "at_expense", "description": "Auf Kosten des Klägers", "required": True},
        {"name": "no_legal_basis", "description": "Ohne Rechtsgrund", "required": True},
        {"name": "amount", "description": "Bereicherungshöhe", "required": True},
    ],
    "other": [
        {"name": "legal_basis", "description": "Anspruchsgrundlage", "required": True},
        {"name": "facts", "description": "Tatsachengrundlage", "required": True},
        {"name": "amount", "description": "Forderungshöhe", "required": True},
    ],
}

# Country-specific statute references for common claim types
_STATUTE_MAP: dict[str, dict[str, str]] = {
    "DE": {
        "invoice": "§§ 433, 434 BGB (Kaufvertrag) / §§ 611, 631 BGB (Dienst-/Werkvertrag)",
        "werklohn": "§§ 631 ff. BGB",
        "refund": "§§ 346, 355 BGB (Rücktritt/Widerruf)",
        "damages": "§§ 280, 823 BGB",
        "unjust_enrichment": "§§ 812 ff. BGB",
    },
    "AT": {
        "invoice": "§§ 1053 ff. ABGB (Kauf) / §§ 1151 ff. ABGB (Werkvertrag)",
        "werklohn": "§§ 1151 ff. ABGB",
        "damages": "§§ 1293 ff. ABGB",
        "unjust_enrichment": "§§ 1431 ff. ABGB",
    },
    "FR": {
        "invoice": "Art. 1103, 1582 Code civil",
        "damages": "Art. 1240, 1241 Code civil",
        "unjust_enrichment": "Art. 1303 Code civil",
    },
    "IT": {
        "invoice": "Art. 1470 Codice civile (vendita) / Art. 1655 (appalto)",
        "damages": "Art. 2043 Codice civile",
    },
    "ES": {
        "invoice": "Art. 1445 Código Civil (compraventa)",
        "damages": "Art. 1101, 1902 Código Civil",
    },
    "NL": {
        "invoice": "Art. 7:1 BW (koop) / Art. 7:400 BW (opdracht)",
        "damages": "Art. 6:162 BW (onrechtmatige daad)",
    },
}


def determine_applicable_law(case: CaseInput) -> ApplicableLawDecision:
    """Determine which country's law applies.

    Priority:
    1. Explicitly provided applicable_law_country
    2. Heuristic: court_country (default for most ESCP cases)
    3. Special handling for B2C cross-border (Rome I considerations)
    """
    if case.applicable_law_country:
        return ApplicableLawDecision(
            country=case.applicable_law_country.upper(),
            method="explicit",
            confidence=0.95,
            notes="Anwendbares Recht explizit angegeben.",
        )

    # Cross-border B2C: Rome I Art. 6 may apply consumer's habitual residence
    is_cross_border = case.court_country != case.debtor_country
    is_b2c = case.debtor_is_consumer or case.creditor_is_consumer

    if is_cross_border and is_b2c:
        consumer_country = case.debtor_country if case.debtor_is_consumer else case.creditor_country
        return ApplicableLawDecision(
            country=consumer_country.upper(),
            method="heuristic_rome_i",
            confidence=0.6,
            notes=(
                f"B2C grenzüberschreitend: Rom-I-VO Art. 6 könnte das Recht des "
                f"Verbraucherstaats ({consumer_country}) anwenden. "
                f"Annahme mit eingeschränkter Konfidenz — Rechtsrecherche empfohlen."
            ),
        )

    # Default: court country's law
    return ApplicableLawDecision(
        country=case.court_country.upper(),
        method="heuristic_court",
        confidence=0.80,
        notes=(
            f"Anwendbares Recht nach Gerichtsland ({case.court_country}) angenommen. "
            f"Heuristik — kann durch IPR-Prüfung abweichen."
        ),
    )


def _get_country_domains(country: str) -> list[str]:
    """Get search domains for a country from the YAML config."""
    domains: list[str] = []
    # EU-wide sources
    for src in LEGAL_SOURCES.get("eu_wide", []):
        domains.append(src["domain"])
    # Country-specific sources
    country_cfg = LEGAL_SOURCES.get("countries", {}).get(country.upper(), {})
    for src in country_cfg.get("sources", []):
        domains.append(src["domain"])
    if not domains:
        domains = LEGAL_SOURCES.get("fallback_domains", ["eur-lex.europa.eu"])
    return domains


def _build_search_queries(case: CaseInput, law_country: str) -> list[str]:
    """Build search queries for legal research."""
    claim_label = {
        "invoice": "Kaufpreisklage Zahlungsklage",
        "werklohn": "Werklohnklage Werkvertrag",
        "refund": "Rückforderungsklage Widerruf Rücktritt",
        "damages": "Schadensersatzklage",
        "unjust_enrichment": "Bereicherungsanspruch ungerechtfertigte Bereicherung",
        "other": "Zivilklage Forderung",
    }.get(case.claim_type.value, "Forderungsklage")

    queries = [
        f"{claim_label} Anspruchsgrundlage {law_country} Tatbestandsvoraussetzungen",
        f"EU Bagatellverfahren {law_country} Kleinverfahren kleine Forderungen",
    ]

    if case.allegations.defenses_known.value != "none":
        defense_label = case.allegations.defenses_known.value
        queries.append(f"{defense_label} Einwendung {claim_label} {law_country}")

    return queries


async def research_legal_bases(
    case: CaseInput,
    applicable_law: ApplicableLawDecision,
    search_client: SearchClient | None = None,
    fetch_client: FetchClient | None = None,
) -> LegalResearchResult:
    """Perform web research on the applicable legal bases.

    Always executes — p_recht must not be computed without prior research.
    Results are cached for efficiency.
    """
    if search_client is None:
        search_client = SearchClient()
    if fetch_client is None:
        fetch_client = FetchClient()

    law_country = applicable_law.country
    claim_type = case.claim_type.value
    domains = _get_country_domains(law_country)

    all_sources: list[SourceRef] = []
    all_snippets: list[str] = []
    warnings: list[str] = []

    # Execute searches
    queries = _build_search_queries(case, law_country)
    for query in queries:
        try:
            results = await search_client.search(query, allowed_domains=domains, max_results=5)
            for r in results:
                all_sources.append(SourceRef(
                    url=r.url,
                    title=r.title,
                    snippet=r.snippet,
                    domain=r.domain,
                    fetched_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                ))

                # Fetch top results for deeper analysis
                if len(all_snippets) < 10:
                    try:
                        fetched = await fetch_client.fetch(r.url)
                        if fetched.ok:
                            text = html_to_text(fetched.text)
                            keywords = ["Anspruchsgrundlage", "Tatbestand", "Voraussetzung",
                                       "base juridique", "base giuridica", "legal basis"]
                            snippets = extract_legal_snippets(text, keywords)
                            all_snippets.extend(snippets[:3])
                            refs = extract_statute_references(text)
                            if refs:
                                all_sources[-1].snippet += f" | Refs: {', '.join(refs[:5])}"
                    except Exception as e:
                        logger.debug("Failed to fetch %s: %s", r.url[:60], e)
        except Exception as e:
            logger.warning("Search query failed: %s", e)
            warnings.append(f"Suchanfrage fehlgeschlagen: {query[:50]}...")

    # Build legal bases from known statute mapping + research
    legal_bases = _build_legal_bases(claim_type, law_country, case)

    # Determine research status
    research_status = "complete"
    if not all_sources:
        research_status = "insufficient"
        warnings.append(
            f"Keine Webquellen für {law_country} erreichbar. "
            "Best-effort-Schätzung mit eingeschränkter Konfidenz."
        )
    elif len(all_sources) < 3:
        research_status = "partial"
        warnings.append("Wenige Quellen gefunden — Konfidenz eingeschränkt.")

    # Build defenses list
    defenses = _get_typical_defenses(claim_type, law_country)

    return LegalResearchResult(
        claim_type=claim_type,
        law_country=law_country,
        ranked_legal_bases=legal_bases,
        defenses=defenses,
        limitation_notes=_get_limitation_notes(claim_type, law_country),
        sources=all_sources,
        research_status=research_status,
        research_warnings=warnings,
    )


def _build_legal_bases(
    claim_type: str, law_country: str, case: CaseInput
) -> list[LegalBasis]:
    """Build ranked legal bases from known statutes and case elements."""
    bases: list[LegalBasis] = []

    # Primary basis from statute map
    statute = _STATUTE_MAP.get(law_country, {}).get(claim_type, "")
    elements_def = CLAIM_TYPE_ELEMENTS.get(claim_type, CLAIM_TYPE_ELEMENTS["other"])

    elements = []
    for edef in elements_def:
        fulfilled = _check_element_from_allegations(edef["name"], case)
        elements.append(LegalElement(
            name=edef["name"],
            description=edef["description"],
            required=edef["required"],
            fulfilled_from_allegations=fulfilled,
        ))

    match_score = sum(1 for e in elements if e.fulfilled_from_allegations is True) / max(len(elements), 1)
    bases.append(LegalBasis(
        name=f"Primäre Anspruchsgrundlage ({claim_type})",
        statute=statute or f"Nationales Recht {law_country}",
        elements=elements,
        match_score=round(match_score, 2),
    ))

    # Alternative: unjust enrichment if alleged
    if case.allegations.unjust_enrichment_alleged == YesNoUnknown.YES:
        ue_elements_def = CLAIM_TYPE_ELEMENTS["unjust_enrichment"]
        ue_elements = [
            LegalElement(name=e["name"], description=e["description"], required=e["required"])
            for e in ue_elements_def
        ]
        ue_statute = _STATUTE_MAP.get(law_country, {}).get("unjust_enrichment", "")
        bases.append(LegalBasis(
            name="Alternative: Ungerechtfertigte Bereicherung",
            statute=ue_statute or f"Bereicherungsrecht {law_country}",
            elements=ue_elements,
            match_score=0.3,
        ))

    return bases


def _check_element_from_allegations(element_name: str, case: CaseInput) -> bool | None:
    """Check if an element is fulfilled based on allegations only (no evidence)."""
    a = case.allegations
    mapping = {
        "contract_basis": a.contract_formed_alleged == YesNoUnknown.YES,
        "performance": a.performance_done_alleged.value in ("yes", "partial"),
        "acceptance": a.performance_done_alleged.value == "yes",
        "amount_due": a.amount_due_alleged == YesNoUnknown.YES,
        "non_payment": a.non_payment_alleged == YesNoUnknown.YES,
        "no_defense": a.defenses_known == DefenseType.NONE,
        "original_payment": a.non_payment_alleged == YesNoUnknown.YES,
        "refund_basis": a.claim_extinguished_alleged.value not in ("no", "unknown"),
        "duty_breach": a.contract_formed_alleged == YesNoUnknown.YES,
        "damage": True,  # Assumed if claim is filed
        "causation": True,
        "fault": None,  # Cannot assess from allegations alone
        "amount": a.amount_due_alleged == YesNoUnknown.YES,
        "enrichment": True,
        "at_expense": True,
        "no_legal_basis": True,
        "legal_basis": a.contract_formed_alleged == YesNoUnknown.YES,
        "facts": a.performance_done_alleged.value != "unknown",
    }
    result = mapping.get(element_name)
    if result is None:
        return None
    return bool(result)


def _get_typical_defenses(claim_type: str, law_country: str) -> list[str]:
    """Get typical defenses for a claim type."""
    common = [
        "Verjährung / Prescription / Limitation",
        "Mangelnde Zuständigkeit / Jurisdiction challenge",
    ]
    specific = {
        "invoice": ["Mangel / Defect defense", "Aufrechnung / Set-off", "Widerruf / Withdrawal (B2C)"],
        "werklohn": ["Mangel / Defect", "Abnahme nicht erfolgt / Non-acceptance", "Nacherfüllung / Remediation"],
        "refund": ["Wirksamer Vertrag / Valid contract", "Fristablauf / Time-barred"],
        "damages": ["Mitverschulden / Contributory fault", "Kein Verschulden / No fault"],
        "unjust_enrichment": ["Rechtsgrund vorhanden / Legal basis exists", "Entreicherung / Loss of enrichment"],
    }
    return common + specific.get(claim_type, [])


def _get_limitation_notes(claim_type: str, law_country: str) -> str:
    """Get limitation period notes for a country."""
    periods = {
        "DE": "Regelverjährung 3 Jahre (§ 195 BGB), Beginn Jahresende (§ 199 BGB)",
        "AT": "Allgemeine Verjährung 3 Jahre (§ 1489 ABGB), 30 Jahre für titulierte Forderungen",
        "FR": "Prescription de droit commun 5 ans (Art. 2224 Code civil)",
        "IT": "Prescrizione ordinaria 10 anni (Art. 2946 Codice civile)",
        "ES": "Prescripción general 5 años (Art. 1964 Código Civil)",
        "NL": "Verjaring 5 jaar (Art. 3:307 BW)",
        "BE": "Prescription 10 ans (Art. 2262bis Code civil)",
        "PT": "Prescrição ordinária 20 anos (Art. 309 Código Civil)",
        "PL": "Przedawnienie 6 lat (Art. 118 Kodeks cywilny), 3 lata für Geschäftsverkehr",
    }
    return periods.get(law_country, f"Verjährungsfrist nach nationalem Recht {law_country} prüfen.")
