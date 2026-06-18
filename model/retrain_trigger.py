"""Process retrain events and evaluate whether model retraining is required."""

from __future__ import annotations

from common.path_setup import ensure_project_root

ensure_project_root()

import argparse
import json
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional

import requests
from sklearn.metrics import accuracy_score
from sklearn.model_selection import train_test_split

from exporter.metrics import model_accuracy, retrain_count_total
from exporter.metrics_snapshot import bump
from model.data_loader import load_ingested_records, split_features_target
from model.train import ACCURACY_THRESHOLD, RANDOM_STATE, load_latest_model, train_model

RETRAIN_EVENTS_FILE = Path("data/retrain_events.jsonl")
RETRAIN_STATE_FILE = Path("data/retrain_state.json")
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)


def send_slack_alert(message: str) -> None:
    if not SLACK_WEBHOOK_URL:
        logger.info("Slack webhook not configured. Alert skipped: %s", message)
        return
    try:
        requests.post(SLACK_WEBHOOK_URL, json={"text": message}, timeout=10).raise_for_status()
    except requests.RequestException as exc:
        logger.warning("Failed to send Slack alert: %s", exc)


def load_state() -> Dict[str, int]:
    if not RETRAIN_STATE_FILE.exists():
        return {"processed_events": 0}
    return json.loads(RETRAIN_STATE_FILE.read_text(encoding="utf-8"))


def save_state(state: Dict[str, int]) -> None:
    RETRAIN_STATE_FILE.parent.mkdir(exist_ok=True)
    RETRAIN_STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def load_events() -> List[Dict[str, object]]:
    if not RETRAIN_EVENTS_FILE.exists():
        return []
    events: List[Dict[str, object]] = []
    with RETRAIN_EVENTS_FILE.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    return events


def evaluate_current_accuracy() -> Optional[float]:
    bundle = load_latest_model()
    frame = load_ingested_records()
    if bundle is None or frame.empty:
        return None

    features, target, _ = split_features_target(frame)
    if len(features) < 10:
        return None

    _, x_val, _, y_val = train_test_split(
        features,
        target,
        test_size=0.2,
        random_state=RANDOM_STATE,
        stratify=target if target.nunique() > 1 else None,
    )
    preds = bundle.estimator.predict(x_val)
    accuracy = float(accuracy_score(y_val, preds))
    model_accuracy.set(accuracy)
    return accuracy


def should_retrain_for_accuracy() -> bool:
    accuracy = evaluate_current_accuracy()
    if accuracy is None:
        return True
    return accuracy < ACCURACY_THRESHOLD


def process_pending_events() -> int:
    events = load_events()
    state = load_state()
    start_index = int(state.get("processed_events", 0))
    pending = events[start_index:]
    if not pending:
        return 0

    reasons = [str(event.get("reason", "unknown")) for event in pending]
    combined_reason = ", ".join(sorted(set(reasons)))
    logger.info("Processing %d retrain event(s): %s", len(pending), combined_reason)

    bundle = train_model(reason=combined_reason)
    retrain_count_total.inc(len(pending))
    bump("retrain_count_total", len(pending))
    save_state({"processed_events": len(events)})

    send_slack_alert(
        (
            "Retraining triggered.\n"
            f"Reason: {combined_reason}\n"
            f"New model version: v{bundle.version}\n"
            f"New accuracy: {bundle.accuracy:.4f}"
        )
    )
    return len(pending)


def run_retrain_check(force: bool = False) -> None:
    processed = 0
    if force or process_pending_events() > 0:
        processed += 1
    elif should_retrain_for_accuracy():
        logger.warning("Model accuracy below threshold. Retraining.")
        bundle = train_model(reason="low_accuracy")
        retrain_count_total.inc()
        bump("retrain_count_total", 1)
        send_slack_alert(
            (
                "Retraining triggered.\n"
                "Reason: low_accuracy\n"
                f"New model version: v{bundle.version}\n"
                f"New accuracy: {bundle.accuracy:.4f}"
            )
        )
        processed += 1

    if processed == 0:
        accuracy = evaluate_current_accuracy()
        logger.info("No retraining required. Current accuracy=%s", accuracy)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate and run model retraining.")
    parser.add_argument("--force", action="store_true", help="Force retrain even without pending events")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_retrain_check(force=args.force)


if __name__ == "__main__":
    main()
