"""Read-only incident repository. The evaluation label is always private."""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any


def dataset_path() -> Path:
    return Path(os.getenv("INCIDENT_DATASET", "data/incidents_v1.jsonl"))


@lru_cache(maxsize=1)
def load_incidents() -> dict[str, dict[str, Any]]:
    path = dataset_path()
    if not path.is_file():
        raise RuntimeError(f"Missing {path}. Run: python scripts/generate_dataset.py")
    cases = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    results = {item["incident_id"]: item for item in cases}
    if len(results) != len(cases):
        raise RuntimeError("Duplicate incident IDs")
    return results


def public_summary(item: dict[str, Any]) -> dict[str, Any]:
    return {key: item[key] for key in ("incident_id", "device_id", "severity")}
