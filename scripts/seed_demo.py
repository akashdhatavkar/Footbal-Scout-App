"""Generate the demo corpus JSON from the bundled sample data.

Usage:
    python scripts/seed_demo.py

This writes data/sample_players.json, which is what the offline/demo path of the
pipeline, FastAPI app and Streamlit UI load by default.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.sample_data import SAMPLE_PLAYERS  # noqa: E402


def main() -> None:
    out = ROOT / "data" / "sample_players.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(SAMPLE_PLAYERS, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"Wrote {len(SAMPLE_PLAYERS)} players -> {out}")


if __name__ == "__main__":
    main()
