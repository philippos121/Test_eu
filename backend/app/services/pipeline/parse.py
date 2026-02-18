"""HTML/text parsing utilities for extracting legal information."""
from __future__ import annotations

import re
import logging

logger = logging.getLogger(__name__)


def html_to_text(html: str, max_length: int = 50_000) -> str:
    """Convert HTML to plain text, stripping tags and normalizing whitespace."""
    # Remove script/style blocks
    text = re.sub(r'<(script|style)[^>]*>.*?</\1>', '', html, flags=re.DOTALL | re.IGNORECASE)
    # Remove HTML tags
    text = re.sub(r'<[^>]+>', ' ', text)
    # Decode common entities
    text = text.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
    text = text.replace('&quot;', '"').replace('&#39;', "'").replace('&nbsp;', ' ')
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:max_length]


def extract_legal_snippets(text: str, keywords: list[str], context_chars: int = 300) -> list[str]:
    """Extract text snippets around keyword matches."""
    snippets: list[str] = []
    text_lower = text.lower()
    for kw in keywords:
        kw_lower = kw.lower()
        start = 0
        while True:
            idx = text_lower.find(kw_lower, start)
            if idx == -1:
                break
            snippet_start = max(0, idx - context_chars)
            snippet_end = min(len(text), idx + len(kw) + context_chars)
            snippet = text[snippet_start:snippet_end].strip()
            if snippet_start > 0:
                snippet = "..." + snippet
            if snippet_end < len(text):
                snippet = snippet + "..."
            snippets.append(snippet)
            start = idx + len(kw)
            if len(snippets) >= 5:
                break
        if len(snippets) >= 10:
            break
    return snippets


def extract_statute_references(text: str) -> list[str]:
    """Extract statute references like '§ 433 BGB', 'Art. 7 EuGVVO', etc."""
    patterns = [
        r'§\s*\d+[a-z]?\s*(?:Abs\.\s*\d+)?\s*(?:S\.\s*\d+)?\s*[A-ZÄÖÜ][A-Za-zÄÖÜäöüß]+',
        r'Art\.?\s*\d+\s*(?:Abs\.\s*\d+)?\s*(?:lit\.\s*[a-z])?\s*[A-ZÄÖÜ][A-Za-zÄÖÜäöüß]*(?:\s*[A-ZÄÖÜ][A-Za-zÄÖÜäöüß]*)?',
        r'[Aa]rticle\s+\d+(?:\(\d+\))?',
        r'[Ss]ection\s+\d+(?:\(\d+\))?',
    ]
    refs: list[str] = []
    for pattern in patterns:
        matches = re.findall(pattern, text)
        refs.extend(m.strip() for m in matches)
    # Deduplicate preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for r in refs:
        if r not in seen:
            seen.add(r)
            unique.append(r)
    return unique[:20]


def extract_key_legal_terms(text: str, language: str = "de") -> list[str]:
    """Extract key legal terms from text based on language."""
    term_sets = {
        "de": [
            "Anspruchsgrundlage", "Kaufvertrag", "Werkvertrag", "Dienstleistung",
            "Schadensersatz", "Gewährleistung", "Verjährung", "Fälligkeit",
            "Mahnung", "Verzug", "Aufrechnung", "Rücktritt", "Bereicherung",
            "Zuständigkeit", "Vollstreckung", "Insolvenz", "Bagatellverfahren",
        ],
        "fr": [
            "base juridique", "contrat de vente", "prestation de services",
            "dommages-intérêts", "prescription", "exécution", "insolvabilité",
        ],
        "it": [
            "base giuridica", "contratto di vendita", "prestazione di servizi",
            "risarcimento danni", "prescrizione", "esecuzione", "insolvenza",
        ],
        "es": [
            "base jurídica", "contrato de compraventa", "prestación de servicios",
            "indemnización", "prescripción", "ejecución", "insolvencia",
        ],
    }
    terms = term_sets.get(language, term_sets["de"])
    text_lower = text.lower()
    found = [t for t in terms if t.lower() in text_lower]
    return found
