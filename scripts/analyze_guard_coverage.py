"""Analyse operational triage coverage versus accuracy on labelled synthetic runs.

No network, no model calls. Expects --consistency-guard on evaluation JSONL.
Reviewing a case is an abstention, NEVER counted as an automatic success.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def summarize_guard(rows: list[dict]) -> dict:
    if not rows:
        raise ValueError("No evaluation records")
    if any('diagnosis_verification' not in r for r in rows):
        raise ValueError("This JSONL lacks guard results; evaluate with --consistency-guard on")
    total = len(rows)
    errors = [r for r in rows if r.get('error_type')]
    accepted = [r for r in rows if not r.get('error_type')
                and r.get('triage_decision', {}).get('status') == 'accepted_in_synthetic_lab'
                and r.get('triage_decision', {}).get('accepted_root_cause') == r.get('prediction')]
    accepted_correct = sum(r.get('prediction') == r.get('ground_truth') for r in accepted)
    # Treat every unaccepted prediction as not automatically resolved.
    # This is coverage-adjusted correct classification, not raw LLM accuracy.
    return {
        'cases': total,
        'raw_llm_correct': sum(r.get('correct') is True for r in rows),
        'raw_llm_accuracy': round(sum(r.get('correct') is True for r in rows)/total, 4),
        'automatically_accepted': len(accepted),
        'human_review_or_failed': total-len(accepted),
        'execution_failures': len(errors),
        'autonomous_coverage': round(len(accepted)/total, 4),
        'selective_accuracy': round(accepted_correct/len(accepted), 4) if accepted else None,
        'overall_auto_correct_fraction': round(accepted_correct/total, 4),
        'incorrect_accepted': len(accepted)-accepted_correct,
        'note': ('Signatures are synthetic and may be imperfect; reporting selective accuracy '
                 'without coverage is misleading. Any test used for tuning is not an unbiased final holdout.'),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    rows = [json.loads(line) for line in args.input.read_text(encoding='utf-8').splitlines() if line.strip()]
    report = summarize_guard(rows)
    formatted = json.dumps(report, indent=2, ensure_ascii=False)
    print(formatted)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(formatted+'\n', encoding='utf-8')


if __name__ == '__main__':
    main()
