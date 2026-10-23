"""Offline tests: exercise real LangGraph routing with a deterministic engine, no API key."""
import asyncio

import httpx
import pytest

from netops_agent.agent import MAX_TOOL_CALLS, PublicNetworkClient, investigate
from netops_agent.agent_engines import MockEngine
from netops_agent.agent_schema import PROBES
from netops_agent.api import app
from netops_agent.storage import load_incidents  # Test-only; NEVER import in agent code.


def test_mock_agent_bgp_incident():
    async def run():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as http:
            return await investigate("INC-0001", PublicNetworkClient(http), MockEngine())

    result = asyncio.run(run())
    assert result["diagnosis"]["root_cause"] == "bgp_session_down"
    assert result["trace"][0]["probe"] == "bgp_status"
    assert result["trace"][0]["result"]["session_state"] == "Idle"
    assert result["tool_calls"] == 1
    assert "ground_truth" not in str(result)


def test_mock_agent_five_categories():
    cases = load_incidents()  # Only offline test code sees ground truth.
    examples = {}
    for incident_id, case in cases.items():
        examples.setdefault(case["ground_truth"], incident_id)
    assert len(examples) == 5

    async def run():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as http:
            for truth, incident_id in examples.items():
                outcome = await investigate(incident_id, PublicNetworkClient(http), MockEngine())
                assert outcome["diagnosis"]["root_cause"] == truth
                assert outcome["tool_calls"] == 1
    asyncio.run(run())


def test_reject_unsafe_inputs():
    async def run():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as http:
            client = PublicNetworkClient(http)
            with pytest.raises(ValueError):
                await client.diagnostic("../../etc/passwd", "ping")
            with pytest.raises(ValueError):
                await client.diagnostic("INC-0001", "exec_shell")
    asyncio.run(run())


def test_graph_enforces_max_calls_and_no_duplicate_probes():
    class GreedyEngine(MockEngine):
        async def choose_probe(self, incident_id, context, trace, available):
            return available[0] if available else None

    async def run():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as http:
            return await investigate("INC-0001", PublicNetworkClient(http), GreedyEngine())
    result = asyncio.run(run())
    assert result["tool_calls"] == MAX_TOOL_CALLS == len(PROBES)
    assert len(set(event["probe"] for event in result["trace"])) == MAX_TOOL_CALLS


def test_missing_incident_returns_http_error():
    async def run():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as http:
            with pytest.raises(httpx.HTTPStatusError):
                await investigate("INC-9999", PublicNetworkClient(http), MockEngine())
    asyncio.run(run())
