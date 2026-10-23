"""Audit matched Early Stopping evaluation JSONL files, without model/API calls.

Usage (project root):
python scripts/audit_early_stop.py --before results/stage5/final_before30.jsonl \
    --after results/stage5/final_after30.jsonl \
    --out-prefix results/stage5/stage5c_audit

This script compares evaluator-generated records. It does not import ground-truth
files or send requests, and it does not reveal LLM internal reasoning.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from statistics import mean
from typing import Any


def load_rows(path: Path) -> dict[str, dict[str, Any]]:
    if not path.is_file():
        raise ValueError(f"Missing JSONL file: {path}")
    output: dict[str, dict[str, Any]] = {}
    for n, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in {path} at line {n}: {exc}") from exc
        required = ("incident_id", "ground_truth", "prediction", "correct", "duration_ms", "tool_calls", "http_requests", "dataset_sha256", "mode", "model")
        missing = [key for key in required if key not in row]
        if missing:
            raise ValueError(f"Missing fields {missing} in {path} at line {n}")
        if not isinstance(row["correct"], bool):
            raise ValueError(f"Non-boolean correct in {path} at line {n}")
        incident_id = str(row["incident_id"])
        if incident_id in output:
            raise ValueError(f"Duplicate incident_id {incident_id} in {path}")
        output[incident_id] = row
    if not output:
        raise ValueError(f"Empty results file: {path}")
    return output


def audit(before: dict[str, dict[str, Any]], after: dict[str, dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    ids_b, ids_a = set(before), set(after)
    if ids_b != ids_a:
        raise ValueError(f"Unmatched incident IDs: before_only={sorted(ids_b - ids_a)} after_only={sorted(ids_a - ids_b)}")
    for field in ("dataset_sha256", "mode", "model"):
        values = {row[field] for row in (*before.values(), *after.values())}
        if len(values) != 1:
            raise ValueError(f"Mismatched {field}: {sorted(map(str,values))}")
    for dataset, expected_mode in ((before, "off"), (after, "on")):
        for item in dataset.values():
            recorded_mode = item.get("early_stop")
            if recorded_mode is not None and recorded_mode != expected_mode:
                raise ValueError(f"Expected early_stop={expected_mode} for {item['incident_id']}, found {recorded_mode}")
    result_rows: list[dict[str, Any]] = []
    classifications = {"both_correct":0,"regression":0,"recovery":0,"both_incorrect":0}
    for incident_id in sorted(ids_b):
        b, a = before[incident_id], after[incident_id]
        if b["ground_truth"] != a["ground_truth"]:
            raise ValueError(f"Ground-truth disagreement for {incident_id}")
        b_correct, a_correct = b["correct"], a["correct"]
        if b_correct and a_correct: classification = "both_correct"
        elif b_correct: classification = "regression"
        elif a_correct: classification = "recovery"
        else: classification = "both_incorrect"
        classifications[classification] += 1
        result_rows.append({
            "incident_id": incident_id,
            "ground_truth": b["ground_truth"],
            "before_prediction": b["prediction"],
            "after_prediction": a["prediction"],
            "before_correct": b_correct,
            "after_correct": a_correct,
            "classification": classification,
            "early_stop_applied": a.get("early_stop_applied"),
            "stop_reason": a.get("stop_reason"),
            "before_tool_calls": b["tool_calls"],
            "after_tool_calls": a["tool_calls"],
            "before_http_requests": b["http_requests"],
            "after_http_requests": a["http_requests"],
            "before_duration_ms": b["duration_ms"],
            "after_duration_ms": a["duration_ms"],
            "latency_saved_ms": round(float(b["duration_ms"]) - float(a["duration_ms"]),2),
            "before_error_type": b.get("error_type"),
            "after_error_type": a.get("error_type"),
        })
    n = len(result_rows)
    b_latency = mean(float(x["before_duration_ms"]) for x in result_rows)
    a_latency = mean(float(x["after_duration_ms"]) for x in result_rows)
    summary = {
        "cases":n,
        "dataset_sha256":next(iter(before.values()))["dataset_sha256"],
        "model":next(iter(before.values()))["model"],
        "before_correct":sum(x["before_correct"] for x in result_rows),
        "after_correct":sum(x["after_correct"] for x in result_rows),
        "transitions":classifications,
        "accuracy_difference_pp":round(100*(sum(x["after_correct"]-x["before_correct"] for x in result_rows)/n),2),
        "early_stop_applied_count":sum(x["early_stop_applied"] is True for x in result_rows),
        "early_stop_regressions_count":sum(x["classification"]=="regression" and x["early_stop_applied"] is True for x in result_rows),
        "mean_latency_ms_before":round(b_latency,2),
        "mean_latency_ms_after":round(a_latency,2),
        "mean_latency_change_pct":round(100*(a_latency-b_latency)/b_latency,2) if b_latency else None,
        "notes":[
            "Paired comparison uses the same incident IDs but API/LLM responses may be stochastic.",
            "early_stop_applied on a regression is a debugging lead, not proof of causality.",
            "Per-case evaluator results contain no probe trace: rerunning an incident may not reproduce the same model choice.",
            "Do not tune a model using these holdout labels and then reuse this set as a final unbiased benchmark.",
        ],
    }
    return summary, result_rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Per-incident audit of Early Stopping effect; local analysis only")
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path, required=True)
    parser.add_argument("--out-prefix", type=Path, default=Path("results/stage5/stage5c_audit"))
    args = parser.parse_args()
    summary, rows = audit(load_rows(args.before), load_rows(args.after))
    args.out_prefix.parent.mkdir(parents=True, exist_ok=True)
    csv_path = args.out_prefix.with_suffix(".csv")
    json_path = args.out_prefix.with_suffix(".json")
    with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    json_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print("\nCASES NEEDING REVIEW:")
    errors = [row for row in rows if row["classification"] != "both_correct"]
    for row in errors:
        print(f"{row['incident_id']}: {row['classification']}; truth={row['ground_truth']}; "
              f"before={row['before_prediction']} ({row['before_tool_calls']} tools); "
              f"after={row['after_prediction']} ({row['after_tool_calls']} tools); "
              f"early_stop={row['early_stop_applied']} reason={row['stop_reason']}")
    if not errors:
        print("None")
    print(f"\nReports: {csv_path}, {json_path}")


if __name__ == "__main__":
    try:
        main()
    except ValueError as exc:
        raise SystemExit(f"Audit stopped: {exc}") from exc
