"""Utility helpers for simple feature distribution drift detection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Tuple


@dataclass
class DriftResult:
    """Stores drift decision and per-feature details."""

    drift_detected: bool
    score: float
    feature_scores: Dict[str, float]
    compared_features: List[str]


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def compute_numeric_stats(records: Iterable[Dict[str, object]]) -> Dict[str, Tuple[float, float]]:
    """
    Compute mean and std-dev for each numeric feature.

    Returns:
        Dict[feature_name, (mean, std_dev)]
    """
    values_by_feature: Dict[str, List[float]] = {}
    for row in records:
        for key, value in row.items():
            if _is_number(value):
                values_by_feature.setdefault(key, []).append(float(value))

    stats: Dict[str, Tuple[float, float]] = {}
    for feature, values in values_by_feature.items():
        if not values:
            continue
        mean = sum(values) / len(values)
        variance = sum((item - mean) ** 2 for item in values) / len(values)
        stats[feature] = (mean, variance**0.5)
    return stats


def detect_drift(
    baseline_stats: Dict[str, Tuple[float, float]],
    current_stats: Dict[str, Tuple[float, float]],
    threshold: float = 0.25,
) -> DriftResult:
    """
    Compare baseline stats with current stats and return a drift decision.

    Drift score is the average normalized change over features available in both
    baseline and current stats:
        mean_delta + std_delta
    where each delta is normalized by max(abs(baseline_value), 1.0).
    """
    common_features = sorted(set(baseline_stats) & set(current_stats))
    if not common_features:
        return DriftResult(False, 0.0, {}, [])

    per_feature_scores: Dict[str, float] = {}
    for feature in common_features:
        base_mean, base_std = baseline_stats[feature]
        cur_mean, cur_std = current_stats[feature]

        mean_delta = abs(cur_mean - base_mean) / max(abs(base_mean), 1.0)
        std_delta = abs(cur_std - base_std) / max(abs(base_std), 1.0)
        per_feature_scores[feature] = mean_delta + std_delta

    overall_score = sum(per_feature_scores.values()) / len(per_feature_scores)
    return DriftResult(
        drift_detected=overall_score >= threshold,
        score=overall_score,
        feature_scores=per_feature_scores,
        compared_features=common_features,
    )
