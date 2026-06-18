"""Normalize API payloads into schema + records for ingestion pipeline."""

from __future__ import annotations

from typing import Any, Dict, List, Sequence


def _feature_names(length: int) -> List[str]:
    return [f"f{i}" for i in range(length)]


def _record_to_row(record: Dict[str, Any]) -> Dict[str, Any]:
    if "features" in record and isinstance(record["features"], list):
        row = {f"f{i}": value for i, value in enumerate(record["features"])}
        if "label" in record:
            row["label"] = record["label"]
        return row

    return dict(record)


def normalize_api_payload(raw: Any) -> Dict[str, Any]:
    """
    Support both project-spec payloads and the live API list format.

    Spec format: {"schema": [...], "records": [...]}
    Live format: [{"features": [...], "label": 0}, ...]
    """
    if isinstance(raw, dict) and "records" in raw:
        schema = list(raw.get("schema") or [])
        records = raw.get("records") or []
        if not schema and records:
            schema = _infer_feature_schema(records)
        return {"schema": schema, "records": records}

    if isinstance(raw, list):
        rows = [_record_to_row(item) for item in raw if isinstance(item, dict)]
        schema = _infer_feature_schema(rows)
        return {"schema": schema, "records": rows}

    raise ValueError("Unsupported API payload format.")


def _infer_feature_schema(records: Sequence[Dict[str, Any]]) -> List[str]:
    max_features = 0
    for row in records:
        feature_keys = [key for key in row if key.startswith("f") and key[1:].isdigit()]
        if feature_keys:
            max_features = max(max_features, len(feature_keys))
        elif "features" in row and isinstance(row["features"], list):
            max_features = max(max_features, len(row["features"]))

    if max_features == 0 and records:
        max_features = len([key for key in records[0] if key != "label"])

    return _feature_names(max_features)
