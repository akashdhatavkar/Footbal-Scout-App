"""Orchestration pipeline.

Ties together: ingestion -> caching -> entity resolution -> similarity
vectorization -> (optional) market-value enrichment.

The pipeline is designed to run in two modes:
* `corpus_file` present: loads a local JSON corpus (seeded by scripts/seed_demo.py
  or built by scripts/build_corpus.py). This is the offline/demo path used by
  tests, the FastAPI app and Streamlit when live scraping is disabled.
* `live`: scrapes FBref/Transfermarkt on demand (network access required).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional, Sequence

from app import config
from app.cache.sqlite_cache import SQLiteCache
from app.matching.entity_matcher import EntityMatcher
from app.models import Player, SimilarityResult
from app.scrapers.fbref import FBrefScraper
from app.scrapers.transfermarkt import TransfermarktScraper
from app.similarity.engine import SimilarityEngine

logger = logging.getLogger(__name__)


class Pipeline:
    def __init__(
        self,
        cache: Optional[SQLiteCache] = None,
        corpus_file: Optional[str | Path] = None,
    ) -> None:
        self.cache = cache or SQLiteCache()
        self.matcher = EntityMatcher()
        self.engine = SimilarityEngine()
        self.corpus_file = Path(corpus_file) if corpus_file else config.DATA_DIR / "sample_players.json"

        self._scraper_fbref: Optional[FBrefScraper] = None
        self._scraper_tm: Optional[TransfermarktScraper] = None
        self._corpus: Optional[list[Player]] = None

    # ------------------------------------------------------------ corpus
    @property
    def corpus(self) -> list[Player]:
        if self._corpus is None:
            self._corpus = self.load_corpus()
        return self._corpus

    def load_corpus(self) -> list[Player]:
        if self.corpus_file.exists():
            logger.info("loading corpus from %s", self.corpus_file)
            data = json.loads(self.corpus_file.read_text(encoding="utf-8"))
            return [Player.from_dict(p) for p in data]

        # Fallback: import the bundled sample data so the app works even if the
        # seed script has not been run (no generated JSON present).
        logger.warning("corpus file %s not found - using bundled sample data", self.corpus_file)
        try:
            from scripts.sample_data import SAMPLE_PLAYERS

            return [Player.from_dict(p) for p in SAMPLE_PLAYERS]
        except ImportError:
            logger.error("bundled sample data unavailable - corpus is empty")
            return []

    def save_corpus(self, players: Sequence[Player]) -> None:
        self.corpus_file.parent.mkdir(parents=True, exist_ok=True)
        payload = [p.to_dict() for p in players]
        self.corpus_file.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        self._corpus = list(players)

    # ------------------------------------------------------------ scrapers
    def _fbref(self) -> FBrefScraper:
        if self._scraper_fbref is None:
            self._scraper_fbref = FBrefScraper(self.cache)
        return self._scraper_fbref

    def _transfermarkt(self) -> TransfermarktScraper:
        if self._scraper_tm is None:
            self._scraper_tm = TransfermarktScraper(self.cache)
        return self._scraper_tm

    # ------------------------------------------------------------ lookup
    def resolve(self, query: str) -> Optional[Player]:
        """Resolve a free-text query to a corpus Player (exact -> fuzzy)."""
        return self.matcher.match(query, self.corpus)

    def resolve_confidence(self, query: str) -> Optional[dict]:
        return self.matcher.match_with_confidence(query, self.corpus)

    # ------------------------------------------------------------ main API
    def get_similar(
        self, query: str, k: Optional[int] = None, enrich_market_value: bool = False
    ) -> dict:
        """Return the query player + top-k similar players.

        `enrich_market_value` triggers a live Transfermarkt lookup (best-effort);
        by default market value is read from the corpus and left untouched.
        """
        resolved = self.resolve_confidence(query)
        if resolved is None:
            raise LookupError(f"Player not found in corpus: {query}")
        player: Player = resolved["player"]

        if enrich_market_value and player.market_value_eur is None:
            player.market_value_eur = self._transfermarkt().get_market_value(player.name)

        similar = self.engine.top_similar(player, self.corpus, k=k)
        return {
            "query": query,
            "match_type": resolved["match_type"],
            "confidence": resolved["confidence"],
            "player": player.to_dict(),
            "similar_players": [s.to_dict() for s in similar],
        }

    # ------------------------------------------------------------ live path
    def ingest_live(self, query: str, k: Optional[int] = None) -> dict:
        """Scrape FBref for a player, enrich via Transfermarkt, then rank against
        the local corpus (which should have been built beforehand)."""
        profile = self._fbref().get_player_profile(query)
        player = Player.from_dict(profile)
        try:
            player.market_value_eur = self._transfermarkt().get_market_value(player.name)
        except Exception as exc:  # noqa: BLE001
            logger.warning("market value enrichment failed for %s: %s", player.name, exc)

        similar = self.engine.top_similar(player, self.corpus, k=k)
        return {
            "query": query,
            "match_type": "live",
            "confidence": 100.0,
            "player": player.to_dict(),
            "similar_players": [s.to_dict() for s in similar],
        }
