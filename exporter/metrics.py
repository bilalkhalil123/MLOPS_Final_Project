"""Prometheus metrics scaffold."""

from prometheus_client import Counter, Gauge, Histogram

model_accuracy = Gauge("model_accuracy", "Current validation accuracy")
records_processed_total = Counter("records_processed_total", "Total ingested records")
retrain_count_total = Counter("retrain_count_total", "Number of retrain events")
distribution_drift_detected = Gauge("distribution_drift_detected", "1 if drift detected")
feature_added = Counter("feature_added", "Features added")
feature_removed = Counter("feature_removed", "Features removed")
datalake_unavailable = Counter("datalake_unavailable", "Number of HTTP 503 responses")
response_delay_seconds = Histogram("response_delay_seconds", "Prediction latency")
