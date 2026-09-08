"""End-to-end pipeline tests using the bundled sample corpus."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.pipeline import Pipeline  # noqa: E402


def test_get_similar_resolves_and_returns_top5(tmp_path):
    pipeline = Pipeline(
        corpus_file=ROOT / "data" / "sample_players.json",
    )
    result = pipeline.get_similar("Martin Ødegaard", k=5)

    assert result["player"]["player_id"] == "odegaard-martin"
    assert result["match_type"] == "exact"
    assert len(result["similar_players"]) == 5

    # No self-references and sorted by final score descending.
    ids = [s["player"]["player_id"] for s in result["similar_players"]]
    assert "odegaard-martin" not in ids
    scores = [s["final_score"] for s in result["similar_players"]]
    assert scores == sorted(scores, reverse=True)

    # Multipliers are strictly applied per the spec.
    for s in result["similar_players"]:
        expected = (
            s["cosine_similarity"]
            * s["league_multiplier"]
            * s["experience_multiplier"]
        )
        assert abs(s["final_score"] - expected) < 1e-9


def test_get_similar_unknown_player_raises(tmp_path):
    pipeline = Pipeline(corpus_file=ROOT / "data" / "sample_players.json")
    try:
        pipeline.get_similar("Not A Real Player Name")
        assert False, "expected LookupError"
    except LookupError:
        pass
