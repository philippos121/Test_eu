"""External recovery checks: insolvency registers + web signals.

p_eintreibung MUST NOT be computed without these checks.
If checks are not performed, p_eintreibung = None (pending).
"""
from __future__ import annotations

import logging
import time
from typing import Optional

from .models import (
    InsolvencyStatus,
    RecoveryInput,
    RecoverySignal,
    SourceRef,
)
from .search import SearchClient
from .fetch import FetchClient
from .parse import html_to_text, extract_legal_snippets

logger = logging.getLogger(__name__)

# Insolvency-related keywords per language
_INSOLVENCY_KEYWORDS: dict[str, list[str]] = {
    "de": ["insolvenz", "insolvent", "konkurs", "liquidation", "zahlungsunfähig", "überschuldet"],
    "fr": ["insolvabilité", "liquidation judiciaire", "faillite", "cessation de paiements"],
    "it": ["insolvenza", "fallimento", "liquidazione", "concordato preventivo"],
    "es": ["insolvencia", "concurso de acreedores", "liquidación", "quiebra"],
    "nl": ["insolventie", "faillissement", "surseance", "liquidatie"],
    "en": ["insolvency", "insolvent", "bankruptcy", "liquidation", "winding up"],
    "pl": ["niewypłacalność", "upadłość", "likwidacja"],
}

# Country -> primary language for keyword selection
_COUNTRY_LANG: dict[str, str] = {
    "DE": "de", "AT": "de", "FR": "fr", "IT": "it", "ES": "es",
    "NL": "nl", "BE": "fr", "PT": "es", "PL": "pl", "CZ": "de",
    "SK": "de", "HU": "de", "RO": "fr", "BG": "fr", "HR": "de",
    "SI": "de", "LT": "de", "LV": "de", "EE": "de", "FI": "en",
    "SE": "en", "DK": "en", "IE": "en", "MT": "en", "CY": "en",
    "LU": "fr", "EL": "en",
}


class InsolvencyCheckProvider:
    """Check insolvency registers (EU-wide, country-specific)."""

    def __init__(
        self,
        search_client: SearchClient | None = None,
        fetch_client: FetchClient | None = None,
    ):
        self.search = search_client or SearchClient()
        self.fetch = fetch_client or FetchClient()

    async def check(
        self, recovery: RecoveryInput, debtor_country: str
    ) -> tuple[InsolvencyStatus, list[RecoverySignal]]:
        """Check insolvency status via web search.

        Returns (status, signals) where status is one of:
        - SOLVENT: no insolvency signals found
        - INSOLVENT: strong insolvency signals
        - UNKNOWN: couldn't determine (check failed or inconclusive)
        """
        signals: list[RecoverySignal] = []
        lang = _COUNTRY_LANG.get(debtor_country, "en")
        keywords = _INSOLVENCY_KEYWORDS.get(lang, _INSOLVENCY_KEYWORDS["en"])

        # Build search query
        name = recovery.debtor_name
        if not name:
            return InsolvencyStatus.UNKNOWN, [
                RecoverySignal(
                    signal_type="insolvency_register",
                    value="Kein Schuldnername angegeben — Check nicht möglich.",
                    confidence=0.0,
                )
            ]

        query = f'"{name}" {" OR ".join(keywords[:3])} {debtor_country}'

        try:
            results = await self.search.search(query, max_results=5)
            insolvency_hits = 0
            for r in results:
                text_lower = (r.title + " " + r.snippet).lower()
                for kw in keywords:
                    if kw.lower() in text_lower:
                        insolvency_hits += 1
                        signals.append(RecoverySignal(
                            signal_type="insolvency_register",
                            value=f"Treffer: '{kw}' in {r.domain}",
                            confidence=0.6,
                            source=SourceRef(
                                url=r.url, title=r.title, snippet=r.snippet,
                                domain=r.domain,
                                fetched_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                            ),
                        ))
                        break

            if insolvency_hits >= 2:
                return InsolvencyStatus.INSOLVENT, signals
            elif insolvency_hits == 1:
                return InsolvencyStatus.UNKNOWN, signals
            else:
                signals.append(RecoverySignal(
                    signal_type="insolvency_register",
                    value="Keine Insolvenz-Treffer gefunden.",
                    confidence=0.5,
                ))
                return InsolvencyStatus.SOLVENT, signals

        except Exception as e:
            logger.warning("Insolvency check failed: %s", e)
            return InsolvencyStatus.UNKNOWN, [
                RecoverySignal(
                    signal_type="insolvency_register",
                    value=f"Check fehlgeschlagen: {e}",
                    confidence=0.0,
                )
            ]


class WebSignalsProvider:
    """Extract web signals about debtor solvency and reputation."""

    def __init__(
        self,
        search_client: SearchClient | None = None,
        fetch_client: FetchClient | None = None,
    ):
        self.search = search_client or SearchClient()
        self.fetch = fetch_client or FetchClient()

    async def check(
        self, recovery: RecoveryInput, debtor_country: str
    ) -> list[RecoverySignal]:
        """Search for web signals about the debtor."""
        signals: list[RecoverySignal] = []
        name = recovery.debtor_name
        if not name:
            return signals

        # Search for negative signals
        negative_keywords = [
            "Beschwerde", "complaint", "Betrug", "fraud", "Nichtzahlung",
            "non-payment", "Warnung", "warning",
        ]
        query = f'"{name}" {" OR ".join(negative_keywords[:4])}'

        try:
            results = await self.search.search(query, max_results=5)
            negative_hits = 0
            for r in results:
                text_lower = (r.title + " " + r.snippet).lower()
                for kw in negative_keywords:
                    if kw.lower() in text_lower:
                        negative_hits += 1
                        signals.append(RecoverySignal(
                            signal_type="web_signal",
                            value=f"Negatives Signal: '{kw}' via {r.domain}",
                            confidence=0.4,
                            source=SourceRef(
                                url=r.url, title=r.title, snippet=r.snippet,
                                domain=r.domain,
                                fetched_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                            ),
                        ))
                        break

            if negative_hits == 0:
                signals.append(RecoverySignal(
                    signal_type="web_signal",
                    value="Keine negativen Web-Signale gefunden.",
                    confidence=0.5,
                ))

        except Exception as e:
            logger.warning("Web signals check failed: %s", e)

        return signals
