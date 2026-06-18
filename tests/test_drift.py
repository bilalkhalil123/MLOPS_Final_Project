"""Tests for distribution drift detection."""

from ingestion.drift_detector import compute_numeric_stats, detect_drift


def _make_records(feature: str, value: float, count: int = 50) -> list:
    return [{feature: value} for _ in range(count)]


def test_detect_drift_on_shifted_distribution() -> None:
    baseline_records = _make_records("feature_a", 10.0) + _make_records("feature_b", 5.0)
    shifted_records = _make_records("feature_a", 100.0) + _make_records("feature_b", 50.0)

    baseline_stats = compute_numeric_stats(baseline_records)
    shifted_stats = compute_numeric_stats(shifted_records)

    result = detect_drift(baseline_stats, shifted_stats, threshold=0.25)

    assert result.drift_detected is True
    assert result.score >= 0.25
    assert "feature_a" in result.compared_features


def test_no_drift_when_distribution_is_stable() -> None:
    baseline_records = _make_records("feature_a", 10.0) + _make_records("feature_b", 5.0)
    stable_records = _make_records("feature_a", 10.2) + _make_records("feature_b", 5.1)

    baseline_stats = compute_numeric_stats(baseline_records)
    stable_stats = compute_numeric_stats(stable_records)

    result = detect_drift(baseline_stats, stable_stats, threshold=0.25)

    assert result.drift_detected is False
