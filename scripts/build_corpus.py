"""Build a live player corpus by scraping FBref.

Usage:
    python scripts/build_corpus.py "Martin Ødegaard" "Erling Haaland" ...

Each player is fetched via the FBref scraper (with the 24-hour SQLite cache and
the randomised 2-5s politeness pause), and the resulting profiles are appended
to data/sample_players.json (or a custom output file).

For a real global corpus, point this at a large list of players/teams. This
script is intentionally minimal: it demonstrates the ingestion -> cache ->
persist path used by the rest of the app.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.pipeline import Pipeline  # noqa: E402
from app.models import Player  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape players into the corpus.")
    parser.add_argument("names", nargs="+", help="Player names to scrape.")
    parser.add_argument(
        "--out",
        default=str(ROOT / "data" / "sample_players.json"),
        help="Output JSON path.",
    )
    args = parser.parse_args()

    pipeline = Pipeline()
    existing = {p.player_id for p in pipeline.corpus}

    scraped = []
    for name in args.names:
        try:
            profile = pipeline.ingest_live(name, k=0)["player"]
            player = Player.from_dict(profile)
            scraped.append(player)
            print(f"OK   {name} -> {player.name} ({player.club}, {player.league})")
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL {name}: {exc}")

    merged = [p for p in pipeline.corpus if p.player_id not in {s.player_id for s in scraped}]
    merged.extend(scraped)
    out = Path(args.out)
    out.write_text(
        json.dumps([p.to_dict() for p in merged], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"Wrote {len(merged)} players -> {out}")


if __name__ == "__main__":
    main()
