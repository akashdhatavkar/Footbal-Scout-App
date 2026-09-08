# System Architecture

## Overview

A global football analytics application that resolves a player by name, fetches
their per-90 statistical profile (FBref) and current market value (Transfermarkt),
then ranks the top-5 most similar players worldwide using a weighted cosine
similarity engine.

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│                              CLIENTS                                        │
│   Streamlit (ui/app.py)      Lightweight React (frontend/index.html)        │
│        FastAPI (app/api)        Cloudflare Pages (static)                    │
└──────────────┬───────────────────────────────┬───────────────────────────────┘
               │  HTTP                         │  HTTP
               ▼                               ▼
┌──────────────────────────────┐   ┌───────────────────────────────────────────┐
│   FastAPI backend (Python)   │   │  Cloudflare Workers (Python, edge)         │
│   app/api/main.py            │   │  workers/index.py  (dependency-free)       │
│                              │   │  - reads pre-seeded corpus                 │
│   ┌────────────────────────┐ │   │  - exact + fuzzy entity resolution        │
│   │  Pipeline (app/pipeline)│ │   │  - standardize + weighted cosine          │
│   │  orchestrator          │ │   │  - league/experience multipliers           │
│   └───────────┬────────────┘ │   └───────────────────────────────────────────┘
└───────────────┼──────────────┘
                │
   ┌────────────▼─────────────┐
   │   Entity Resolution      │  app/matching/entity_matcher.py
   │   1. exact first+last    │  unidecode normalisation
   │   2. rapidfuzz ratio>=85 │  difflib fallback
   └────────────┬─────────────┘
                │
   ┌────────────▼─────────────┐
   │   Similarity Engine      │  app/similarity/engine.py
   │   1. standardize per-90  │  sklearn StandardScaler (global, no position filter)
   │   2. weighted cosine     │  per-feature importance weights
   │   3. final score =       │  cosine * league(0.6/0.4) * exp(0.55/0.45)
   └────────────┬─────────────┘
                │
   ┌────────────▼─────────────┐
   │   Ingestion              │  app/scrapers/*
   │   FBref:                 │  requests + random UA pool + 2-5s sleep
   │     pandas.read_html     │  strip lazy-load HTML comments
   │   Transfermarkt:         │  structured headers (UA/Accept-Language/Referer)
   └────────────┬─────────────┘
                │
   ┌────────────▼─────────────┐
   │   Caching (24h TTL)      │  app/cache/sqlite_cache.py
   │   SQLite: key->JSON      │  expires_at indexed, thread-safe
   └──────────────────────────┘
```

## Data flow

1. **Ingestion** — `FBrefScraper` performs HTTP GETs with a randomised
   User-Agent pool and a randomised 2–5s pause. `TransfermarktScraper` sends
   structured headers and degrades gracefully if blocked.
2. **Caching** — every URL lookup goes through `SQLiteCache`. A hit within
   24 hours returns stored JSON and never touches the network.
3. **Entity resolution** — `EntityMatcher` normalises names (unidecode +
   lowercase) and tries an exact `first_name + last_name` match, then falls back
   to `rapidfuzz.fuzz.ratio >= 85`.
4. **Similarity vectorization** — `SimilarityEngine` builds a global feature
   matrix (16 per-90 metrics), standardises with `StandardScaler`, computes a
   weighted cosine similarity, then applies league and experience multipliers.
5. **API / UI** — FastAPI serves `/similar`; Streamlit and a lightweight React
   app consume it. A dependency-free Cloudflare Worker serves the same read path
   at the edge.

## Weighting model

### Per-feature importance (weighted cosine)
Each per-90 metric carries a relative weight (see `config.FEATURE_WEIGHTS`),
used inside the weighted cosine similarity so chance creation and output drive
profile similarity more than raw defensive volume.

### League multiplier
`0.60` for the Top-5 European leagues (Premier League, La Liga, Serie A,
Bundesliga, Ligue 1), `0.40` for Rest of World.

### Experience multiplier
`0.55` for players with ≥5 years of senior experience, `0.45` for <5 years.

### Why the multipliers are applied at ranking time
Cosine similarity is scale-invariant — multiplying an entire vector by a scalar
cancels out in the numerator and denominator. The league/experience factors are
therefore applied as a **profile-quality weight** to the final score:

```
final_score = weighted_cosine * league_multiplier * experience_multiplier
```

The raw cosine is always returned alongside so the pure statistical similarity
remains inspectable.

## Key modules

| Module | Responsibility |
| --- | --- |
| `app/config.py` | all tunables: weights, thresholds, TTL, UA pool |
| `app/models.py` | `Player`, `SimilarityResult` dataclasses |
| `app/cache/sqlite_cache.py` | 24h TTL SQLite cache |
| `app/scrapers/base.py` | shared HTTP + cache + politeness plumbing |
| `app/scrapers/fbref.py` | FBref search + player page parsing |
| `app/scrapers/transfermarkt.py` | Transfermarkt market value |
| `app/matching/entity_matcher.py` | exact + fuzzy resolution |
| `app/similarity/engine.py` | standardise + weighted cosine + multipliers |
| `app/pipeline.py` | orchestrator |
| `app/api/main.py` | FastAPI routes |
| `ui/app.py` | Streamlit UI |
| `workers/index.py` | dependency-free Cloudflare Workers (Python) |
