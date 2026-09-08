"""FastAPI backend for the Football Stats App.

Endpoints:
    GET  /health                     -> liveness probe
    GET  /players?query=...          -> resolve a player
    GET  /similar?query=...&k=5      -> top-k similar players (weighted)
    POST /similar                    -> same as above with a JSON body
    GET  /corpus                     -> list the corpus (id + name + club)

Run locally:
    uvicorn app.api.main:app --reload
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

from app.pipeline import Pipeline

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("football.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.pipeline = Pipeline()
    logger.info("pipeline initialised with %d players", len(app.state.pipeline.corpus))
    yield
    app.state.pipeline.cache.close()


app = FastAPI(
    title="Football Stats App API",
    version="1.0.0",
    lifespan=lifespan,
)


class SimilarRequest(BaseModel):
    query: str
    k: Optional[int] = None
    enrich_market_value: bool = False


def _pipeline(app: FastAPI) -> Pipeline:
    return app.state.pipeline


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "corpus_size": len(_pipeline(app).corpus)}


@app.get("/players")
def resolve_player(query: str = Query(..., min_length=2)) -> dict:
    resolved = _pipeline(app).resolve_confidence(query)
    if resolved is None:
        raise HTTPException(status_code=404, detail=f"Player not found: {query}")
    player = resolved["player"]
    return {
        "query": query,
        "match_type": resolved["match_type"],
        "confidence": resolved["confidence"],
        "player": player.to_dict(),
    }


@app.get("/similar")
def get_similar(
    query: str = Query(..., min_length=2),
    k: Optional[int] = Query(None, ge=1, le=50),
    enrich_market_value: bool = False,
) -> dict:
    try:
        return _pipeline(app).get_similar(query, k=k, enrich_market_value=enrich_market_value)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/similar")
def post_similar(body: SimilarRequest) -> dict:
    try:
        return _pipeline(app).get_similar(
            body.query, k=body.k, enrich_market_value=body.enrich_market_value
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/corpus")
def corpus() -> dict:
    players = _pipeline(app).corpus
    return {
        "count": len(players),
        "players": [
            {
                "player_id": p.player_id,
                "name": p.name,
                "club": p.club,
                "league": p.league,
                "position": p.position,
            }
            for p in players
        ],
    }
