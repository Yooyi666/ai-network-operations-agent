"""Run from repository root: python scripts/generate_dataset.py"""
import json
from collections import Counter
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from netops_agent.simulator import generate_cases  # noqa: E402


def main():
    out = Path(__file__).resolve().parents[1] / "data" / "incidents_v1.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    cases = generate_cases(seed=42, per_class=40)
    out.write_text("".join(json.dumps(case, sort_keys=True) + "\n" for case in cases), encoding="utf-8")
    print(f"Generated {len(cases)} cases: {out}")
    print("Ground truth (PRIVATE):", dict(Counter(c["ground_truth"] for c in cases)))
    print("Do not use ground_truth during agent inference.")


if __name__ == "__main__":
    main()
