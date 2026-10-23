"""LangGraph integration, runs on the user's installed LangGraph environment.

Never uses OpenAI, Redis, or any private labels. No payment incurred.
"""
import asyncio
import pytest

pytest.importorskip("langgraph")

from netops_agent.agent import investigate
from netops_agent.agent_schema import Diagnosis


class ProbeClient:
    def __init__(self, live=None):
        self.live = live or {"interface_counters": {"util_pct": 95.0, "egress_discards": 2000}}
        self.calls = []

    def validate_incident_id(self, incident_id):
        assert incident_id == "INC-0001"

    async def context(self, incident_id):
        return {"telemetry": {"telemetry": {"cpu_pct": 90.0}}, "logs": {"logs": []}}

    async def diagnostic(self, incident_id, probe):
        self.calls.append(probe)
        return {"incident_id": incident_id, "probe": probe, "result": self.live.get(probe, {})}


class GreedyEngine:
    require_confirmation = True
    def __init__(self):
        self.plan_calls = 0

    async def choose_probe(self, incident_id, context, trace, available):
        self.plan_calls += 1
        return "interface_counters" if not trace else available[0] if available else None

    async def diagnose(self, incident_id, context, trace):
        return Diagnosis(incident_id=incident_id, root_cause="interface_congestion",
                         confidence=0.8, evidence=["Observed live probe"],
                         recommended_action="Review the switch interface utilization")


def run(client, engine, early_stop):
    return asyncio.run(investigate("INC-0001", client, engine, early_stop=early_stop))


def test_enabled_stops_after_first_confirmed_probe():
    c, e = ProbeClient(), GreedyEngine()
    out = run(c, e, True)
    assert out["tool_calls"] == 1
    assert out["early_stop_applied"] is True
    assert out["stop_reason"] == "confirmed_live_evidence"
    assert e.plan_calls == 1


def test_disabled_preserves_six_probes_legacy_behavior():
    c, e = ProbeClient(), GreedyEngine()
    out = run(c, e, False)
    assert out["tool_calls"] == 6
    assert out["early_stop_applied"] is False
    assert out["stop_reason"] == "tool_budget"


def test_unconfirmed_signal_does_not_stop_and_bounded_to_six():
    c, e = ProbeClient(live={"interface_counters": {"util_pct": 42, "egress_discards": 1}}), GreedyEngine()
    out = run(c, e, True)
    assert out["tool_calls"] == 6
    assert out["early_stop_applied"] is False


def test_mock_does_not_early_stop_even_if_forced_setting():
    from netops_agent.agent_engines import MockEngine
    c = ProbeClient(live={"cpu_process": {"total_cpu_pct": 90, "run_queue": 19}})
    out = run(c, MockEngine(), True)
    assert out["tool_calls"] == 1
    assert out["early_stop_applied"] is False
