"""Tests for inference /predict endpoint."""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from serving import app as serving_app


@pytest.fixture
def client() -> TestClient:
    return TestClient(serving_app.app)


@pytest.fixture(autouse=True)
def clear_model() -> None:
    serving_app.set_model(None)
    yield
    serving_app.set_model(None)


def test_predict_endpoint_returns_prediction_and_confidence(client: TestClient) -> None:
    mock_model = MagicMock()
    mock_model.predict.return_value = [1]
    mock_model.predict_proba.return_value = [[0.15, 0.85]]

    serving_app.set_model(mock_model)
    response = client.post("/predict", json={"age": 30, "income": 50000})

    assert response.status_code == 200
    body = response.json()
    assert body["prediction"] == 1
    assert body["confidence"] == pytest.approx(0.85)
    mock_model.predict.assert_called_once()


def test_predict_without_model_returns_503(client: TestClient) -> None:
    response = client.post("/predict", json={"age": 30})

    assert response.status_code == 503
