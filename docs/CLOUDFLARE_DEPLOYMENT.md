# Cloudflare Deployment Guide

The app is split into three independently deployable pieces, each with a
recommended Cloudflare product:

| Component | Cloudflare product |
| --- | --- |
| Frontend (React) | **Cloudflare Pages** (static site) |
| Backend API | **Cloudflare Workers (Python, beta)** or **Cloudflare Containers** (beta) |
| Cache / corpus | Workers **KV / R2** (optional) or the bundled seed corpus |

> **Recommendation** — For the read path, use the dependency-free
> `workers/index.py` on Cloudflare Workers (Python). For the full ML stack
> (scikit-learn / pandas / FastAPI), use Cloudflare Containers, or keep the
> canonical FastAPI backend on any container host.

---

## 1. Frontend — Cloudflare Pages

`frontend/index.html` is a single self-contained React page (React UMD, no build
step). To deploy:

1. Point it at your deployed API by editing one line in
   `frontend/index.html`:

   ```js
   const API_URL = "https://football-api.YOUR_SUBDOMAIN.workers.dev";
   ```

2. From the Cloudflare dashboard → **Workers & Pages → Create → Pages → Direct Upload**
   (or **Git integration** pointing at this repo with build command empty and
   output directory `frontend`).

3. For Git integration:
   - **Build command:** *(leave empty)*
   - **Build output directory:** `frontend`

For a production React app, replace the UMD/CDN approach with a Vite or Next.js
build (Cloudflare has first-class `React + Vite` and `Next.js` framework guides).

---

## 2. Backend — Cloudflare Workers (Python, open beta)

Python Workers are in **open beta** and require the `python_workers`
compatibility flag (already set in `wrangler.toml`).

### 2a. Install prerequisites

Python Workers use [`pywrangler`](https://developers.cloudflare.com/workers/languages/python/)
with `uv` and Node.js:

```bash
# one-time project scaffold (creates pyproject.toml + wrangler config)
uvx --from workers-py pywrangler init

# local dev server
uv run pywrangler dev

# deploy
uv run pywrangler deploy
```

`pyproject.toml` in this repo already declares `workers-py` as a dev dependency.

### 2b. Bundle the corpus

`workers/index.py` imports `workers/data.py`, which re-exports the corpus from
`scripts/sample_data.py`. Ensure both `workers/` and `scripts/` are included in
the bundle (Wrangler bundles the Worker entry and its imports automatically).

To freeze the corpus as a static JSON file at build time instead:

```bash
uv run python scripts/seed_demo.py   # writes data/sample_players.json
```

### 2c. Verify

```bash
curl "http://127.0.0.1:8787/?query=Martin%20%C3%98degaard&k=5"
```

Expected: a JSON object with `player`, `match_type`, and `similar_players`
(top-5) with `cosine_similarity`, `league_multiplier`, `experience_multiplier`
and `final_score`.

---

## 3. Backend — Cloudflare Containers (beta, for the full ML stack)

Cloudflare Containers lets you run a Docker container (e.g. the FastAPI +
scikit-learn backend) on Cloudflare's network. A `Dockerfile` is provided.

```bash
docker build -t football-stats-api .
# push to a registry accessible to Cloudflare, then deploy via wrangler:
#   wrangler containers deploy --image <registry>/football-stats-api
```

The container runs `uvicorn app.api.main:app` on port 8000 and serves:

- `GET /health`
- `GET /similar?query=Martin Ødegaard&k=5`
- `GET /corpus`

---

## 4. Optional — Cloudflare KV / R2 for the corpus & cache

- Store the generated `data/sample_players.json` in **R2** or **KV** and load it
  at Worker cold-start (instead of bundling) so the corpus can be refreshed
  without redeploying code.
- For the SQLite 24-hour cache on the edge, Workers does not run SQLite directly;
  use **KV** (key → JSON, with `expirationTtl: 86400`) or **D1** (SQLite-at-the-edge)
  to reproduce the same 24h TTL semantics.

---

## 5. Local development (non-Cloudflare)

```bash
# install dependencies (uses uv; falls back to pip)
uv sync --extra dev || pip install -r requirements.txt

# generate the corpus
uv run python scripts/seed_demo.py

# run the API
uv run uvicorn app.api.main:app --reload

# run the Streamlit UI
uv run streamlit run ui/app.py

# run tests
uv run pytest
```
