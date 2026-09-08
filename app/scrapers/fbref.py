"""FBref ingestion.

Standard HTTP GET requests with a randomised User-Agent pool and a randomised
2-5 second pause between requests. Tables are parsed with pandas.read_html /
BeautifulSoup (no Selenium / browser drivers).

FBref wraps its stat tables in HTML comments for lazy loading, so we strip the
comment markers before handing the page to pandas. Schema drift on FBref is
common, so parsing is best-effort and degrades gracefully (unknown columns are
simply ignored).
"""
from __future__ import annotations

import logging
import re
from typing import Any, Optional
from urllib.parse import quote_plus

import pandas as pd
from bs4 import BeautifulSoup
from unidecode import unidecode

from app import config
from app.cache.sqlite_cache import SQLiteCache
from app.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

# Map FBref column labels -> our canonical feature keys (see config.FEATURES).
FBREF_COLUMN_MAP: dict[str, str] = {
    "Gls": "goals_p90",
    "Ast": "assists_p90",
    "Sh": "shots_p90",
    "SoT": "shots_on_target_p90",
    "npxG": "npxg_p90",
    "xAG": "xa_p90",
    "xA": "xa_p90",
    "KP": "key_passes_p90",
    "Cmp%": "pass_completion_pct",
    "PrgP": "progressive_passes_p90",
    "PrgC": "progressive_carries_p90",
    "Succ": "successful_take_ons_p90",
    "Tkl": "tackles_p90",
    "Int": "interceptions_p90",
    "Blocks": "blocks_p90",
    "Won": "aerial_duels_won_p90",
    "Touches": "touches_p90",
}

# Competitions codes -> human league name (used to derive league & tier).
COMPETITION_TO_LEAGUE: dict[str, str] = {
    "Premier League": "Premier League",
    "La Liga": "La Liga",
    "Serie A": "Serie A",
    "Bundesliga": "Bundesliga",
    "Ligue 1": "Ligue 1",
}


