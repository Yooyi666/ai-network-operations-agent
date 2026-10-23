"""Needs real LangGraph or compatible test double; no paid API calls."""
import asyncio
import pytest

pytest.importorskip('langgraph')
from netops_agent.agent import investigate
from netops_agent.agent_schema import Diagnosis

class Client:
    def validate_incident_id(self, incident_id):
        assert incident_id == 'INC-0001'
    async def context(self, incident_id):
        return {'telemetry': {'telemetry': {}}, 'logs': {'logs': []}}
    async def diagnostic(self, incident_id, probe):
        return {'result': {'latency_ms': 2025.81, 'timed_out': True}}

class Engine:
    require_confirmation = True
    async def choose_probe(self, incident_id, context, trace, available):
        return 'dns_query' if not trace else None
    async def diagnose(self, incident_id, context, trace):
        return Diagnosis(incident_id=incident_id, root_cause='interface_congestion',
                         confidence=.9, evidence=['Wrong'], recommended_action='Inspect DNS logs')
    async def reconsider_diagnosis(self, incident_id, context, trace, initial, causes):
        return initial

def test_review_required_does_not_accept_wrong_root_cause():
    report = asyncio.run(investigate('INC-0001', Client(), Engine(),
                                    early_stop=True, consistency_guard=True))
    assert report['review_required'] is True
    assert report['diagnosis']['root_cause'] == 'interface_congestion'
    assert report['triage_decision']['accepted_root_cause'] is None
    assert report['triage_decision']['provisional_root_cause'] == 'interface_congestion'
