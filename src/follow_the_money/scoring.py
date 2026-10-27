"""Numpy-only distribution checks and bounded inference fallback."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

import numpy as np

from follow_the_money.contracts import FtmError


@dataclass
class DistributionGuard:
    mean: np.ndarray
    scale: np.ndarray
    threshold: float
    chain: str
    feature_names: tuple[str, ...]

    @classmethod
    def fit(
        cls, values: np.ndarray, *, chain: str, feature_names: Sequence[str]
    ) -> DistributionGuard:
        if len(values) < 2 or not np.isfinite(values).all():
            raise FtmError("invalid_training", "OOD fit requires finite training rows")
        mean = values.mean(axis=0)
        scale = np.maximum(values.std(axis=0), 1e-6)
        distances = np.sqrt(np.mean(((values - mean) / scale) ** 2, axis=1))
        return cls(
            mean,
            scale,
            float(max(1.0, np.quantile(distances, 0.99) * 1.25)),
            chain,
            tuple(feature_names),
        )

    def inspect(
        self, values: Sequence[float], *, chain: str, feature_names: Sequence[str]
    ) -> dict[str, Any]:
        x = np.asarray(values, dtype=float)
        mismatch = (
            chain != self.chain
            or tuple(feature_names) != self.feature_names
            or x.shape != self.mean.shape
            or not np.isfinite(x).all()
        )
        distance = (
            None
            if mismatch
            else float(np.sqrt(np.mean(((x - self.mean) / self.scale) ** 2)))
        )
        return {
            "ood": mismatch or distance > self.threshold,
            "distance": distance,
            "threshold": self.threshold,
            "reason": "schema_or_chain_mismatch" if mismatch else "training_distance",
        }


def score_address(
    values: Sequence[float],
    *,
    guard: DistributionGuard | None,
    predict: Any = None,
    chain: str,
    feature_names: Sequence[str],
    heuristic: float,
) -> dict[str, Any]:
    """Fail closed to a bounded heuristic when no suitable trained model exists."""
    if not np.isfinite(heuristic) or not 0 <= heuristic <= 1:
        raise ValueError("heuristic must be finite in [0, 1]")
    check = (
        {"ood": True, "reason": "model_unavailable"}
        if guard is None
        else guard.inspect(values, chain=chain, feature_names=feature_names)
    )
    if check["ood"] or predict is None:
        return {
            **check,
            "score": heuristic,
            "method": "heuristic_fallback",
            "calibrated": False,
        }
    try:
        score = float(predict(np.asarray(values, dtype=float).reshape(1, -1))[0])
    except (ValueError, TypeError, RuntimeError, IndexError, KeyError):
        return {
            "ood": True,
            "reason": "model_error",
            "score": heuristic,
            "method": "heuristic_fallback",
            "calibrated": False,
        }
    if not np.isfinite(score) or not 0 <= score <= 1:
        return {
            "ood": True,
            "reason": "invalid_model_output",
            "score": heuristic,
            "method": "heuristic_fallback",
            "calibrated": False,
        }
    return {**check, "score": score, "method": "priority_model", "calibrated": False}
