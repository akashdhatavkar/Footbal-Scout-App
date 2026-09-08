"""Test helper factories."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.models import Player  # noqa: E402

_FEATURES = (
    "goals_p90", "assists_p90", "shots_p90", "shots_on_target_p90",
    "npxg_p90", "xa_p90", "key_passes_p90", "pass_completion_pct",
    "progressive_passes_p90", "progressive_carries_p90",
    "successful_take_ons_p90", "tackles_p90", "interceptions_p90",
    "blocks_p90", "aerial_duels_won_p90", "touches_p90",
)


def make_player(
    pid: str,
    name: str,
    position: str = "MF",
    club: str = "Arsenal",
    league: str = "Premier League",
    tier: str = "top5",
    exp: int = 8,
    mv: int | None = 90_000_000,
    **features: float,
) -> Player:
    parts = name.split()
    first, last = parts[0], " ".join(parts[1:])
    defaults = {f: 0.0 for f in _FEATURES}
    defaults.update(features)
    return Player(
        player_id=pid,
        name=name,
        first_name=first,
        last_name=last,
        position=position,
        club=club,
        league=league,
        league_tier=tier,
        age=max(18, exp + 18),
        experience_years=exp,
        market_value_eur=mv,
        source_url=None,
        features=defaults,
    )
