"""Train versioned classifiers from ingested data."""

from __future__ import annotations

from common.path_setup import ensure_project_root

ensure_project_root()

import argparse
import json
import logging
import os
import re
from pathlib import Path
from typing import Optional, Tuple

import joblib
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from exporter.metrics import model_accuracy
from model.bundle import ModelBundle
from model.data_loader import load_ingested_records, split_features_target

MODEL_DIR = Path("model")
LATEST_POINTER = MODEL_DIR / "latest_model.json"
ACCURACY_THRESHOLD = float(os.getenv("MODEL_ACCURACY_THRESHOLD", "0.80"))
MAX_TRAINING_ITERATIONS = int(os.getenv("MAX_TRAINING_ITERATIONS", "10"))
RANDOM_STATE = 42

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)


def next_model_version(model_dir: Path = MODEL_DIR) -> int:
    versions = []
    for path in model_dir.glob("model_v*.pkl"):
        match = re.search(r"model_v(\d+)\.pkl$", path.name)
        if match:
            versions.append(int(match.group(1)))
    return max(versions, default=0) + 1


def train_until_target(
    features,
    target,
    feature_columns: list,
    max_iterations: int = MAX_TRAINING_ITERATIONS,
    target_accuracy: float = ACCURACY_THRESHOLD,
) -> Tuple[Pipeline, float]:
    """Train repeatedly with increasing model capacity until accuracy target is met."""
    if len(features) < 10:
        raise ValueError("Need at least 10 records to train a model.")

    x_train, x_val, y_train, y_val = train_test_split(
        features,
        target,
        test_size=0.2,
        random_state=RANDOM_STATE,
        stratify=target if target.nunique() > 1 else None,
    )

    best_model: Optional[Pipeline] = None
    best_accuracy = 0.0

    estimators = [
        ("n_estimators_50", RandomForestClassifier(n_estimators=50, random_state=RANDOM_STATE)),
        ("n_estimators_100", RandomForestClassifier(n_estimators=100, random_state=RANDOM_STATE)),
        ("n_estimators_200", RandomForestClassifier(n_estimators=200, random_state=RANDOM_STATE)),
        ("n_estimators_300", RandomForestClassifier(n_estimators=300, random_state=RANDOM_STATE)),
    ]

    for index in range(max_iterations):
        estimator = estimators[min(index, len(estimators) - 1)][1]
        pipeline = Pipeline(
            [
                ("scaler", StandardScaler()),
                ("classifier", estimator),
            ]
        )
        pipeline.fit(x_train, y_train)
        val_preds = pipeline.predict(x_val)
        accuracy = float(accuracy_score(y_val, val_preds))
        logger.info("Training iteration %d accuracy=%.4f", index + 1, accuracy)

        if accuracy > best_accuracy:
            best_accuracy = accuracy
            best_model = pipeline

        if accuracy >= target_accuracy:
            return pipeline, accuracy

    if best_model is None:
        raise RuntimeError("Training failed to produce any model.")

    logger.warning(
        "Target accuracy %.2f not reached in %d iterations. Using best model (%.4f).",
        target_accuracy,
        max_iterations,
        best_accuracy,
    )
    return best_model, best_accuracy


def save_model(bundle: ModelBundle, model_dir: Path = MODEL_DIR) -> Path:
    model_dir.mkdir(exist_ok=True)
    model_path = model_dir / f"model_v{bundle.version}.pkl"
    joblib.dump(bundle, model_path)

    pointer = {
        "version": bundle.version,
        "path": model_path.as_posix(),
        "accuracy": bundle.accuracy,
        "feature_columns": bundle.feature_columns,
    }
    LATEST_POINTER.write_text(json.dumps(pointer, indent=2), encoding="utf-8")
    model_accuracy.set(bundle.accuracy)
    logger.info("Saved %s with accuracy=%.4f", model_path.name, bundle.accuracy)
    return model_path


def train_model(reason: str = "manual") -> ModelBundle:
    """Train a new model version from ingested data."""
    logger.info("Starting training. reason=%s", reason)
    frame = load_ingested_records()
    if frame.empty:
        raise ValueError("No ingested data found. Run ingestion before training.")

    features, target, feature_columns = split_features_target(frame)
    pipeline, accuracy = train_until_target(features, target, feature_columns)
    version = next_model_version()

    bundle = ModelBundle(
        estimator=pipeline,
        feature_columns=feature_columns,
        version=version,
        accuracy=accuracy,
    )
    save_model(bundle)
    return bundle


def load_latest_model(model_dir: Path = MODEL_DIR) -> Optional[ModelBundle]:
    if not LATEST_POINTER.exists():
        return None
    pointer = json.loads(LATEST_POINTER.read_text(encoding="utf-8"))
    model_path = Path(str(pointer["path"]).replace("\\", "/"))
    if not model_path.is_absolute():
        model_path = MODEL_DIR.parent / model_path
    if not model_path.exists():
        return None
    return joblib.load(model_path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train ML model from ingested data.")
    parser.add_argument("--reason", default="manual", help="Reason logged for this training run")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    train_model(reason=args.reason)


if __name__ == "__main__":
    main()
