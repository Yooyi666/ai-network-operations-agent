"""Free, post-hoc comparison of saved public probe evidence with past predictions.

This does NOT reconstruct the probes seen by the LLM during the past runs.
No OpenAI/API calls, private labels or network calls.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from netops_agent.diagnosis_verifier import verify_prediction


def main() -> None:
    p = argparse.ArgumentParser(description='Offline public-evidence consistency audit')
    p.add_argument('--public-report', type=Path,
                   default=Path('results/stage5/stage5d_public_evidence.json'))
    p.add_argument('--prediction', nargs='+', required=True,
                   help='Pairs such as INC-0027=interface_congestion')
    p.add_argument('--output', type=Path,
                   default=Path('results/stage5/stage5e_consistency_audit.json'))
    args = p.parse_args()
    predictions: dict[str, str] = {}
    for item in args.prediction:
        if '=' not in item:
            p.error(f'Expected incident=prediction: {item}')
        incident_id, label = item.split('=', 1)
        if not re.fullmatch(r'INC-\d{4}', incident_id):
            p.error(f'Invalid incident ID: {incident_id}')
        predictions[incident_id] = label
    report = json.loads(args.public_report.read_text(encoding='utf-8'))
    cases = {row['incident_id']: row for row in report['cases']}
    rows = []
    for incident_id, prediction in predictions.items():
        if incident_id not in cases:
            p.error(f'Missing public case: {incident_id}')
        result = verify_prediction(prediction, cases[incident_id]['probe_trace'])
        rows.append({'incident_id': incident_id, 'past_prediction': prediction, **result})
    output = {
        'warning': ('Post-hoc ALL-probe consistency only; not an original model trace, '
                    'not the original evidence available at early stop, and not ground truth.'),
        'cases': rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, ensure_ascii=False)+'\n',encoding='utf-8')
    print(json.dumps(output, indent=2, ensure_ascii=False))
    print(f'Report saved: {args.output}')


if __name__ == '__main__':
    main()
