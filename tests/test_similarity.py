"""Tests for the weighted similarity engine."""
from __future__ import annotations

import math

import numpy as np

from app.similarity.engine import SimilarityEngine
from tests.helpers import make_player


def test_league_multiplier():
    engine = SimilarityEngine()
    top5 = make_player("a", "Top Five", tier="top5")
    row = make_player("b", "Rest World", tier="row")
    assert engine.league_multiplier(top5) == 0.60
    assert engine.league_multiplier(row) == 0.40


def test_experience_multiplier_threshold():
    engine = SimilarityEngine()
    senior = make_player("a", "Senior Player", exp=5)
    junior = make_player("b", "Junior Player", exp=4)
    assert engine.experience_multiplier(senior) == 0.55
    assert engine.experience_multiplier(junior) == 0.45


def test_weighted_cosine_identical_vectors():
    engine = SimilarityEngine()
    a = np.array([1.0, 2.0, 3.0])
    assert math.isclose(engine.weighted_cosine(a, a), 1.0, rel_tol=1e-9)


def test_weighted_cosine_orthogonal_vectors():
    engine = SimilarityEngine()
    a = np.array([1.0, 0.0])
    b = np.array([0.0, 1.0])
    assert engine.weighted_cosine(a, b) == 0.0


def test_top_similar_returns_k_and_excludes_query():
    engine = SimilarityEngine()
    query = make_player("q", "Query Player", goals_p90=0.9, assists_p90=0.1)
    corpus = [
        query,
        make_player("a", "Alpha", goals_p90=0.85, assists_p90=0.15),
        make_player("b", "Beta", goals_p90=0.1, assists_p90=0.9),
        make_player("c", "Gamma", goals_p90=0.8, assists_p90=0.2),
    ]
    results = engine.top_similar(query, corpus, k=2)
    assert len(results) == 2
    assert all(r.player.player_id != "q" for r in results)
    # Sorted by final score descending.
    assert results[0].final_score >= results[1].final_score


def test_profile_weight_combines_multipliers():
    engine = SimilarityEngine()
    top5_senior = make_player("a", "A", tier="top5", exp=8)
    row_junior = make_player("b", "B", tier="row", exp=2)

    assert math.isclose(engine.profile_weight(top5_senior), 0.60 * 0.55, rel_tol=1e-9)
    assert math.isclose(engine.profile_weight(row_junior), 0.40 * 0.45, rel_tol=1e-9)
    assert engine.profile_weight(top5_senior) > engine.profile_weight(row_junior)


def test_top_similar_final_score_formula():
    engine = SimilarityEngine()
    query = make_player("q", "Query Player", goals_p90=0.4, assists_p90=0.5, touches_p90=70.0)
    corpus = [
        make_player("a", "Alpha", tier="top5", exp=8, goals_p90=0.35, assists_p90=0.45, touches_p90=68.0),
        make_player("b", "Beta", tier="row", exp=2, goals_p90=0.38, assists_p90=0.48, touches_p90=69.0),
        make_player("c", "Gamma", tier="top5", exp=10, goals_p90=0.42, assists_p90=0.52, touches_p90=72.0),
    ]
    results = engine.top_similar(query, corpus, k=3)
    for r in results:
        expected = r.cosine_similarity * r.league_multiplier * r.experience_multiplier
        assert math.isclose(r.final_score, expected, rel_tol=1e-9)
