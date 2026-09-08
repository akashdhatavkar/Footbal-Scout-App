"""Corpus data for the Cloudflare Workers (edge) deployment.

Kept as a thin re-export of the single source of truth in scripts/sample_data.py
so the corpus never drifts between the full Python backend and the edge worker.
The deployment guide explains how to bundle this module (or inline the data via
scripts/export_worker_data.py) when deploying to Workers.
"""
from __future__ import annotations

from scripts.sample_data import SAMPLE_PLAYERS as CORPUS
