"""Cloudflare Workers (Python) entry point.

A dependency-free reimplementation of the similarity engine that runs on the
edge (no numpy / scikit-learn / pandas). It loads the pre-seeded corpus and
answers:

    GET /?query=Martin%20Ødegaard&k=5

with a JSON payload identical in shape to the FastAPI /similar endpoint.

The full Python backend (FastAPI + scikit-learn) remains the canonical engine;
this worker exists so the read path can be served at the edge with zero cold
start. The feature list and weights are intentionally inlined here (rather than
importing app.config) so the worker has no third-party dependencies.
"""
from __future__ import annotations

import difflib
import json
import math
import unicodedata
from urllib.parse import parse_qs, urlparse

try:  # Workers Python runtime
    from workers import Response, WorkerEntrypoint
except ImportError:  # pragma: no cover - local testing without the runtime
    class WorkerEntrypoint:  # type: ignore[no-redef]
        pass

    class Response:  # type: ignore[no-redef]
        def __init__(self, body="", status=200, headers=None):
            self.body = body
            self.status = status
            self.headers = headers or {}


from workers.data import CORPUS  # noqa: E402

FEATURES = [
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

FEATURE_WEIGHTS = {
    "goals_p90": 1.30, "assists_p90": 1.20, "shots_p90": 1.00,
    "shots_on_target_p90": 1.00, "npxg_p90": 1.20, "xa_p90": 1.10,
    "key_passes_p90": 1.10, "pass_completion_pct": 0.90,
    "progressive_passes_p90": 1.00, "progressive_carries_p90": 1.00,
    "successful_take_ons_p90": 0.90, "tackles_p90": 0.70,
    "interceptions_p90": 0.60, "blocks_p90": 0.50,
    "aerial_duels_won_p90": 0.50, "touches_p90": 0.80,
}

FUZZY_THRESHOLD = 85


# ---------------------------------------------------------------- utilities
def normalize(text: str) -> str:
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return " ".join(text.lower().split())


def ratio(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, normalize(a), normalize(b)).ratio() * 100.0


def feature_vector(player: dict) -> list[float]:
    feats = player.get("features", {})
    return [float(feats.get(f, 0.0)) for f in FEATURES]


def league_multiplier(player: dict) -> float:
    return 0.60 if player.get("league_tier") == "top5" else 0.40


def experience_multiplier(player: dict) -> float:
    return 0.55 if player.get("experience_years", 0) >= 5 else 0.45


def weighted_cosine(a: list[float], b: list[float], w: list[float]) -> float:
    num = sum(wi * ai * bi for wi, ai, bi in zip(w, a, b))
    den = math.sqrt(sum(wi * ai * ai for wi, ai in zip(w, a)) *
                    sum(wi * bi * bi for wi, bi in zip(w, b)))
    return num / den if den else 0.0


def standardize(rows: list[list[float]]) -> list[list[float]]:
    """Z-score standardise each feature column across the population."""
    n = len(rows)
    m = len(FEATURES)
    if n < 2:
        return rows
    means = [sum(r[j] for r in rows) / n for j in range(m)]
    stds = []
    for j in range(m):
        var = sum((r[j] - means[j]) ** 2 for r in rows) / n
        stds.append(math.sqrt(var) if var > 0 else 1.0)
    return [[(r[j] - means[j]) / stds[j] for j in range(m)] for r in rows]


def resolve(query: str) -> dict | None:
    parts = query.strip().split()
    q_first = normalize(parts[0]) if parts else ""
    q_last = normalize(" ".join(parts[1:]) if len(parts) > 1 else (parts[0] if parts else ""))

    for p in CORPUS:
        if normalize(p["first_name"]) == q_first and normalize(p["last_name"]) == q_last:
            return {"player": p, "match_type": "exact", "confidence": 100.0}

    best, best_score = None, 0.0
    for p in CORPUS:
        full = normalize(f"{p['first_name']} {p['last_name']}".strip())
        score = max(ratio(query, full), ratio(q_last, normalize(p["last_name"])))
        if score >= FUZZY_THRESHOLD and score > best_score:
            best, best_score = p, score
    if best is not None:
        return {"player": best, "match_type": "fuzzy", "confidence": best_score}
    return None


def similar(query: str, k: int = 5) -> dict:
    resolved = resolve(query)
    if resolved is None:
        return {"error": f"Player not found: {query}"}

    player = resolved["player"]
    others = [p for p in CORPUS if p["player_id"] != player["player_id"]]

    rows = standardize([feature_vector(player)] + [feature_vector(p) for p in others])
    q_vec = rows[0]
    corpus_vecs = rows[1:]
    weights = [FEATURE_WEIGHTS[f] for f in FEATURES]

    results = []
    for vec, p in zip(corpus_vecs, others):
        cosine = weighted_cosine(q_vec, vec, weights)
        league = league_multiplier(p)
        exp = experience_multiplier(p)
        results.append({
            "rank": 0,
            "player": p,
            "cosine_similarity": cosine,
            "league_multiplier": league,
            "experience_multiplier": exp,
            "final_score": cosine * league * exp,
        })

    results.sort(key=lambda r: r["final_score"], reverse=True)
    for i, r in enumerate(results[:k], start=1):
        r["rank"] = i

    return {
        "query": query,
        "match_type": resolved["match_type"],
        "confidence": resolved["confidence"],
        "player": player,
        "similar_players": results[:k],
    }


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        qs = parse_qs(urlparse(str(getattr(request, "url", ""))).query)
        query = (qs.get("query") or [""])[0]
        try:
            k = int((qs.get("k") or ["5"])[0])
        except ValueError:
            k = 5

        if not query:
            body = json.dumps({"error": "missing 'query' parameter"})
            return Response(body, status=400, headers={"Content-Type": "application/json"})

        payload = similar(query, k=k)
        headers = {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"}
        status = 404 if "error" in payload else 200
        return Response(json.dumps(payload, ensure_ascii=False), status=status, headers=headers)
