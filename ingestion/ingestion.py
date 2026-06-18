"""Data ingestion service for schema/drift monitoring and event triggering."""

from __future__ import annotations

from common.path_setup import ensure_project_root

ensure_project_root()

import argparse
import json
import logging
import os
import time

from dotenv import load_dotenv

load_dotenv()
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional, Sequence, Set, Tuple

import requests

from exporter.metrics import (
    datalake_unavailable,
    distribution_drift_detected,
    feature_added,
    feature_removed,
    records_processed_total,
)
from exporter.metrics_snapshot import bump, set_gauge
from ingestion.drift_detector import compute_numeric_stats, detect_drift
from ingestion.normalize import normalize_api_payload

DATA_DIR = Path("data")
LOG_DIR = Path("logs")
BATCH_FILE = DATA_DIR / "ingested_batches.jsonl"
RETRAIN_EVENTS_FILE = DATA_DIR / "retrain_events.jsonl"
INGESTION_STATE_FILE = DATA_DIR / "ingestion_state.json"
DEFAULT_API_URL = os.getenv("DATA_API_URL", "http://149.40.228.124:6500/records")
DEFAULT_INTERVAL_SECONDS = int(os.getenv("INGEST_INTERVAL_SECONDS", "60"))
DEFAULT_DRIFT_THRESHOLD = float(os.getenv("DRIFT_THRESHOLD", "0.25"))
DEFAULT_RETRAIN_MIN_NEW_RECORDS = int(os.getenv("RETRAIN_MIN_NEW_RECORDS", "200"))
DEFAULT_TIMEOUT_SECONDS = int(os.getenv("INGEST_HTTP_TIMEOUT_SECONDS", "20"))
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")


def setup_logging() -> None:
    """Configure file and console logging for ingestion process."""
    LOG_DIR.mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(LOG_DIR / "ingestion.log", encoding="utf-8"),
        ],
    )


def send_slack_alert(message: str) -> None:
    """Send alert message to Slack if webhook is configured."""
    if not SLACK_WEBHOOK_URL:
        logging.info("Slack webhook not configured. Alert skipped: %s", message)
        return

    try:
        response = requests.post(
            SLACK_WEBHOOK_URL,
            json={"text": message},
            timeout=10,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        logging.warning("Failed to send Slack alert: %s", exc)


def append_json_line(path: Path, payload: Dict[str, object]) -> None:
    """Append one JSON object as a single line to a file."""
    path.parent.mkdir(exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, separators=(",", ":")))
        handle.write("\n")


def load_ingestion_state() -> Dict[str, object]:
    if not INGESTION_STATE_FILE.exists():
        return {}
    return json.loads(INGESTION_STATE_FILE.read_text(encoding="utf-8"))


def save_ingestion_state(
    previous_schema: Optional[Sequence[str]],
    baseline_stats: Dict[str, Tuple[float, float]],
    records_since_last_retrain: int,
    drift_detected: int = 0,
) -> None:
    payload = {
        "previous_schema": list(previous_schema or []),
        "baseline_stats": {key: [mean, std] for key, (mean, std) in baseline_stats.items()},
        "records_since_last_retrain": records_since_last_retrain,
        "drift_detected": drift_detected,
    }
    INGESTION_STATE_FILE.parent.mkdir(exist_ok=True)
    INGESTION_STATE_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def restore_baseline_stats(raw_stats: Dict[str, object]) -> Dict[str, Tuple[float, float]]:
    restored: Dict[str, Tuple[float, float]] = {}
    for key, value in raw_stats.items():
        if isinstance(value, list) and len(value) == 2:
            restored[key] = (float(value[0]), float(value[1]))
    return restored


def emit_retrain_event(reason: str, details: Optional[Dict[str, object]] = None) -> None:
    """Record retrain trigger reason so retraining service can consume it."""
    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "reason": reason,
        "details": details or {},
    }
    append_json_line(RETRAIN_EVENTS_FILE, event)
    logging.info("Retraining trigger emitted: %s", reason)
    send_slack_alert(f"Retraining triggered. Reason: {reason}. Details: {event['details']}")


