"""No OpenAI API usage; deterministic local stress dataset validation."""
from __future__ import annotations
import json
from collections import Counter
from netops_agent.simulator import ROOT_CAUSES
from netops_agent.stress_simulator import make_stress_cases
from netops_agent.evaluation import baseline_predict, baseline_tools_predict


def test_fixed_seed_and_class_balance():
    a=make_stress_cases(seed=7,per_class=4)
    b=make_stress_cases(seed=7,per_class=4)
    assert a==b and len(a)==20
    assert Counter(x['ground_truth'] for x in a)=={label:4 for label in ROOT_CAUSES}
    assert len(set(x['incident_id'] for x in a))==len(a)


def test_stress_has_unreliable_telemetry_and_strong_live_probes():
    cases=make_stress_cases(seed=20261101,per_class=40)
    inferred=[]
    for case in cases:
        public={'telemetry':{'telemetry':case['telemetry']}}
        inferred.append(baseline_predict(public))
        probes=case['probes']
        assert baseline_tools_predict(probes)==case['ground_truth']
        # There is no answer key in any of the tool responses.
        for payload in (case['telemetry'],case['logs'],case['probes']):
            assert 'ground_truth' not in json.dumps(payload)
    assert sum(x==c['ground_truth'] for x,c in zip(inferred,cases))<200


def test_unsupported_probe_observations_give_unknown():
    assert baseline_tools_predict({})=='unknown'
    assert baseline_tools_predict({'bgp_status':{'session_state':'Established'}})=='unknown'
