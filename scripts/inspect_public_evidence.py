"""Inspect PUBLIC incident evidence without invoking a paid LLM or viewing labels.

Use --base-url to target a running simulator with the intended INCIDENT_DATASET.
This diagnostic script performs only GET context and POST allowlisted read-only probes.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
from pathlib import Path
from typing import Any

import httpx

from netops_agent.agent_schema import PROBES
from netops_agent.early_stop import confirmed_causes

INCIDENT_ID_RE = re.compile(r'^INC-\d{4}$')


def summarise_public_evidence(incident_id: str, telemetry: dict[str, Any],
                              logs: dict[str, Any], trace: list[dict[str, Any]]) -> dict[str, Any]:
    """Rule signatures are descriptions of public evidence, NOT ground-truth labels."""
    return {
        'incident_id': incident_id,
        'telemetry': telemetry.get('telemetry', {}),
        'logs': logs.get('logs', []),
        'probe_trace': trace,
        'live_positive_signatures': sorted(confirmed_causes(trace)),
        'probe_errors': [e['probe'] for e in trace if 'error' in e],
    }


async def collect_case(http: httpx.AsyncClient, incident_id: str) -> dict[str, Any]:
    if not INCIDENT_ID_RE.fullmatch(incident_id):
        raise ValueError(f'Invalid incident ID: {incident_id}')
    response = await http.get(f'/incidents/{incident_id}/telemetry')
    response.raise_for_status()
    telemetry = response.json()
    response = await http.get(f'/incidents/{incident_id}/logs')
    response.raise_for_status()
    logs = response.json()
    trace: list[dict[str, Any]] = []
    for probe in PROBES:
        try:
            response = await http.post(f'/incidents/{incident_id}/diagnostics/{probe}')
            response.raise_for_status()
            payload = response.json()
            result = payload['result']
            if not isinstance(result, dict):
                raise ValueError('Invalid probe result')
            trace.append({'probe': probe, 'result': result})
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            trace.append({'probe': probe, 'error': type(exc).__name__})
    return summarise_public_evidence(incident_id, telemetry, logs, trace)


async def main() -> None:
    parser = argparse.ArgumentParser(description='Non-LLM public-evidence inspection')
    parser.add_argument('--incident-ids', nargs='+', required=True)
    parser.add_argument('--base-url', default='http://127.0.0.1:8004')
    parser.add_argument('--output', type=Path, default=Path('results/stage5/stage5d_public_evidence.json'))
    args = parser.parse_args()
    async with httpx.AsyncClient(base_url=args.base_url, timeout=5.0) as http:
        records = [await collect_case(http, incident_id) for incident_id in args.incident_ids]
    report = {
        'source_base_url': args.base_url,
        'warning': 'This report contains PUBLIC simulator responses only. It does not include ground_truth and does not reproduce historical LLM traces.',
        'cases': records,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
    for item in records:
        print(f"{item['incident_id']}: positive live signatures={item['live_positive_signatures']}; errors={item['probe_errors']}")
    print(f'Report: {args.output}')


if __name__ == '__main__':
    asyncio.run(main())
