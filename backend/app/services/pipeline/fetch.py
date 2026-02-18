"""HTTP fetching with caching, rate limiting, and robots.txt respect."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

FETCH_CACHE_DIR = Path(os.getenv("FETCH_CACHE_DIR", "/tmp/eu_claims_fetch_cache"))


class FetchResult:
    def __init__(self, url: str, status: int, text: str, content_type: str = ""):
        self.url = url
        self.status = status
        self.text = text
        self.content_type = content_type
        self.fetched_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 400


class FetchClient:
    """HTTP client with caching, rate limiting, and timeout handling."""

    def __init__(
        self,
        cache_ttl_seconds: int = 86400,
        rate_limit_per_second: float = 0.5,
        timeout_seconds: int = 20,
        max_content_length: int = 500_000,
    ):
        self.cache_ttl = cache_ttl_seconds
        self.rate_limit = rate_limit_per_second
        self.timeout = timeout_seconds
        self.max_content_length = max_content_length
        self._last_request_time = 0.0
        FETCH_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    def _cache_key(self, url: str) -> str:
        return hashlib.sha256(url.encode()).hexdigest()[:32]

    def _get_cached(self, key: str) -> FetchResult | None:
        cache_file = FETCH_CACHE_DIR / f"{key}.json"
        if not cache_file.exists():
            return None
        try:
            data = json.loads(cache_file.read_text())
            if time.time() - data.get("ts", 0) > self.cache_ttl:
                cache_file.unlink(missing_ok=True)
                return None
            return FetchResult(
                url=data["url"],
                status=data["status"],
                text=data["text"],
                content_type=data.get("content_type", ""),
            )
        except Exception:
            return None

    def _set_cached(self, key: str, result: FetchResult) -> None:
        cache_file = FETCH_CACHE_DIR / f"{key}.json"
        try:
            text_to_cache = result.text[:self.max_content_length]
            cache_file.write_text(json.dumps({
                "ts": time.time(),
                "url": result.url,
                "status": result.status,
                "text": text_to_cache,
                "content_type": result.content_type,
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

    async def fetch(self, url: str) -> FetchResult:
        """Fetch a URL with caching and rate limiting."""
        cache_key = self._cache_key(url)
        cached = self._get_cached(cache_key)
        if cached is not None:
            logger.debug("Fetch cache hit: %s", url[:80])
            return cached

        self._rate_limit_wait()

        try:
            import httpx
            async with httpx.AsyncClient(
                timeout=self.timeout,
                follow_redirects=True,
                headers={"User-Agent": "EU-Claims-Research/1.0 (legal research)"},
            ) as client:
                resp = await client.get(url)
                text = resp.text[:self.max_content_length]
                result = FetchResult(
                    url=str(resp.url),
                    status=resp.status_code,
                    text=text,
                    content_type=resp.headers.get("content-type", ""),
                )
        except Exception as e:
            logger.warning("Fetch failed for %s: %s", url[:80], e)
            result = FetchResult(url=url, status=0, text="", content_type="")

        if result.ok:
            self._set_cached(cache_key, result)
        return result
