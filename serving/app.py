"""Inference API with health, predict, and metrics endpoints."""

from __future__ import annotations

from common.path_setup import ensure_project_root

ensure_project_root()

import logging
import time
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from exporter.metrics import model_accuracy, response_delay_seconds
from exporter.metrics_sync import sync_metrics_from_snapshot
from model.bundle import ModelBundle
from model.train import load_latest_model

logger = logging.getLogger(__name__)

app = FastAPI(title="MLOps Inference Service")

_model: Optional[ModelBundle] = None


def set_model(model: Any) -> None:
    """Inject or replace the loaded model (used in tests and training pipeline)."""
    global _model
    _model = model
    if isinstance(model, ModelBundle):
        model_accuracy.set(model.accuracy)


def get_model() -> ModelBundle:
    if _model is None:
        raise HTTPException(status_code=503, detail="Model not loaded")
    return _model


def load_model_on_startup() -> None:
    bundle = load_latest_model()
    if bundle is not None:
        set_model(bundle)
        logger.info("Loaded model v%s (accuracy=%.4f)", bundle.version, bundle.accuracy)


@app.on_event("startup")
def startup_event() -> None:
    load_model_on_startup()


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "model_loaded": _model is not None}


@app.get("/metrics")
def metrics() -> Response:
    sync_metrics_from_snapshot()
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/predict")
def predict(features: Dict[str, Any]) -> dict:
    """Accept feature JSON and return prediction with confidence."""
    model = get_model()
    start = time.perf_counter()
    try:
        prediction = model.predict([features])[0]
        proba = model.predict_proba([features])[0]
        confidence = float(max(proba))
        return {
            "prediction": _to_json_scalar(prediction),
            "confidence": confidence,
            "model_version": model.version if isinstance(model, ModelBundle) else None,
        }
    finally:
        response_delay_seconds.observe(time.perf_counter() - start)


def _to_json_scalar(value: Any) -> Any:
    if hasattr(value, "item"):
        return value.item()
    return value
