# Football Stats App

A global football analytics application that evaluates player statistical
profiles and market values. Search any player (e.g. **Martin Ødegaard**) to see
their per-90 stats, current market value (Transfermarkt) and the **top-5 most
similar players worldwide** based on statistical profile (FBref).

## Features

- **FBref ingestion** — HTTP GET with a randomised User-Agent pool and a
  randomised 2–5s pause; tables parsed with `pandas.read_html`/BeautifulSoup
  (no Selenium).
- **Transfermarkt ingestion** — structured headers (`User-Agent`,
  `Accept-Language`, `Referer`) to bypass basic anti-bot filters; degrades
  gracefully when blocked.
- **24-hour caching** — SQLite TTL cache; repeat scrapes within 24h hit cache.
- **Entity resolution** — exact `first_name + last_name` match, then
  `rapidfuzz.fuzz.ratio >= 85` fuzzy fallback (accent/Unicode aware).
- **Global similarity engine** — 16 standardised per-90 metrics across all
  positions (no positional filtering), weighted cosine similarity, plus strict
  league (`0.60`/`0.40`) and experience (`0.55`/`0.45`) multipliers.
- **FastAPI backend** + **Streamlit** and **lightweight React** frontends.
- **Cloudflare-ready** — Workers (Python) edge worker, Pages frontend, and a
  containerised FastAPI option.

## Project layout

```
app/               # FastAPI backend, scrapers, cache, matcher, similarity, pipeline
ui/                # Streamlit frontend
frontend/          # lightweight React frontend (Cloudflare Pages)
workers/           # dependency-free Cloudflare Workers (Python)
scripts/           # corpus seed + live corpus builder
tests/             # pytest suite
docs/              # ARCHITECTURE.md + CLOUDFLARE_DEPLOYMENT.md
data/              # generated sample_players.json corpus
```

## Quickstart

```bash
# 1. Install (uv recommended; pip fallback)
uv sync --extra dev || pip install -r requirements.txt

# 2. Seed the demo corpus (already generated at data/sample_players.json)
uv run python scripts/seed_demo.py

# 3. Run the API
uv run uvicorn app.api.main:app --reload
#    → http://127.0.0.1:8000/docs

# 4. Run the Streamlit UI (separate terminal)
uv run streamlit run ui/app.py
```

Try it:

```bash
curl "http://127.0.0.1:8000/similar?query=Martin%20%C3%98degaard&k=5"
```

## Tests

```bash
uv run pytest
```

## Documentation

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — architecture diagram & weighting model
- [`docs/CLOUDFLARE_DEPLOYMENT.md`](docs/CLOUDFLARE_DEPLOYMENT.md) — Cloudflare deployment guide

## Notes & assumptions

- The bundled `data/sample_players.json` is **illustrative seed data** so the
  pipeline runs end-to-end offline. Replace it with `scripts/build_corpus.py`
  (live FBref scraping) for production.
- Senior experience is estimated as `max(0, age - 18)` when scraping live; the
  corpus can store explicit `experience_years` where known.
- Market value is optional and best-effort: Transfermarkt aggressively blocks
  scrapers, so the pipeline returns `None` rather than failing.
