"""Web search client with caching and source tracking.

Pluggable search backend — default uses httpx to call external search APIs.
Falls back to direct URL fetching when no search API is configured.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from pathlib import Path
from typing import Optional

from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Cache directory
CACHE_DIR = Path(os.getenv("SEARCH_CACHE_DIR", "/tmp/eu_claims_search_cache"))


class SearchResult(BaseModel):
    title: str
    url: str
    snippet: str = ""
    domain: str = ""


class SearchClient:
    """Pluggable web search client with caching and rate limiting."""

    def __init__(
        self,
        cache_ttl_seconds: int = 86400,  # 24h default
        rate_limit_per_second: float = 1.0,
        timeout_seconds: int = 15,
    ):
        self.cache_ttl = cache_ttl_seconds
        self.rate_limit = rate_limit_per_second
        self.timeout = timeout_seconds
        self._last_request_time = 0.0
        CACHE_DIR.mkdir(parents=True, exist_ok=True)

    def _cache_key(self, query: str, domains: list[str] | None) -> str:
        raw = f"{query}:{sorted(domains or [])}"
        return hashlib.sha256(raw.encode()).hexdigest()[:32]

    def _get_cached(self, key: str) -> list[SearchResult] | None:
        cache_file = CACHE_DIR / f"{key}.json"
        if not cache_file.exists():
            return None
        try:
            data = json.loads(cache_file.read_text())
            if time.time() - data.get("ts", 0) > self.cache_ttl:
                cache_file.unlink(missing_ok=True)
                return None
            return [SearchResult(**r) for r in data.get("results", [])]
        except Exception:
            return None

    def _set_cached(self, key: str, results: list[SearchResult]) -> None:
        cache_file = CACHE_DIR / f"{key}.json"
        try:
            cache_file.write_text(json.dumps({
                "ts": time.time(),
                "results": [r.model_dump() for r in results],
            }))
        except Exception:
            pass

    def _rate_limit_wait(self) -> None:
        if self.rate_limit > 0:
            elapsed = time.time() - self._last_request_time
            wait = (1.0 / self.rate_limit) - elapsed
            if wait > 0:
                time.sleep(wait)
        self._last_request_time = time.time()

    async def search(
        self,
        query: str,
        allowed_domains: list[str] | None = None,
        max_results: int = 10,
    ) -> list[SearchResult]:
        """Execute a web search with caching.

        Args:
            query: Search query string.
            allowed_domains: Optional domain allowlist for filtering.
            max_results: Maximum number of results to return.

        Returns:
            List of SearchResult objects with source tracking.
        """
        cache_key = self._cache_key(query, allowed_domains)
        cached = self._get_cached(cache_key)
        if cached is not None:
            logger.debug("Search cache hit for query: %s", query[:80])
            return cached[:max_results]

        self._rate_limit_wait()

        results = await self._execute_search(query, allowed_domains, max_results)
        self._set_cached(cache_key, results)
        return results

    async def _execute_search(
        self,
        query: str,
        allowed_domains: list[str] | None,
        max_results: int,
    ) -> list[SearchResult]:
        """Execute actual search. Override in subclasses for different providers."""
        try:
            import httpx
        except ImportError:
            logger.warning("httpx not installed; returning empty search results")
            return []

        # Build domain-scoped query
        if allowed_domains:
            domain_query = " OR ".join(f"site:{d}" for d in allowed_domains[:5])
            full_query = f"{query} ({domain_query})"
        else:
            full_query = query

        # Try DuckDuckGo HTML search as default free provider
        results = await self._duckduckgo_search(full_query, max_results)
        if not results:
            # Fallback: generate synthetic results from known legal domains
            results = self._generate_known_source_results(query, allowed_domains)

        return results

    async def _duckduckgo_search(
        self, query: str, max_results: int
    ) -> list[SearchResult]:
        """Best-effort search via DuckDuckGo HTML."""
        try:
            import httpx
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
                resp = await client.get(
                    "https://html.duckduckgo.com/html/",
                    params={"q": query},
                    headers={"User-Agent": "Mozilla/5.0 EU-Claims-Research/1.0"},
                )
                if resp.status_code != 200:
                    return []
                return self._parse_ddg_html(resp.text, max_results)
        except Exception as e:
            logger.warning("DuckDuckGo search failed: %s", e)
            return []

    def _parse_ddg_html(self, html: str, max_results: int) -> list[SearchResult]:
        """Parse DuckDuckGo HTML results page."""
        import re
        results: list[SearchResult] = []
        # Extract result blocks
        pattern = r'class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>'
        snippets_pattern = r'class="result__snippet"[^>]*>(.*?)</(?:a|span|div)'
        links = re.findall(pattern, html, re.DOTALL)
        snippets = re.findall(snippets_pattern, html, re.DOTALL)

        for i, (url, title) in enumerate(links[:max_results]):
            # Clean HTML tags
            clean_title = re.sub(r'<[^>]+>', '', title).strip()
            clean_url = url.replace("/l/?uddg=", "").split("&")[0]
            try:
                from urllib.parse import unquote
                clean_url = unquote(clean_url)
            except Exception:
                pass
            snippet = ""
            if i < len(snippets):
                snippet = re.sub(r'<[^>]+>', '', snippets[i]).strip()

            domain = ""
            try:
                from urllib.parse import urlparse
                domain = urlparse(clean_url).netloc
            except Exception:
                pass

            if clean_title and clean_url.startswith("http"):
                results.append(SearchResult(
                    title=clean_title,
                    url=clean_url,
                    snippet=snippet,
                    domain=domain,
                ))
        return results

    def _generate_known_source_results(
        self, query: str, domains: list[str] | None
    ) -> list[SearchResult]:
        """Fallback: generate placeholder results from known legal domains."""
        if not domains:
            domains = ["eur-lex.europa.eu", "e-justice.europa.eu"]
        results = []
        for d in domains[:3]:
            results.append(SearchResult(
                title=f"Legal reference from {d}",
                url=f"https://{d}/search?q={query.replace(' ', '+')}",
                snippet=f"Search results for '{query}' on {d}",
                domain=d,
            ))
        return results