class FBrefScraper(BaseScraper):
    BASE_URL = "https://fbref.com"
    SEARCH_URL = BASE_URL + "/en/search/search.fcgi?search={query}"

    def search_player(self, name: str) -> list[dict[str, str]]:
        """Return a list of candidate player links for a search term."""
        url = self.SEARCH_URL.format(query=quote_plus(name))
        key = f"fbref:search:{name.lower()}"
        html = self.get(url, cache_key=key)
        self._random_pause()

        soup = BeautifulSoup(html, "lxml")
        results: list[dict[str, str]] = []
        for item in soup.select("div.search-item-name"):
            link = item.find("a", href=re.compile(r"/en/players/"))
            if not link:
                continue
            desc = item.find_next_sibling("div", class_="search-item-desc")
            results.append(
                {
                    "name": link.get_text(strip=True),
                    "url": self.BASE_URL + link["href"],
                    "description": desc.get_text(" ", strip=True) if desc else "",
                }
            )
        return results

    # ------------------------------------------------------------------ pages
    def get_player_profile(self, name: str) -> dict[str, Any]:
        """Resolve a player name and return a full profile dict (features + meta).

        This is the primary entry point used by the pipeline. It searches FBref,
        picks the best candidate, then parses the player page.
        """
        results = self.search_player(name)
        if not results:
            raise ValueError(f"No FBref results for player: {name}")
        best = results[0]
        return self.parse_player_page(best["url"], best["name"])

    def parse_player_page(self, url: str, fallback_name: str) -> dict[str, Any]:
        key = f"fbref:player-page:{url}"
        html = self.get(url, cache_key=key)
        self._random_pause()

        soup = BeautifulSoup(html, "lxml")
        meta = self._parse_identity(soup, fallback_name)

        # Strip lazy-load comment markers so pandas can see the tables.
        uncommented = html.replace("<!--", "").replace("-->", "")
        features = self._parse_features(uncommented)
        league, tier = self._derive_league(uncommented)

        return {
            "player_id": self._slug(fallback_name),
            "name": meta["name"],
            "first_name": meta["first_name"],
            "last_name": meta["last_name"],
            "position": meta["position"],
            "club": meta["club"],
            "league": league,
            "league_tier": tier,
            "age": meta["age"],
            "experience_years": self._estimate_experience(meta["age"]),
            "market_value_eur": None,  # populated by Transfermarkt scraper
            "source_url": url,
            "features": features,
        }

    # -------------------------------------------------------------- identity
    def _parse_identity(self, soup: BeautifulSoup, fallback_name: str) -> dict[str, Any]:
        h1 = soup.find("h1")
        name = h1.find("span").get_text(strip=True) if h1 and h1.find("span") else fallback_name

        position = ""
        club = ""
        age = 0
        meta_block = soup.find("div", id="meta")
        if meta_block:
            strong = meta_block.find("strong")
            if strong:
                club = strong.get_text(strip=True)
            meta_text = meta_block.get_text(" ", strip=True)
            pos_match = re.search(r"Position:\s*([\w, -]+)", meta_text)
            if pos_match:
                position = pos_match.group(1).strip()
            born_match = re.search(r"Born:\s*[A-Za-z]+ \d{1,2}, (\d{4})", meta_text)
            if born_match:
                age = self._year_to_age(int(born_match.group(1)))

        first, last = self._split_name(name)
        return {
            "name": name,
            "first_name": first,
            "last_name": last,
            "position": position,
            "club": club,
            "age": age,
        }

    # -------------------------------------------------------------- features
    def _parse_features(self, html: str) -> dict[str, float]:
        """Extract per-90 features from the standard/shooting/passing/defense tables."""
        features: dict[str, float] = {}
        try:
            tables = pd.read_html(html)
        except Exception as exc:  # noqa: BLE001
            logger.warning("pandas.read_html failed: %s", exc)
            return features

        for table in tables:
            self._absorb_table(features, table)
        return features

    def _absorb_table(self, features: dict[str, float], table: pd.DataFrame) -> None:
        """Map a single FBref DataFrame's columns into our feature dict.

        FBref uses duplicate column names for per-90 variants (e.g. "Gls" for
        totals and "Gls.1" for per-90). We prefer the per-90 variant when both
        exist, otherwise use the raw column.
        """
        if table.empty:
            return
        row = table.iloc[-1]  # most recent season

        columns: dict[str, list[tuple[str, bool]]] = {}
        for col in table.columns:
            col_str = str(col)
            base = re.sub(r"\.\d+$", "", col_str)  # strip ".1"/".2" per-90 suffix
            if base in FBREF_COLUMN_MAP:
                is_per90 = col_str != base
                columns.setdefault(base, []).append((col_str, is_per90))

        for base, variants in columns.items():
            variants.sort(key=lambda v: not v[1])  # prefer per-90
            chosen = variants[0][0]
            features[FBREF_COLUMN_MAP[base]] = self._to_float(row.get(chosen))

    @staticmethod
    def _to_float(value: Any) -> float:
        try:
            if pd.isna(value):
                return 0.0
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    # -------------------------------------------------------------- league
    def _derive_league(self, html: str) -> tuple[str, str]:
        """Infer league + tier from the standard table's competition column."""
        try:
            tables = pd.read_html(html)
            for table in tables:
                if "Comp" not in table.columns:
                    continue
                comp = str(table.iloc[-1].get("Comp", ""))
                for code, league in COMPETITION_TO_LEAGUE.items():
                    if code.lower() in comp.lower():
                        return league, self._tier(league)
        except Exception:  # noqa: BLE001
            pass
        return "Rest of World", "row"

    @staticmethod
    def _tier(league: str) -> str:
        return "top5" if league in config.TOP5_LEAGUES else "row"

    # -------------------------------------------------------------- helpers
    @staticmethod
    def _slug(name: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", unidecode(name).lower()).strip("-")
        return slug or "player"

    @staticmethod
    def _split_name(name: str) -> tuple[str, str]:
        parts = name.split()
        if not parts:
            return "", ""
        if len(parts) == 1:
            return parts[0], ""
        return parts[0], " ".join(parts[1:])

    @staticmethod
    def _year_to_age(year: int) -> int:
        from datetime import date

        return max(0, date.today().year - year)

    @staticmethod
    def _estimate_experience(age: int) -> int:
        """Heuristic: senior experience ~= age - 18 (documented approximation)."""
        return max(0, age - 18) if age else 0
