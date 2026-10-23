"""Stage 4 batched, resumable and auditable evaluation. Run from project root.

Real OpenAI calls require --allow-billed-api; a 200-case run requires --all.
Inference NEVER receives ground_truth. The evaluator scores after predictions.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

from netops_agent.evaluation import (
    LABELS, baseline_predict, baseline_tools_predict, load_labelled_cases,
    public_matches_private, summarise, write_reports,
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description='Evaluate network diagnosis on locked synthetic cases')
    p.add_argument('--mode', choices=('baseline', 'baseline-tools', 'mock', 'openai'), default='baseline')
    p.add_argument('--dataset', type=Path, default=Path('data/incidents_holdout_v1.jsonl'))
    p.add_argument('--base-url', default='http://127.0.0.1:8001')
    group = p.add_mutually_exclusive_group()
    group.add_argument('--limit', type=int, default=None, help='Run N cases (default 5)')
    group.add_argument('--all', action='store_true', help='Explicitly evaluate all 200 cases')
    p.add_argument('--output', type=Path, default=None, help='Persistent per-case JSONL results')
    p.add_argument('--resume', action='store_true', help='Continue a matching interrupted run')
    p.add_argument('--allow-billed-api', action='store_true', help='Consent to paid OpenAI API requests')
    p.add_argument('--timeout', type=float, default=2.0)
    p.add_argument('--attempts', type=int, default=3)
    p.add_argument('--early-stop', choices=('off', 'on'), default='off',
                   help='Opt-in early stopping, only effective for real LLM mode')
    p.add_argument('--consistency-guard', choices=('off', 'on'), default='off',
                   help='Opt-in public-evidence contradiction check and bounded LLM reconsideration')
    p.add_argument('--capture-trace', action='store_true',
                   help='Store public probe execution trace in JSONL for debugging; no private label is sent to the model')
    p.add_argument('--pause', type=float, default=0.0, help='Seconds between cases')
    p.add_argument('--max-consecutive-errors', type=int, default=3, help='Stop after repeated failures to limit API cost')
    return p.parse_args()


def load_completed(path: Path, fingerprint: str, mode: str, model: str, resume: bool,
                   early_stop: str = 'off', consistency_guard: str = 'off') -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    if not resume:
        raise ValueError(f'Result file exists: {path}. Use --resume or select a NEW output path')
    completed: dict[str, dict[str, Any]] = {}
    for line in path.read_text(encoding='utf-8').splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if (row.get('dataset_sha256') != fingerprint or row.get('mode') != mode
                or row.get('model') != model or row.get('early_stop', 'off') != early_stop
                or row.get('consistency_guard', 'off') != consistency_guard):
            raise ValueError('Resume blocked: previous results have different dataset/mode/model/early_stop')
        key = row['incident_id']
        if key in completed:
            raise ValueError(f'Duplicate completed incident {key}')
        completed[key] = row
    return completed


async def verify_dataset(http: httpx.AsyncClient, cases: list[dict[str, Any]]) -> None:
    """Holdout-vs-server consistency check before scoring any result."""
    sample: list[dict[str, Any]] = []
    seen: set[str] = set()
    for case in cases:
        label = case['ground_truth']
        if label not in seen:
            seen.add(label)
            sample.append(case)
    for case in sample:
        incident_id = case['incident_id']
        response = await http.get(f'/incidents/{incident_id}/telemetry')
        response.raise_for_status()
        if not public_matches_private(response.json(), case):
            raise RuntimeError(
                f'DATASET MISMATCH at {incident_id}: evaluator labels and simulator differ. '
                'Start the server with the right INCIDENT_DATASET and port.'
            )


async def evaluate_case(
    case: dict[str, Any], mode: str, http: httpx.AsyncClient,
    engine: Any, timeout: float, attempts: int, early_stop: bool = False,
    capture_trace: bool = False, consistency_guard: bool = False,
) -> dict[str, Any]:
    incident_id = case['incident_id']
    t0 = time.perf_counter()
    prediction = None
    tool_calls = 0
    degraded = False
    http_requests = 0
    stop_reason = None
    early_stop_applied = False
    probe_trace = None
    verification = None
    triage_decision = None
    error_type = None
    error_message = None
    # Public inference sees incident ID only. PRIVATE label is copied AFTER inference.
    try:
        if mode == 'baseline':
            from netops_agent.reliable_client import ReliableNetworkClient, RetryPolicy
            client = ReliableNetworkClient(http, policy=RetryPolicy(attempts=attempts, timeout_seconds=timeout), cache=None)
            public_context = await client.context(incident_id)
            prediction = baseline_predict(public_context)
            http_requests = client.stats['http_requests']
            degraded = bool(public_context.get('collection_errors'))
        elif mode == 'baseline-tools':
            # Fairer reference: this rule baseline may inspect the same six
            # read-only diagnostics that the Agent can request. No labels.
            from netops_agent.reliable_client import ReliableNetworkClient, RetryPolicy
            client = ReliableNetworkClient(http, policy=RetryPolicy(attempts=attempts, timeout_seconds=timeout), cache=None)
            public_context = await client.context(incident_id)
            degraded = bool(public_context.get('collection_errors'))
            probe_results = {}
            for probe in ('ping', 'bgp_status', 'optical_power', 'dns_query', 'cpu_process', 'interface_counters'):
                response = await client.diagnostic(incident_id, probe)
                probe_results[probe] = response['result']
                tool_calls += 1
            prediction = baseline_tools_predict(probe_results)
            http_requests = client.stats['http_requests']
        else:
            from netops_agent.agent import investigate
            from netops_agent.reliable_client import ReliableNetworkClient, RetryPolicy
            client = ReliableNetworkClient(http, policy=RetryPolicy(attempts=attempts, timeout_seconds=timeout), cache=None)
            result = await investigate(incident_id, client, engine,
                                       early_stop=early_stop, consistency_guard=consistency_guard)
            verification = result.get('diagnosis_verification')
            triage_decision = result.get('triage_decision')
            stop_reason = result.get('stop_reason')
            early_stop_applied = bool(result.get('early_stop_applied'))
            prediction = result['diagnosis']['root_cause']
            tool_calls = result['tool_calls']
            if capture_trace:
                probe_trace = result.get('trace', [])
            degraded = bool(result.get('degraded'))
            http_requests = client.stats['http_requests']
    except Exception as exc:
        error_type = type(exc).__name__
        error_message = str(exc)[:240]
        if 'client' in locals():
            http_requests = client.stats.get('http_requests', 0)
    duration_ms = round((time.perf_counter()-t0)*1000, 2)
    return {
        'incident_id': incident_id,
        'ground_truth': case['ground_truth'],  # scorer output ONLY, not LLM input
        'prediction': prediction,
        'correct': prediction == case['ground_truth'] and error_type is None,
        'error_type': error_type,
        'error_message': error_message,
        'degraded': degraded,
        'tool_calls': tool_calls,
        'http_requests': http_requests,
        'duration_ms': duration_ms,
        'stop_reason': stop_reason,
        'early_stop_applied': early_stop_applied,
        **({'diagnosis_verification': verification,
            'review_required': bool(verification['review_required'])} if verification is not None else {}),
        **({'triage_decision': triage_decision} if triage_decision is not None else {}),
        **({'probe_trace': probe_trace} if capture_trace and probe_trace is not None else {}),
    }


async def main() -> None:
    load_dotenv()
    args = parse_args()
    if args.mode == 'openai' and not args.allow_billed_api:
        raise ValueError('Paid API calls blocked. Explicitly pass --allow-billed-api')
    if args.limit is not None and args.limit < 1:
        raise ValueError('--limit must be positive')
    if args.pause < 0:
        raise ValueError('--pause must be nonnegative')
    if args.max_consecutive_errors < 1:
        raise ValueError('--max-consecutive-errors must be positive')
    cases, fingerprint = load_labelled_cases(args.dataset)
    limit = len(cases) if args.all else min(args.limit or 5, len(cases))
    cases = cases[:limit]
    model = os.getenv('NETOPS_MODEL_NAME', 'gpt-4.1-mini') if args.mode == 'openai' else args.mode
    output = args.output or Path(f'results/stage4/{args.mode}_{fingerprint[:8]}_{limit}.jsonl')
    output.parent.mkdir(parents=True, exist_ok=True)
    completed = load_completed(output, fingerprint, args.mode, model, args.resume,
                               args.early_stop, args.consistency_guard)
    if any(i not in {case['incident_id'] for case in cases} for i in completed):
        raise ValueError('Resume file contains incident IDs outside selected --limit/--all')

    engine = None
    if args.mode in ('mock', 'openai'):
        from netops_agent.agent_engines import make_engine
        engine = make_engine(args.mode)

    # Explicitly disable Redis cache for fair, repeatable evaluations. Nothing writes to Redis.
    async with httpx.AsyncClient(base_url=args.base_url, timeout=httpx.Timeout(max(5.0, args.timeout+1))) as http:
        await verify_dataset(http, cases)
        print(f'Preflight PASS: server dataset matches {args.dataset}; SHA256={fingerprint}')
        print(f'Mode={args.mode}, model={model}, early_stop={args.early_stop}, '
              f'cases={limit}, cache=off, output={output}')
        consecutive_errors = 0
        aborted = False
        for index, case in enumerate(cases, 1):
            incident_id = case['incident_id']
            if incident_id in completed:
                continue
            row = await evaluate_case(case, args.mode, http, engine, args.timeout,
                                      args.attempts, early_stop=args.early_stop == 'on',
                                      capture_trace=args.capture_trace,
                                      consistency_guard=args.consistency_guard == 'on')
            row.update({
                'mode': args.mode, 'model': model, 'dataset_sha256': fingerprint,
                'early_stop': args.early_stop,
                'consistency_guard': args.consistency_guard,
                'capture_trace': args.capture_trace,
                'timestamp_utc': datetime.now(timezone.utc).isoformat(),
            })
            with output.open('a', encoding='utf-8') as f:
                f.write(json.dumps(row, ensure_ascii=False)+'\n')
            completed[incident_id] = row
            consecutive_errors = consecutive_errors + 1 if row['error_type'] else 0
            print(f'[{index}/{limit}] {incident_id} predicted={row["prediction"]} '
                  f'correct={row["correct"]} error={row["error_type"] or "none"}')
            if consecutive_errors >= args.max_consecutive_errors:
                print(f'STOP: {consecutive_errors} consecutive errors; preserving partial results', file=sys.stderr)
                aborted = True
                break
            if args.pause and index < limit:
                await asyncio.sleep(args.pause)

    ordered = [completed[c['incident_id']] for c in cases if c['incident_id'] in completed]
    metadata = {
        'mode': args.mode, 'model': model,
        'dataset_path': str(args.dataset), 'dataset_sha256': fingerprint,
        'simulator_base_url': args.base_url, 'cache': 'off',
        'early_stop': args.early_stop,
        'cases_requested': limit,
        'reported_at_utc': datetime.now(timezone.utc).isoformat(),
        'benchmark_notes': 'Sequential; API/tool and model latency included; cold evidence cache; telemetry-only baseline versus fixed six-probe baseline; not a production benchmark.',
    }
    summary_file, confusion_file = write_reports(ordered, output, metadata)
    stats = summarise(ordered)
    print(f'FINISHED: {stats["correct"]}/{stats["evaluated"]} correct = {stats["accuracy"]:.1%}')
    print(f'Coverage: {stats["coverage"]:.1%}; failures: {stats["failed_cases"]}')
    print(f'Reports: {summary_file}, {confusion_file}')
    if stats['failed_cases']:
        print('NOTE: failed cases counted as incorrect. Inspect error_types before conclusions.')
    if aborted:
        raise RuntimeError('Aborted after repeated errors. Check results and use --resume after fixing.')


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (ValueError, RuntimeError, FileNotFoundError, httpx.HTTPError) as exc:
        print(f'Evaluation stopped: {type(exc).__name__}: {exc}', file=sys.stderr)
        raise SystemExit(1)