def compare_schema(previous: Optional[Sequence[str]], current: Sequence[str]) -> Tuple[Set[str], Set[str]]:
    """Return sets of added and removed features."""
    current_set = set(current)
    previous_set = set(previous or [])
    return current_set - previous_set, previous_set - current_set


def handle_schema_change(added: Set[str], removed: Set[str]) -> bool:
    """Process schema changes and return whether retraining should be triggered."""
    schema_changed = False
    if added:
        for feat in sorted(added):
            feature_added.inc()
            logging.warning("Schema change detected. Added feature: %s", feat)
            send_slack_alert(f"New feature detected in schema: {feat}")
        bump("feature_added_total", len(added))
        schema_changed = True

    if removed:
        for feat in sorted(removed):
            feature_removed.inc()
            logging.warning("Schema change detected. Removed feature: %s", feat)
            send_slack_alert(f"Feature removed from schema: {feat}")
        bump("feature_removed_total", len(removed))
        schema_changed = True

    return schema_changed


def fetch_batch(api_url: str, timeout_seconds: int) -> Optional[Dict[str, object]]:
    """Fetch one batch from data source, handling expected failures."""
    try:
        response = requests.get(api_url, timeout=timeout_seconds)
    except requests.RequestException as exc:
        logging.error("Data API request failed: %s", exc)
        datalake_unavailable.inc()
        bump("datalake_unavailable", 1)
        send_slack_alert(f"Data source request failed: {exc}")
        return None

    if response.status_code == 503:
        logging.error("Data API unavailable (503).")
        datalake_unavailable.inc()
        bump("datalake_unavailable", 1)
        send_slack_alert("Data source returned HTTP 503. Check API availability.")
        return None

    response.raise_for_status()
    raw_payload = response.json()
    try:
        return normalize_api_payload(raw_payload)
    except ValueError as exc:
        logging.error("Failed to normalize API payload: %s", exc)
        return None


def process_batch(
    payload: Dict[str, object],
    previous_schema: Optional[Sequence[str]],
    baseline_stats: Optional[Dict[str, Tuple[float, float]]],
    drift_threshold: float,
    min_new_records_for_retrain: int,
    records_since_last_retrain: int,
) -> Tuple[Sequence[str], Dict[str, Tuple[float, float]], int, int]:
    """Process one payload and return updated state and drift flag."""
    drift_flag = 0
    schema = [col for col in payload.get("schema", []) if col != "label"]
    records = payload.get("records", [])
    if not isinstance(schema, list) or not isinstance(records, list):
        raise ValueError("Payload must include list fields 'schema' and 'records'.")

    timestamp = datetime.now(timezone.utc).isoformat()
    append_json_line(
        BATCH_FILE,
        {
            "timestamp": timestamp,
            "schema": schema,
            "record_count": len(records),
            "records": records,
        },
    )
    records_processed_total.inc(len(records))
    bump("records_processed_total", len(records))
    records_since_last_retrain += len(records)
    logging.info("Ingested batch with %d records.", len(records))

    added, removed = compare_schema(previous_schema, schema)
    schema_changed = handle_schema_change(added, removed)
    if schema_changed:
        emit_retrain_event(
            reason="schema_change",
            details={"added": sorted(added), "removed": sorted(removed)},
        )
        records_since_last_retrain = 0

    feature_records = [{key: value for key, value in row.items() if key != "label"} for row in records]
    current_stats = compute_numeric_stats(feature_records)
    if baseline_stats is None and current_stats:
        baseline_stats = current_stats
        logging.info("Baseline stats initialized with current batch.")
    elif baseline_stats and current_stats:
        drift_result = detect_drift(
            baseline_stats=baseline_stats,
            current_stats=current_stats,
            threshold=drift_threshold,
        )
        drift_flag = 1 if drift_result.drift_detected else 0
        distribution_drift_detected.set(drift_flag)
        set_gauge("distribution_drift_detected", drift_flag)
        if drift_result.drift_detected:
            logging.warning(
                "Distribution drift detected (score=%.4f, threshold=%.4f).",
                drift_result.score,
                drift_threshold,
            )
            send_slack_alert(
                (
                    "Data distribution drift detected. "
                    f"Score={drift_result.score:.4f}, threshold={drift_threshold:.4f}."
                )
            )
            emit_retrain_event(
                reason="distribution_drift",
                details={
                    "score": round(drift_result.score, 6),
                    "threshold": drift_threshold,
                    "compared_features": drift_result.compared_features,
                },
            )
            records_since_last_retrain = 0

    if records_since_last_retrain >= min_new_records_for_retrain:
        emit_retrain_event(
            reason="new_data_volume",
            details={"records_since_last_retrain": records_since_last_retrain},
        )
        records_since_last_retrain = 0

    return schema, baseline_stats or {}, records_since_last_retrain, drift_flag


