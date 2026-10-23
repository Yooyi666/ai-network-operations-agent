"""Stage 5A: analyse latency/usage of existing Stage 4 evaluation JSONL.

No model calls, no cache mutation, no dataset labels read by the agent.
Usage:
  python scripts/analyze_latency.py --input results/stage5/before_10.jsonl
  python scripts/analyze_latency.py --input before.jsonl --compare after.jsonl

Uses nearest-rank percentile: ceil(p*n), so small samples cannot yield a
stable estimate of real p95 latency. Full end-to-end duration is used.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
from pathlib import Path
from typing import Any


def read_rows(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise ValueError(f"File does not exist: {path}")
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON at {path}:{lineno}: {exc}") from exc
        if not isinstance(row, dict) or not isinstance(row.get("incident_id"), str):
            raise ValueError(f"Invalid evaluation row at {path}:{lineno}")
        if row["incident_id"] in seen:
            raise ValueError(f"Duplicate incident_id in {path}: {row['incident_id']}")
        duration = row.get("duration_ms")
        if not isinstance(duration, (int, float)) or isinstance(duration, bool) or not math.isfinite(duration) or duration < 0:
            raise ValueError(f"Missing or invalid duration_ms at {path}:{lineno}")
        seen.add(row["incident_id"])
        rows.append(row)
    if not rows:
        raise ValueError(f"Empty evaluation file: {path}")
    return rows


def percentile(values: list[float], p: float) -> float:
    if not values or not 0 < p <= 1:
        raise ValueError("Need durations and percentile in (0, 1]")
    ordered = sorted(values)
    return ordered[math.ceil(p * len(ordered)) - 1]


def _avg(rows: list[dict[str, Any]], key: str) -> float | None:
    nums = [row[key] for row in rows if isinstance(row.get(key), (int, float)) and not isinstance(row.get(key), bool)]
    return round(statistics.mean(nums), 2) if len(nums) == len(rows) else None


def summarise(rows: list[dict[str, Any]]) -> dict[str, Any]:
    success = [row for row in rows if not row.get("error_type")]
    latencies = [float(row["duration_ms"]) for row in success]
    n = len(rows)
    fingerprints = {row.get("dataset_sha256") for row in rows if row.get("dataset_sha256")}
    if len(fingerprints) > 1:
        raise ValueError("Mixed dataset fingerprints: use one benchmark per file")
    modes = {row.get("mode") for row in rows if row.get("mode")}
    if len(modes) > 1:
        raise ValueError("Mixed inference modes in one benchmark file")
    return {
        "samples": n,
        "success_samples": len(success),
        "failed_samples": n - len(success),
        "failure_rate": round((n-len(success))/n, 4),
        "dataset_sha256": next(iter(fingerprints), None),
        "mode": next(iter(modes), None),
        "accuracy": round(sum(row.get("correct") is True for row in rows)/n, 4)
            if all(isinstance(row.get("correct"), bool) for row in rows) else None,
        "latency_ms_success_only": (
            {
                "mean": round(statistics.mean(latencies), 2),
                "p50": round(percentile(latencies, 0.5), 2),
                "p95": round(percentile(latencies, 0.95), 2),
                "max": round(max(latencies), 2),
            } if latencies else None
        ),
        "avg_tool_calls": _avg(rows, "tool_calls"),
        "avg_http_requests": _avg(rows, "http_requests"),
        "notes": [
            "p95 is nearest-rank over successful end-to-end evaluations only; errors reported separately.",
            "Cache is off in Stage 4 evaluate.py; reported times include live model/API latency and may vary with network load.",
            "Synthetic cases do not establish production latency or diagnostic accuracy.",
        ] + (["WARNING: <30 successes; p95 is highly unstable and only a smoke-test statistic."] if len(success) < 30 else []),
    }


def compare(before: list[dict[str, Any]], after: list[dict[str, Any]]) -> dict[str, Any]:
    b = {row["incident_id"]: row for row in before}
    a = {row["incident_id"]: row for row in after}
    if set(b) != set(a):
        raise ValueError("Compare requires identical incident IDs (paired cases)")
    fb = {r.get("dataset_sha256") for r in before}
    fa = {r.get("dataset_sha256") for r in after}
    if fb != fa or None in fb:
        raise ValueError("Compare requires matching, nonempty dataset SHA256")
    mb = {r.get("model") for r in before}
    ma = {r.get("model") for r in after}
    if mb != ma:
        raise ValueError("Compare requires identical models")
    before_summary, after_summary = summarise(before), summarise(after)
    both_success = [id_ for id_ in b if not b[id_].get("error_type") and not a[id_].get("error_type")]
    if not both_success:
        raise ValueError("No paired successful cases for latency comparison")
    d0 = [float(b[id_]["duration_ms"]) for id_ in both_success]
    d1 = [float(a[id_]["duration_ms"]) for id_ in both_success]
    p95_before, p95_after = percentile(d0, 0.95), percentile(d1, 0.95)
    return {
        "before": before_summary,
        "after": after_summary,
        "paired_successful_cases": len(both_success),
        "paired_p95_ms_before": round(p95_before, 2),
        "paired_p95_ms_after": round(p95_after, 2),
        "paired_p95_change_percent": round((p95_after/p95_before-1)*100, 2) if p95_before else None,
        "warning": "An observed p95 change is not causal proof; control cache, model, data, execution order and cloud-load variation.",
    }


def main() -> None:
    p = argparse.ArgumentParser(description="Analyse recorded netops Agent duration_ms; no paid API calls")
    p.add_argument("--input", type=Path, required=True, help="Stage 4/5 JSONL result file")
    p.add_argument("--compare", type=Path, help="Optional second run for paired analysis")
    p.add_argument("--output", type=Path, help="Optional JSON report file")
    args = p.parse_args()
    rows = read_rows(args.input)
    report = compare(rows, read_rows(args.compare)) if args.compare else summarise(rows)
    report["source"] = str(args.input)
    if args.compare:
        report["comparison_source"] = str(args.compare)
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    print(payload)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
        print(f"Report written to {args.output}")


if __name__ == "__main__":
    main()
