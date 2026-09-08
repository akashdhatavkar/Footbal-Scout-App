"""Shared HTTP base for the scraping engine.

Provides randomised User-Agent selection, polite randomized pauses, retry/backoff
and transparent integration with the SQLite 24-hour cache. Child scrapers only
implement the *parsing* of their specific site.
"""
from __future__ import annotations

import logging
import random
import time
from typing import Any, Optional

import requests

from app import config
from app.cache.sqlite_cache import SQLiteCache

logger = logging.getLogger(__name__)


class BaseScraper:
    """Common request + cache plumbing for site-specific scrapers."""

    def __init__(
        self,
        cache: SQLiteCache,
        min_sleep: Optional[float] = None,
        max_sleep: Optional[float] = None,
        timeout: Optional[int] = None,
        max_retries: Optional[int] = None,
    ) -> None:
        self.cache = cache
        self.min_sleep = min_sleep if min_sleep is not None else config.FBREF_MIN_SLEEP
        self.max_sleep = max_sleep if max_sleep is not None else config.FBREF_MAX_SLEEP
        self.timeout = timeout or config.SCRAPER_TIMEOUT_SECONDS
        self.max_retries = max_retries if max_retries is not None else config.SCRAPER_MAX_RETRIES
        self.session = requests.Session()

    # -- helpers -------------------------------------------------------------
    def _random_user_agent(self) -> str:
        return random.choice(config.USER_AGENTS)

    def _random_pause(self) -> None:
        """Randomized pause of 2-5 seconds (requirement)."""
        delay = random.uniform(self.min_sleep, self.max_sleep)
        logger.debug("politeness pause %.2fs", delay)
        time.sleep(delay)

    def _headers(self, extra: Optional[dict[str, str]] = None) -> dict[str, str]:
        headers = {"User-Agent": self._random_user_agent()}
        if extra:
            headers.update(extra)
        return headers

    # -- network -------------------------------------------------------------
    def get(
        self,
        url: str,
        cache_key: Optional[str] = None,
        headers: Optional[dict[str, str]] = None,
        ttl: Optional[int] = None,
    ) -> str:
        """GET a URL returning its HTML/text, served from cache when possible.

        On a cache hit the network and politeness pause are skipped entirely.
        On a miss we perform up to `max_retries` attempts with a randomized
        pause between them, then cache the successful response.
        """
        if cache_key is not None:
            cached = self.cache.get(cache_key)
            if cached is not None:
                logger.debug("cache hit: %s", cache_key)
                return cached

        last_error: Optional[Exception] = None
        for attempt in range(1, self.max_retries + 2):
            try:
                resp = self.session.get(
                    url, headers=headers or self._headers(), timeout=self.timeout
                )
                resp.raise_for_status()
                html = resp.text
                if cache_key is not None:
                    self.cache.set(cache_key, html, ttl=ttl)
                return html
            except requests.RequestException as exc:  # noqa: PERF203
                last_error = exc
                logger.warning("GET %s failed (attempt %d): %s", url, attempt, exc)
                if attempt <= self.max_retries:
                    self._random_pause()

        raise RuntimeError(f"Failed to fetch {url} after retries: {last_error}")

    def get_json(
        self,
        url: str,
        cache_key: Optional[str] = None,
        headers: Optional[dict[str, str]] = None,
        ttl: Optional[int] = None,
    ) -> Any:
        """GET a URL expecting a JSON response."""
        # JSON endpoints do not go through the same politeness pause as HTML.
        if cache_key is not None:
            cached = self.cache.get(cache_key)
            if cached is not None:
                return cached
        resp = self.session.get(
            url, headers=headers or self._headers(), timeout=self.timeout
        )
        resp.raise_for_status()
        data = resp.json()
        if cache_key is not None:
            self.cache.set(cache_key, data, ttl=ttl)
        return data
