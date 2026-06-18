"""Rebuild data/metrics_snapshot.json from existing data files before docker build."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from exporter.metrics_sync import rebuild_snapshot_from_data_files

if __name__ == "__main__":
    rebuild_snapshot_from_data_files()
    print("Wrote data/metrics_snapshot.json")
