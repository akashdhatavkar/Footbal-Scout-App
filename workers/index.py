from __future__ import annotations

import difflib
import json
import math
import unicodedata
from urllib.parse import parse_qs, urlparse

from js import Response, WorkerEntrypoint

# Embedded seed corpus directly inside index.py to avoid cross-module import failures
CORPUS = [
    {
        "player_id": "p1",
        "first_name": "Martin",
        "last_name": "Ødegaard",
        "league_tier": "top5",
        "experience_years": 7,
        "features": {
            "goals_p90": 0.28, "assists_p90": 0.25, "shots_p90": 2.30,
            "shots_on_target_p90": 0.85, "npxg_p90": 0.26, "xa_p90": 0.28,
            "key_passes_p90": 2.50, "pass_completion_pct": 84.5,
            "progressive_passes_p90": 8.10, "progressive_carries_p90": 3.20,
            "successful_take_ons_p90": 1.10, "tackles_p90": 1.10,
            "interceptions_p90": 0.40, "blocks_p90": 0.60,
            "aerial_duels_won_p90": 0.50, "touches_p90": 68.0,
        },
    },
    {
        "player_id": "p2",
        "first_name": "Bruno",
        "last_name": "Fernandes",
        "league_tier": "top5",
        "experience_years": 8,
        "features": {
            "goals_p90": 0.25, "assists_p90": 0.22, "shots_p90": 2.60,
            "shots_on_target_p90": 0.90, "npxg_p90": 0.24, "xa_p90": 0.32,
            "key_passes_p90": 3.10, "pass_completion_pct": 78.0,
            "progressive_passes_p90": 7.80, "progressive_carries_p90": 2.50,
            "successful_take_ons_p90": 0.80, "tackles_p90": 1.80,
            "interceptions_p90": 0.70, "blocks_p90": 0.80,
            "aerial_duels_won_p90": 0.60, "touches_p90": 72.0,
        },
    },
    {
        "player_id": "p3",
        "first_name": "James",
        "last_name": "Maddison",
        "league_tier": "top5",
        "experience_years": 6,
        "features": {
            "goals_p90": 0.22, "assists_p90": 0.28, "shots_p90": 2.40,
            "shots_on_target_p90": 0.95, "npxg_p90": 0.20, "xa_p90": 0.30,
            "key_passes_p90": 2.80, "pass_completion_pct": 80.2,
            "progressive_passes_p90": 6.90, "progressive_carries_p90": 3.10,
            "successful_take_ons_p90": 1.40, "tackles_p90": 1.20,
            "interceptions_p90": 0.50, "blocks_p90": 0.40,
            "aerial_duels_won_p90": 0.30, "touches_p90": 62.0,
        },
    },
]

FEATURES = [
    "goals_p90", "assists_p90", "shots_p90", "shots_on_target_p90",
    "npxg_p90", "xa_p90", "key_passes_p90", "pass_completion_pct",
    "progressive_passes_p90", "progressive_carries_p90", "successful_take_ons_p90",
    "tackles_p90", "interceptions_p90", "blocks_p90", "aerial_duels_won_p90", "touches_p90"
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


def normalize(text: str) -> str:
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", str(text))
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
        p_first = normalize(p.get("first_name", ""))
        p_last = normalize(p.get("last_name", ""))
        if p_first == q_first and p_last == q_last:
            return {"player": p, "match_type": "exact", "confidence": 100.0}

    best, best_score = None, 0.0
    for p in CORPUS:
        full = normalize(f"{p.get('first_name', '')} {p.get('last_name', '')}".strip())
        score = max(ratio(query, full), ratio(q_last, normalize(p.get("last_name", ""))))
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
    others = [p for p in CORPUS if p.get("player_id") != player.get("player_id")]

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
        try:
            url_str = str(getattr(request, "url", ""))
            qs = parse_qs(urlparse(url_str).query)
            query = (qs.get("query") or [""])[0]

            try:
                k = int((qs.get("k") or ["5"])[0])
            except ValueError:
                k = 5

            headers = {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            }

            if not query:
                body = json.dumps({
                    "status": "ok",
                    "message": "Football Stats Worker API online. Pass ?query=PlayerName to search."
                })
                return Response(body, status=200, headers=headers)

            payload = similar(query, k=k)
            status = 404 if "error" in payload else 200
            return Response(json.dumps(payload, ensure_ascii=False), status=status, headers=headers)

        except Exception:
            import traceback
            err_headers = {
                "Content-Type": "text/plain",
                "Access-Control-Allow-Origin": "*",
            }
            return Response(
                f"Worker Error:\n{traceback.format_exc()}",
                status=500,
                headers=err_headers,
            )
