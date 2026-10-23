"""Generate new locked 200-case evaluation data, distinct from Stage 1 dev seed."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from netops_agent.simulator import generate_cases


def main():
    parser = argparse.ArgumentParser(description='Generate 200 synthetic holdout incidents')
    parser.add_argument('--seed', type=int, default=20261022)
    parser.add_argument('--output', type=Path, default=Path('data/incidents_holdout_v1.jsonl'))
    parser.add_argument('--force', action='store_true', help='Explicitly overwrite existing dataset')
    args = parser.parse_args()
    if args.output.exists() and not args.force:
        parser.error(f'{args.output} already exists; refusing to replace locked dataset')
    if args.output.resolve() == Path('data/incidents_v1.jsonl').resolve():
        parser.error('Never overwrite the original development dataset')
    cases = generate_cases(seed=args.seed, per_class=40)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    payload = ''.join(json.dumps(case, sort_keys=True)+'\n' for case in cases)
    args.output.write_text(payload, encoding='utf-8')
    digest = hashlib.sha256(payload.encode('utf-8')).hexdigest()
    print(f'Generated {len(cases)} holdout cases: {args.output}')
    print(f'Dataset SHA256: {digest}')
    print('PRIVATE ground_truth is scoring-only; do not feed it to the Agent')

if __name__ == '__main__':
    main()
