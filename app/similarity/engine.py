"""Global similarity engine with weighted feature scaling.

Pipeline:
1. Collect the per-90 feature vector for every player in the corpus (no
   positional filtering - a single global model).
2. Z-score standardise each feature across the whole corpus (scikit-learn
   StandardScaler) so units/scale are comparable.
3. Compute a *weighted* cosine similarity using per-feature importance weights
   (see config.FEATURE_WEIGHTS).
4. Apply the strict league/experience multipliers to the final ranking score.

Design note on the multipliers: cosine similarity is scale-invariant, so a
scalar applied to a whole vector cancels out. The league (0.60/0.40) and
experience (0.55/0.45) multipliers are therefore applied as a *profile-quality
weight* at ranking time:

    final_score = weighted_cosine * league_multiplier * experience_multiplier

The raw (unweighted) cosine is always returned alongside so the caller can
inspect the pure statistical similarity separately.
"""
from __future__ import annotations

import math
from typing import Optional, Sequence

import numpy as np
from sklearn.preprocessing import StandardScaler

from app import config
from app.models import Player, SimilarityResult


class SimilarityEngine:
    """Weighted cosine-similarity ranking over a corpus of players."""

    def __init__(
        self,
        features: Optional[Sequence[str]] = None,
        feature_weights: Optional[dict[str, float]] = None,
    ) -> None:
        self.features = list(features) if features else list(config.FEATURES)
        self.feature_weights = feature_weights if feature_weights else dict(config.FEATURE_WEIGHTS)
        self._weight_vector = np.array(
            [self.feature_weights.get(f, 1.0) for f in self.features], dtype=float
        )

    # ------------------------------------------------------------- weighting
    def league_multiplier(self, player: Player) -> float:
        return config.LEAGUE_WEIGHT_TOP5 if player.league_tier == "top5" else config.LEAGUE_WEIGHT_ROW

    def experience_multiplier(self, player: Player) -> float:
        return (
            config.EXPERIENCE_WEIGHT_SENIOR
            if player.experience_years >= config.SENIOR_YEARS_THRESHOLD
            else config.EXPERIENCE_WEIGHT_JUNIOR
        )

    def profile_weight(self, player: Player) -> float:
        return self.league_multiplier(player) * self.experience_multiplier(player)

    # ------------------------------------------------------------ vectorisation
    def _feature_vector(self, player: Player) -> np.ndarray:
        return np.array(
            [float(player.features.get(f, 0.0)) for f in self.features], dtype=float
        )

    def _matrix(self, players: Sequence[Player]) -> np.ndarray:
        return np.vstack([self._feature_vector(p) for p in players])

    def standardize(self, matrix: np.ndarray) -> np.ndarray:
        """Z-score standardise the feature matrix across players."""
        if matrix.shape[0] < 2:
            return matrix  # StandardScaler is undefined for a single sample.
        return StandardScaler().fit_transform(matrix)

    # ------------------------------------------------------------ similarity
    def weighted_cosine(
        self, a: np.ndarray, b: np.ndarray, weights: Optional[np.ndarray] = None
    ) -> float:
        """Weighted cosine similarity between two feature vectors.

        When `weights` is omitted a uniform weight vector is used (standard
        cosine). The feature-importance weighting is applied explicitly by
        `similarity_matrix`, which passes `self._weight_vector`.
        """
        a = np.asarray(a, dtype=float)
        b = np.asarray(b, dtype=float)
        if weights is None:
            w = np.ones_like(a, dtype=float)
        else:
            w = np.asarray(weights, dtype=float)
        denom = math.sqrt(float(np.dot(a * a, w)) * float(np.dot(b * b, w)))
        if denom == 0.0:
            return 0.0
        return float(np.dot(a * w, b)) / denom

    def similarity_matrix(
        self, query: np.ndarray, corpus_matrix: np.ndarray
    ) -> np.ndarray:
        """Weighted cosine of `query` against every row of `corpus_matrix`."""
        w = self._weight_vector
        query = np.asarray(query, dtype=float)
        corpus = np.asarray(corpus_matrix, dtype=float)
        numerator = corpus @ (w * query)
        corpus_denom = np.sqrt((corpus * corpus) @ w)
        query_denom = math.sqrt(float(np.dot(query * query, w)))
        denom = corpus_denom * query_denom
        return np.divide(numerator, denom, out=np.zeros_like(numerator), where=denom != 0)

    # ------------------------------------------------------------ ranking
    def top_similar(
        self,
        query: Player,
        corpus: Sequence[Player],
        k: Optional[int] = None,
        exclude_query: bool = True,
    ) -> list[SimilarityResult]:
        """Return the top-k most similar players by final weighted score.

        The query is standardised jointly with the corpus so it lives on the
        same scale as the rest of the population.
        """
        k = k if k is not None else config.TOP_K
        if not corpus:
            return []

        all_players = list(corpus)
        if exclude_query:
            all_players = [p for p in all_players if p.player_id != query.player_id]
        if not all_players:
            return []

        query_vec = self._feature_vector(query)
        combined = np.vstack([query_vec, self._matrix(all_players)])
        standardised = self.standardize(combined)
        std_query = standardised[0]
        std_corpus = standardised[1:]

        sims = self.similarity_matrix(std_query, std_corpus)

        results: list[SimilarityResult] = []
        for i, player in enumerate(all_players):
            cosine = float(sims[i])
            league = self.league_multiplier(player)
            experience = self.experience_multiplier(player)
            results.append(
                SimilarityResult(
                    rank=0,
                    player=player,
                    cosine_similarity=cosine,
                    league_multiplier=league,
                    experience_multiplier=experience,
                    final_score=cosine * league * experience,
                )
            )

        results.sort(key=lambda r: r.final_score, reverse=True)
        for rank, result in enumerate(results[:k], start=1):
            result.rank = rank
        return results[:k]
