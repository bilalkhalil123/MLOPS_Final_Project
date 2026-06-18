"""Serializable model bundle used by training and inference."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Sequence


@dataclass
class ModelBundle:
    estimator: Any
    feature_columns: List[str]
    version: int
    accuracy: float
    target_column: str = "label"

    def predict(self, rows: Sequence[Dict[str, Any]]) -> List[Any]:
        matrix = self._to_matrix(rows)
        return list(self.estimator.predict(matrix))

    def predict_proba(self, rows: Sequence[Dict[str, Any]]) -> List[List[float]]:
        matrix = self._to_matrix(rows)
        if hasattr(self.estimator, "predict_proba"):
            return list(self.estimator.predict_proba(matrix))
        preds = self.predict(rows)
        return [[1.0 - float(pred), float(pred)] for pred in preds]

    def _to_matrix(self, rows: Sequence[Dict[str, Any]]):
        import pandas as pd

        frame = pd.DataFrame(rows)
        for column in self.feature_columns:
            if column not in frame.columns:
                frame[column] = 0.0
        matrix = frame[self.feature_columns].apply(pd.to_numeric, errors="coerce").fillna(0.0)
        return matrix
