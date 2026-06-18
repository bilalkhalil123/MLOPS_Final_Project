"""Persist and load pipeline metrics for EC2 /metrics sync."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

DATA_DIR = Path("data")
SNAPSHOT_FILE = DATA_DIR / "metrics_snapshot.json"

DEFAULT_SNAPSHOT: Dict[str, float] = {
    "records_processed_total": 0,
    "retrain_count_total": 0,
    "distribution_drift_detected": 0,
    "datalake_unavailable": 0,
    "feature_added_total": 0,
    "feature_removed_total": 0,
}


def load_snapshot() -> Dict[str, float]:
    if not SNAPSHOT_FILE.exists():
        return dict(DEFAULT_SNAPSHOT)
    raw = json.loads(SNAPSHOT_FILE.read_text(encoding="utf-8"))
    merged = dict(DEFAULT_SNAPSHOT)
    for key in DEFAULT_SNAPSHOT:
        if key in raw:
            merged[key] = float(raw[key])
    return merged


def save_snapshot(snapshot: Dict[str, float]) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    SNAPSHOT_FILE.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")


def bump(key: str, amount: float = 1.0) -> None:
    snapshot = load_snapshot()
    snapshot[key] = snapshot.get(key, 0) + amount
    save_snapshot(snapshot)


def set_gauge(key: str, value: float) -> None:
    snapshot = load_snapshot()
    snapshot[key] = value
    save_snapshot(snapshot)
