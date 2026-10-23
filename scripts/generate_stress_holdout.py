"""Generate a new, separate, fixed-seed v2 stress benchmark; never overwrite v1."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
from netops_agent.stress_simulator import make_stress_cases


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--seed', type=int, default=20261101)
    p.add_argument('--output', type=Path, default=Path('data/incidents_stress_v2.jsonl'))
    args = p.parse_args()
    if args.output.exists():
        p.error('Refusing to overwrite a locked dataset. Choose a new --output path.')
    if args.output.resolve() in (Path('data/incidents_v1.jsonl').resolve(),
                                 Path('data/incidents_holdout_v1.jsonl').resolve()):
        p.error('Cannot overwrite v1 datasets.')
    records = make_stress_cases(seed=args.seed, per_class=40)
    payload = ''.join(json.dumps(case,sort_keys=True)+'\n' for case in records)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(payload,encoding='utf-8')
    print(f'Generated {len(records)} stress incidents: {args.output}')
    print('SHA256:', hashlib.sha256(payload.encode('utf-8')).hexdigest())
    print('Private labels: evaluation only. Never send ground_truth to the Agent.')

if __name__ == '__main__':
    main()