def run_ingestion_loop(
    api_url: str,
    interval_seconds: int,
    once: bool,
    drift_threshold: float,
    min_new_records_for_retrain: int,
    timeout_seconds: int,
) -> None:
    """Run periodic ingestion and monitoring loop."""
    DATA_DIR.mkdir(exist_ok=True)
    LOG_DIR.mkdir(exist_ok=True)

    state = load_ingestion_state()
    previous_schema: Optional[Sequence[str]] = state.get("previous_schema") or None
    baseline_stats = restore_baseline_stats(state.get("baseline_stats", {})) or None
    records_since_last_retrain = int(state.get("records_since_last_retrain", 0))
    drift_detected = int(state.get("drift_detected", 0))

    while True:
        try:
            payload = fetch_batch(api_url=api_url, timeout_seconds=timeout_seconds)
            if payload:
                previous_schema, baseline_stats, records_since_last_retrain, drift_detected = process_batch(
                    payload=payload,
                    previous_schema=previous_schema,
                    baseline_stats=baseline_stats,
                    drift_threshold=drift_threshold,
                    min_new_records_for_retrain=min_new_records_for_retrain,
                    records_since_last_retrain=records_since_last_retrain,
                )
        except Exception as exc:  # pragma: no cover
            logging.exception("Unexpected ingestion error: %s", exc)

        save_ingestion_state(
            previous_schema,
            baseline_stats or {},
            records_since_last_retrain,
            drift_detected=drift_detected,
        )

        if once:
            break
        time.sleep(interval_seconds)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run data ingestion and drift monitoring.")
    parser.add_argument("--api-url", default=DEFAULT_API_URL, help="Source API URL for /records")
    parser.add_argument("--interval", type=int, default=DEFAULT_INTERVAL_SECONDS, help="Polling interval in seconds")
    parser.add_argument("--drift-threshold", type=float, default=DEFAULT_DRIFT_THRESHOLD, help="Drift detection threshold")
    parser.add_argument(
        "--retrain-min-new-records",
        type=int,
        default=DEFAULT_RETRAIN_MIN_NEW_RECORDS,
        help="Retrain trigger threshold based on new records count",
    )
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS, help="HTTP timeout in seconds")
    parser.add_argument("--once", action="store_true", help="Run one ingestion cycle and exit")
    return parser.parse_args()


def main() -> None:
    setup_logging()
    args = parse_args()
    logging.info("Starting ingestion with api=%s interval=%ss", args.api_url, args.interval)
    run_ingestion_loop(
        api_url=args.api_url,
        interval_seconds=args.interval,
        once=args.once,
        drift_threshold=args.drift_threshold,
        min_new_records_for_retrain=args.retrain_min_new_records,
        timeout_seconds=args.timeout,
    )


if __name__ == "__main__":
    main()
