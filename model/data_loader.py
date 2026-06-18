"""Load training data from ingested batch files."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pandas as pd

INGESTED_BATCHES = Path("data/ingested_batches.jsonl")
TARGET_COLUMN = "label"


def load_ingested_records(path: Path = INGESTED_BATCHES) -> pd.DataFrame:
    """Load and flatten all ingested records into a single DataFrame."""
    if not path.exists():
        return pd.DataFrame()

    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            batch = json.loads(line)
            batch_records = batch.get("records", [])
            if isinstance(batch_records, list):
                rows.extend(batch_records)

    if not rows:
        return pd.DataFrame()

    return pd.DataFrame(rows)


def split_features_target(frame: pd.DataFrame) -> Tuple[pd.DataFrame, pd.Series, List[str]]:
    if frame.empty:
        return pd.DataFrame(), pd.Series(dtype=int), []

    if TARGET_COLUMN not in frame.columns:
        raise ValueError(f"Target column '{TARGET_COLUMN}' not found in ingested data.")

    feature_columns = sorted(
        [col for col in frame.columns if col != TARGET_COLUMN],
        key=lambda name: (not name.startswith("f"), int(name[1:]) if name.startswith("f") and name[1:].isdigit() else name),
    )
    features = frame[feature_columns].apply(pd.to_numeric, errors="coerce").fillna(0.0)
    target = frame[TARGET_COLUMN]
    return features, target, feature_columns
