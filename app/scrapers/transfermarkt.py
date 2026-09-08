"""Transfermarkt ingestion.

Requests use structured custom headers (User-Agent, Accept-Language, Referer)
to bypass basic anti-bot filters. Transfermarkt aggressively blocks scrapers,
so every network path degrades gracefully: if a request is blocked or parsing
fails we return `None` rather than crashing the pipeline (market value is an
optional, non-blocking enrichment on top of FBref stats).
"""
from __future__ import annotations

import logging
import re
from typing import Optional
from urllib.parse import quote_plus

from bs4 import BeautifulSoup

from app import config
from app.cache.sqlite_cache import SQLiteCache
from app.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class TransfermarktScraper(BaseScraper):
    BASE_URL = "https://www.transfermarkt.com"
    SEARCH_URL = BASE_URL + "/schnellsuche/ergebnis/schnellsuche?query={query}"

    def __init__(self, cache: SQLiteCache, **kwargs) -> None:
        super().__init__(cache, **kwargs)

    def _headers(self) -> dict[str, str]:
        # Use the structured Transfermarkt header set (bypass basic filters).
        return dict(config.TRANSFERMARKT_HEADERS)

    # -------------------------------------------------------------- search
    def search_player(self, name: str) -> list[dict[str, str]]:
        url = self.SEARCH_URL.format(query=quote_plus(name))
        key = f"transfermarkt:search:{name.lower()}"
        try:
            html = self.get(url, cache_key=key, headers=self._headers())
        except Exception as exc:  # noqa: BLE001
            logger.warning("Transfermarkt search failed for %r: %s", name, exc)
            return []

        soup = BeautifulSoup(html, "lxml")
        results: list[dict[str, str]] = []
        # Result rows link to player profile pages.
        for link in soup.select("a[href*='/profil/spieler/']"):
            href = link["href"]
            if href in {r["url"] for r in results}:
                continue
            results.append(
                {
                    "name": link.get_text(strip=True),
                    "url": self.BASE_URL + href,
                }
            )
            if len(results) >= 10:
                break
        return results

    # -------------------------------------------------------------- value
    def get_market_value(self, name: str, player_url: Optional[str] = None) -> Optional[int]:
        """Return the current market value (EUR) for a player, or None.

        `player_url` (an FBref/Transfermarkt profile URL) is optional and only
        used to disambiguate when provided.
        """
        if player_url:
            value = self._parse_market_value_page(player_url)
            if value is not None:
                return value

        results = self.search_player(name)
        for result in results:
            value = self._parse_market_value_page(result["url"])
            if value is not None:
                return value
        return None

    def _parse_market_value_page(self, url: str) -> Optional[int]:
        key = f"transfermarkt:player-page:{url}"
        try:
            html = self.get(url, cache_key=key, headers=self._headers())
        except Exception as exc:  # noqa: BLE001
            logger.warning("Transfermarkt page failed for %s: %s", url, exc)
            return None

        soup = BeautifulSoup(html, "lxml")
        # Market value renders like "€90.00m" / "€900k" inside a specific header.
        for selector in (
            "a.data-header__market-value-wrapper",
            "a.tm-player-market-value",
            ".dataMarktwert",
        ):
            node = soup.select_one(selector)
            if node:
                raw = node.get_text(" ", strip=True)
                parsed = self._parse_value_text(raw)
                if parsed is not None:
                    return parsed

        # Fallback: regex over the page for a currency pattern.
        match = re.search(r"(?:€|EUR)\s*([\d.,]+)\s*(m|M|k|K|bn)?", soup.get_text(" "))
        if match:
            return self._parse_value_text(match.group(0))
        return None

    @staticmethod
    def _parse_value_text(raw: str) -> Optional[int]:
        """Convert Transfermarkt value strings like '€90.00m' / '€900k' to EUR."""
        if not raw:
            return None
        # Keep only digits, dots, commas and the m/k/b suffix.
        cleaned = re.sub(r"[^0-9.,mMkKbB]", "", raw)
        m = re.search(r"([\d.,]+)\s*([mMkKbB])?", cleaned)
        if not m:
            return None
        number = float(m.group(1).replace(",", "."))
        suffix = (m.group(2) or "").lower()
        if suffix == "m":
            number *= 1_000_000
        elif suffix == "k":
            number *= 1_000
        elif suffix == "b":
            number *= 1_000_000_000
        return int(number)
