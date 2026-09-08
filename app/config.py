"""Central configuration for the Football Stats App.

All tunable knobs (weights, thresholds, cache TTL, scraper behaviour) live here
so the rest of the codebase stays declarative and easy to audit.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Load a local `.env` if present (values are optional; defaults below still apply).
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
CACHE_DIR = BASE_DIR / ".cache"
DATA_DIR.mkdir(exist_ok=True, parents=True)
CACHE_DIR.mkdir(exist_ok=True, parents=True)

# ---------------------------------------------------------------------------
# Caching
# ---------------------------------------------------------------------------
SQLITE_CACHE_PATH = os.getenv("SQLITE_CACHE_PATH", str(CACHE_DIR / "football_cache.db"))
# 24-hour TTL in seconds (requirement).
CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", str(24 * 60 * 60)))

# ---------------------------------------------------------------------------
# Scraper behaviour
# ---------------------------------------------------------------------------
FBREF_MIN_SLEEP = float(os.getenv("FBREF_MIN_SLEEP", "2.0"))
FBREF_MAX_SLEEP = float(os.getenv("FBREF_MAX_SLEEP", "5.0"))
SCRAPER_TIMEOUT_SECONDS = int(os.getenv("SCRAPER_TIMEOUT_SECONDS", "30"))
SCRAPER_MAX_RETRIES = int(os.getenv("SCRAPER_MAX_RETRIES", "2"))

# Randomized User-Agent pool for FBref ingestion.
USER_AGENTS: list[str] = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
]

# Structured custom headers for Transfermarkt (basic anti-bot bypass).
TRANSFERMARKT_HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,*/*;q=0.8",
    "Referer": "https://www.transfermarkt.com/",
}

# ---------------------------------------------------------------------------
# Entity resolution
# ---------------------------------------------------------------------------
# Fuzzy ratio threshold (0-100). Requirement: ratio >= 85.
FUZZY_MATCH_THRESHOLD = int(os.getenv("FUZZY_MATCH_THRESHOLD", "85"))

# ---------------------------------------------------------------------------
# League / experience weighting (strict multipliers)
# ---------------------------------------------------------------------------
TOP5_LEAGUES: set[str] = {
    l.strip()
    for l in os.getenv(
        "TOP5_LEAGUES", "Premier League,La Liga,Serie A,Bundesliga,Ligue 1"
    ).split(",")
    if l.strip()
}

# League weighting: 0.60 Top-5 European Leagues, 0.40 Rest of World.
LEAGUE_WEIGHT_TOP5 = 0.60
LEAGUE_WEIGHT_ROW = 0.40

# Experience weighting: 0.55 for >= 5 years senior experience, 0.45 for < 5 years.
EXPERIENCE_WEIGHT_SENIOR = 0.55
EXPERIENCE_WEIGHT_JUNIOR = 0.45
SENIOR_YEARS_THRESHOLD = 5

# ---------------------------------------------------------------------------
# Similarity engine
# ---------------------------------------------------------------------------
# Number of "most similar players" returned by default.
TOP_K = 5

# Global, position-agnostic per-90 feature set. Each feature also carries a
# relative importance weight used by the weighted cosine similarity. Weights
# are applied per-dimension BEFORE the league/experience multipliers are applied
# to the final ranking score.
FEATURES: list[str] = [
    "goals_p90",
    "assists_p90",
    "shots_p90",
    "shots_on_target_p90",
    "npxg_p90",
    "xa_p90",
    "key_passes_p90",
    "pass_completion_pct",
    "progressive_passes_p90",
    "progressive_carries_p90",
    "successful_take_ons_p90",
    "tackles_p90",
    "interceptions_p90",
    "blocks_p90",
    "aerial_duels_won_p90",
    "touches_p90",
]

# Default per-feature importance weights (must sum to anything; they are
# normalised inside the engine). Offensive/creative metrics are weighted higher
# because "statistical profile similarity" is usually dominated by output and
# chance creation, but every position contributes (no positional filtering).
FEATURE_WEIGHTS: dict[str, float] = {
    "goals_p90": 1.30,
    "assists_p90": 1.20,
    "shots_p90": 1.00,
    "shots_on_target_p90": 1.00,
    "npxg_p90": 1.20,
    "xa_p90": 1.10,
    "key_passes_p90": 1.10,
    "pass_completion_pct": 0.90,
    "progressive_passes_p90": 1.00,
    "progressive_carries_p90": 1.00,
    "successful_take_ons_p90": 0.90,
    "tackles_p90": 0.70,
    "interceptions_p90": 0.60,
    "blocks_p90": 0.50,
    "aerial_duels_won_p90": 0.50,
    "touches_p90": 0.80,
}
