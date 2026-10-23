"""Stage 5E LangGraph integration: deterministic stub engines, no billed calls."""
import asyncio
import pytest

pytest.importorskip('langgraph')
from netops_agent.agent import investigate
from netops_agent.agent_schema import Diagnosis


class FakeClient:
    def validate_incident_id(self, incident_id):
        assert incident_id == 'INC-0001'

    async def context(self, incident_id):
        return {'telemetry': {'telemetry': {}}, 'logs': {'logs': []}}

    async def diagnostic(self, incident_id, probe):
        if probe == 'dns_query':
            return {'result': {'latency_ms': 2100, 'timed_out': True}}
        return {'result': {}}


class Engine:
    require_confirmation = True
    def __init__(self, revise='correct'):
        self.revise = revise
        self.recheck_calls = 0
    async def choose_probe(self, incident_id, context, trace, available):
        return 'dns_query' if not trace else None
    async def diagnose(self, incident_id, context, trace):
        return Diagnosis(incident_id=incident_id, root_cause='cpu_saturation',
                         confidence=0.9, evidence=['Stale telemetry CPU'],
                         recommended_action='Review the public CPU counters')
    async def reconsider_diagnosis(self, incident_id, context, trace, initial, causes):
        self.recheck_calls += 1
        assert causes == ['dns_resolution_failure']
        if self.revise == 'raise':
            raise RuntimeError('Transient LLM error')
        label = 'dns_resolution_failure' if self.revise == 'correct' else 'cpu_saturation'
        return Diagnosis(incident_id=incident_id, root_cause=label,
                         confidence=0.75, evidence=['Live DNS timed out'],
                         recommended_action='Check resolver state safely')


def run(engine, consistency_guard=True):
    return asyncio.run(investigate('INC-0001', FakeClient(), engine,
                       early_stop=True, consistency_guard=consistency_guard))


def test_guard_recheck_changes_a_disagreeing_llm_output():
    engine = Engine()
    out = run(engine)
    assert out['tool_calls'] == 1
    assert out['diagnosis']['root_cause'] == 'dns_resolution_failure'
    assert out['diagnosis_verification']['status'] == 'supported'
    assert out['diagnosis_verification']['initial_prediction'] == 'cpu_saturation'
    assert out['diagnosis_verification']['recheck_used']
    assert engine.recheck_calls == 1


def test_unresolved_disagreement_is_flagged_not_silently_overwritten():
    engine = Engine('wrong')
    out = run(engine)
    assert out['review_required'] is True
    assert out['diagnosis']['root_cause'] == 'cpu_saturation'
    assert out['diagnosis_verification']['status'] == 'contradicted'
    assert engine.recheck_calls == 1


def test_recheck_error_is_reported_not_masked():
    out = run(Engine('raise'))
    assert out['review_required'] is True
    assert out['diagnosis_verification']['recheck_error'] == 'RuntimeError'


def test_disabled_guard_keeps_legacy_behavior():
    engine=Engine()
    out=run(engine, False)
    assert out['diagnosis']['root_cause']=='cpu_saturation'
    assert 'diagnosis_verification' not in out
    assert engine.recheck_calls==0
