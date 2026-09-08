"""Core data models for the Football Stats App.

Uses stdlib dataclasses so the models are framework-agnostic and can be
serialised to/from JSON anywhere (FastAPI, Workers, Streamlit, SQLite cache).
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Optional


@dataclass
class Player:
    """A football player with identity, context and a per-90 statistical profile."""

    player_id: str
    name: str
    first_name: str
    last_name: str
    position: str
    club: str
    league: str
    league_tier: str  # "top5" or "row"
    age: int
    experience_years: int  # years of senior (first-team) experience
    market_value_eur: Optional[int] = None
    source_url: Optional[str] = None
    # Per-90 statistical profile (keys match app.config.FEATURES).
    features: dict[str, float] = field(default_factory=dict)

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Player":
        return cls(**data)


@dataclass
class SimilarityResult:
    """A single ranked "similar player" outcome."""

    rank: int
    player: Player
    cosine_similarity: float  # raw statistical similarity in [0, 1]
    league_multiplier: float  # 0.60 or 0.40
    experience_multiplier: float  # 0.55 or 0.45
    final_score: float  # cosine * league_multiplier * experience_multiplier

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        # Flatten the player for friendlier API/UI consumption.
        data["player"] = self.player.to_dict()
        return data


@dataclass
class PlayerMatch:
    """Result of resolving a query string against a corpus of players."""

    query: str
    player: Player
    match_type: str  # "exact" | "fuzzy"
    confidence: float  # 0-100
