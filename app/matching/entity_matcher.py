"""Entity resolution between FBref and Transfermarkt player names.

Strategy (per requirements):
1. Exact match on normalised first_name + last_name.
2. Fallback to fuzzy string matching (rapidfuzz `ratio`, with a stdlib difflib
   fallback) using a set similarity threshold of ratio >= 85 to resolve
   spelling variations and accents.

Normalisation lowercases, strips accents (via unidecode) and collapses
whitespace so "Martin Ødegaard" == "martin odegaard" and "Ødegaard" ==
"Odegaard".
"""
from __future__ import annotations

import logging
from typing import Iterable, Optional, Sequence

from unidecode import unidecode

try:  # rapidfuzz is the preferred engine; difflib is a zero-dependency fallback.
    from rapidfuzz import fuzz
    from rapidfuzz.utils import default_process

    def _ratio(a: str, b: str) -> float:
        return float(fuzz.ratio(default_process(a), default_process(b)))

except ImportError:  # pragma: no cover - exercised only when rapidfuzz absent
    import difflib

    def _ratio(a: str, b: str) -> float:
        return float(difflib.SequenceMatcher(None, a, b).ratio() * 100)


from app import config
from app.models import Player

logger = logging.getLogger(__name__)


class EntityMatcher:
    """Resolves query strings against a corpus of Player objects."""

    def __init__(self, threshold: Optional[int] = None) -> None:
        self.threshold = threshold if threshold is not None else config.FUZZY_MATCH_THRESHOLD

    # ------------------------------------------------------------ normalisation
    @staticmethod
    def normalize(text: str) -> str:
        """Lowercase, strip accents and collapse whitespace."""
        if not text:
            return ""
        return " ".join(unidecode(text).lower().split())

    @staticmethod
    def _full_name(player: Player) -> str:
        return f"{player.first_name} {player.last_name}".strip()

    # ------------------------------------------------------------ matching
    def exact_match(
        self, query_first: str, query_last: str, candidate: Player
    ) -> bool:
        q_first = self.normalize(query_first)
        q_last = self.normalize(query_last)
        c_first = self.normalize(candidate.first_name)
        c_last = self.normalize(candidate.last_name)
        return q_first == c_first and q_last == c_last

    def fuzzy_score(
        self, query_first: str, query_last: str, candidate: Player
    ) -> float:
        """Best fuzzy ratio between the query name and candidate name(s)."""
        query_full = self.normalize(f"{query_first} {query_last}".strip())
        candidate_full = self.normalize(self._full_name(candidate))
        scores = [_ratio(query_full, candidate_full)]
        # Also compare last-name-only for resilience to missing first names.
        scores.append(_ratio(self.normalize(query_last), self.normalize(candidate.last_name)))
        return max(scores)

    def match(
        self, query: str, candidates: Sequence[Player]
    ) -> Optional[Player]:
        """Return the best-matching Player for `query`, exact first then fuzzy."""
        if not candidates:
            return None

        parts = query.strip().split()
        q_first = parts[0] if parts else ""
        # A single-word query ("Pedri") has no separate last name.
        q_last = " ".join(parts[1:])

        # 1) Exact match on normalised first + last name.
        for candidate in candidates:
            if self.exact_match(q_first, q_last, candidate):
                logger.debug("exact match: %s -> %s", query, candidate.name)
                return candidate

        # 2) Fuzzy fallback (ratio >= threshold).
        best: Optional[Player] = None
        best_score = 0.0
        for candidate in candidates:
            score = self.fuzzy_score(q_first, q_last, candidate)
            if score >= self.threshold and score > best_score:
                best = candidate
                best_score = score
        if best is not None:
            logger.debug("fuzzy match: %s -> %s (%.1f)", query, best.name, best_score)
        return best

    def match_with_confidence(
        self, query: str, candidates: Sequence[Player]
    ) -> Optional[dict]:
        """Like match() but returns the match type and confidence score."""
        if not candidates:
            return None
        parts = query.strip().split()
        q_first = parts[0] if parts else ""
        q_last = " ".join(parts[1:])

        for candidate in candidates:
            if self.exact_match(q_first, q_last, candidate):
                return {"player": candidate, "match_type": "exact", "confidence": 100.0}

        best: Optional[Player] = None
        best_score = 0.0
        for candidate in candidates:
            score = self.fuzzy_score(q_first, q_last, candidate)
            if score >= self.threshold and score > best_score:
                best, best_score = candidate, score
        if best is not None:
            return {"player": best, "match_type": "fuzzy", "confidence": best_score}
        return None
