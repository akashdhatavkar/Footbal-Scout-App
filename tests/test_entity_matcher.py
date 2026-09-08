"""Tests for entity resolution (exact -> fuzzy)."""
from __future__ import annotations

from app.matching.entity_matcher import EntityMatcher
from tests.helpers import make_player


def _players():
    return [
        make_player("odegaard", "Martin Ødegaard"),
        make_player("pedri", "Pedri", club="Barcelona", league="La Liga"),
        make_player("mbappe", "Kylian Mbappé", position="FW", club="Real Madrid", league="La Liga"),
        make_player("vinicius", "Vinícius Júnior", position="FW", club="Real Madrid", league="La Liga"),
    ]


def test_normalize_strips_accents():
    assert EntityMatcher.normalize("Ødegaard") == "odegaard"
    assert EntityMatcher.normalize("Vinícius Júnior") == "vinicius junior"
    assert EntityMatcher.normalize("  Multiple   Spaces ") == "multiple spaces"


def test_exact_match_is_case_and_accent_insensitive():
    matcher = EntityMatcher()
    players = _players()
    # Accented query resolves exactly.
    assert matcher.match("martin odegaard", players).player_id == "odegaard"
    assert matcher.match("MARTIN ØDEGAARD", players).player_id == "odegaard"


def test_fuzzy_match_within_threshold():
    matcher = EntityMatcher(threshold=85)
    players = _players()
    # "Odegaard" (no Ø) should fuzzy match "Ødegaard" at high ratio.
    assert matcher.match("Martin Odegaard", players).player_id == "odegaard"


def test_single_name_player_matches():
    matcher = EntityMatcher()
    players = _players()
    assert matcher.match("Pedri", players).player_id == "pedri"


def test_no_match_below_threshold():
    matcher = EntityMatcher(threshold=85)
    players = _players()
    assert matcher.match("Completely Unknown Name", players) is None


def test_match_with_confidence_returns_type():
    matcher = EntityMatcher()
    players = _players()
    exact = matcher.match_with_confidence("Martin Ødegaard", players)
    assert exact["match_type"] == "exact"
    assert exact["confidence"] == 100.0
