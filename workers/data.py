"""Corpus data for the Cloudflare Workers (edge) deployment.

Kept as a thin re-export of the single source of truth in scripts/sample_data.py
so the corpus never drifts between the full Python backend and the edge worker.
The deployment guide explains how to bundle this module (or inline the data via
scripts/export_worker_data.py) when deploying to Workers.
"""
from __future__ import annotations

# Inline static seed corpus for Cloudflare Workers edge deployment
CORPUS = [
    {
        "name": "Martin Ødegaard",
        "position": "MF",
        "league": "Premier League",
        "market_value_eur": 110000000,
        "metrics": {"goals_per90": 0.28, "assists_per90": 0.25}
    }
]
