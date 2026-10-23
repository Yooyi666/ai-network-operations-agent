"""Stage 5D: public-evidence inspection and optional trace capture, offline."""
import asyncio
import importlib.util
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('inspect_public_evidence', ROOT/'scripts/inspect_public_evidence.py')
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


def test_public_evidence_signatures_and_no_ground_truth():
    row = module.summarise_public_evidence(
        'INC-0027', {'telemetry': {'cpu_pct': 90}}, {'logs': ['old warning']},
        [{'probe': 'dns_query', 'result': {'timed_out': True, 'latency_ms': 2200}},
         {'probe': 'interface_counters', 'result': {'util_pct': 70, 'egress_discards': 10}}],
    )
    assert row['live_positive_signatures'] == ['dns_resolution_failure']
    assert 'ground_truth' not in row


def test_failed_probe_not_treated_as_positive():
    row = module.summarise_public_evidence(
        'INC-0027', {}, {}, [{'probe': 'dns_query', 'error': 'TimeoutError',
                              'result': {'timed_out': True}}]
    )
    assert row['live_positive_signatures'] == []
    assert row['probe_errors'] == ['dns_query']


def test_bad_id_rejected_before_api_call():
    async def run():
        async with httpx.AsyncClient(base_url='http://localhost') as h:
            await module.collect_case(h, '../secret')
    with pytest.raises(ValueError, match='Invalid incident ID'):
        asyncio.run(run())


def test_collect_case_calls_only_allowlisted_probes():
    requests = []
    async def handler(req):
        requests.append((req.method, req.url.path))
        path = req.url.path
        if path.endswith('/telemetry'):
            return httpx.Response(200, json={'telemetry': {}})
        if path.endswith('/logs'):
            return httpx.Response(200, json={'logs': []})
        return httpx.Response(200, json={'result': {'session_state': 'Established'}})
    async def run():
        async with httpx.AsyncClient(base_url='http://test', transport=httpx.MockTransport(handler)) as h:
            return await module.collect_case(h, 'INC-0027')
    output = asyncio.run(run())
    from netops_agent.agent_schema import PROBES
    assert len(requests) == 2 + len(PROBES)
    assert requests[0][0] == 'GET'
    assert requests[1][0] == 'GET'
    assert all(method == 'POST' for method, _ in requests[2:])
    assert len(output['probe_trace']) == len(PROBES)


def test_evaluation_trace_capture_is_opt_in_no_llm():
    pytest.importorskip('langgraph')
    from netops_agent.api import app
    from netops_agent.agent_engines import MockEngine
    from netops_agent.storage import load_incidents
    from scripts.evaluate import evaluate_case
    case = load_incidents()['INC-0001']

    async def run(capture):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                     base_url='http://test') as h:
            return await evaluate_case(case, 'mock', h, MockEngine(),
                                       timeout=2, attempts=2,
                                       capture_trace=capture)

    with_trace = asyncio.run(run(True))
    without_trace = asyncio.run(run(False))
    assert with_trace['probe_trace']
    assert all('ground_truth' not in event for event in with_trace['probe_trace'])
    assert 'probe_trace' not in without_trace
