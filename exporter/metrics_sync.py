"""Apply metrics_snapshot.json values to Prometheus metrics before /metrics scrape."""

from __future__ import annotations

import json
from pathlib import Path

from exporter.metrics import (
    datalake_unavailable,
    distribution_drift_detected,
    feature_added,
    feature_removed,
    records_processed_total,
    retrain_count_total,
)
from exporter.metrics_snapshot import load_snapshot, save_snapshot

DATA_DIR = Path("data")
_last_applied: dict[str, float] = {}


def _sync_counter(counter, key: str, target: float) -> None:
    previous = _last_applied.get(key, 0.0)
    if target > previous:
        counter.inc(target - previous)
    _last_applied[key] = target


def _sync_gauge(gauge, key: str, target: float) -> None:
    gauge.set(target)
    _last_applied[key] = target


def sync_metrics_from_snapshot() -> None:
    """Load data/metrics_snapshot.json and mirror values into Prometheus registry."""
    snapshot = load_snapshot()

    _sync_counter(records_processed_total, "records_processed_total", snapshot["records_processed_total"])
    _sync_counter(retrain_count_total, "retrain_count_total", snapshot["retrain_count_total"])
    _sync_counter(datalake_unavailable, "datalake_unavailable", snapshot["datalake_unavailable"])
    _sync_counter(feature_added, "feature_added_total", snapshot["feature_added_total"])
    _sync_counter(feature_removed, "feature_removed_total", snapshot["feature_removed_total"])
    _sync_gauge(distribution_drift_detected, "distribution_drift_detected", snapshot["distribution_drift_detected"])


def rebuild_snapshot_from_data_files() -> None:
    """Rebuild metrics_snapshot.json from jsonl logs (run on C: before docker build)."""
    batches = DATA_DIR / "ingested_batches.jsonl"
    retrains = DATA_DIR / "retrain_events.jsonl"
    state_file = DATA_DIR / "ingestion_state.json"

    records = 0
    if batches.exists():
        for line in batches.read_text(encoding="utf-8").splitlines():
            if line.strip():
                batch = json.loads(line)
                records += int(batch.get("record_count", len(batch.get("records", []))))

    retrain_events = 0
    if retrains.exists():
        retrain_events = sum(1 for line in retrains.read_text(encoding="utf-8").splitlines() if line.strip())

    drift = 0.0
    if state_file.exists():
        state = json.loads(state_file.read_text(encoding="utf-8"))
        drift = float(state.get("drift_detected", 0))

    save_snapshot(
        {
            "records_processed_total": float(records),
            "retrain_count_total": float(retrain_events),
            "distribution_drift_detected": drift,
            "datalake_unavailable": load_snapshot().get("datalake_unavailable", 0),
            "feature_added_total": load_snapshot().get("feature_added_total", 0),
            "feature_removed_total": load_snapshot().get("feature_removed_total", 0),
        }
    )
