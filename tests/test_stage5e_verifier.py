"""Stage 5E pure tests: no model, simulator, internet or private labels."""
from netops_agent.diagnosis_verifier import verify_prediction


def event(probe, **result):
    return {'probe': probe, 'result': result}


def test_matching_dns_signature_supported():
    v = verify_prediction('dns_resolution_failure', [event('dns_query', timed_out=True)])
    assert v['status'] == 'supported'
    assert not v['review_required']


def test_wrong_cpu_predicted_despite_dns_signature():
    v = verify_prediction('cpu_saturation', [
        event('cpu_process', total_cpu_pct=64, run_queue=2),
        event('dns_query', timed_out=True),
    ])
    assert v['status'] == 'contradicted'
    assert v['live_confirmed_causes'] == ['dns_resolution_failure']
    assert v['review_required']


def test_wrong_interface_predicted_despite_dns_signature():
    v = verify_prediction('interface_congestion', [
        event('interface_counters', util_pct=74, egress_discards=36),
        event('dns_query', timed_out=True),
    ])
    assert v['status'] == 'contradicted'


def test_failed_probe_cannot_confirm():
    v = verify_prediction('dns_resolution_failure', [
        {'probe': 'dns_query', 'error': 'TimeoutError', 'result': {'timed_out': True}},
    ])
    assert v['status'] == 'unverified'
    assert v['review_required']


def test_multiple_positive_causes_ambiguous():
    v = verify_prediction('dns_resolution_failure', [
        event('dns_query', timed_out=True),
        event('bgp_status', session_state='Idle'),
    ])
    assert v['status'] == 'ambiguous'
    assert len(v['live_confirmed_causes']) == 2


def test_ping_cannot_establish_root_cause():
    assert verify_prediction('interface_congestion', [
        event('ping', loss_pct=40, rtt_ms=300),
    ])['status'] == 'unverified'


def test_normal_live_cpu_not_a_positive_signature():
    assert verify_prediction('cpu_saturation', [
        event('cpu_process', total_cpu_pct=67, run_queue=2),
    ])['status'] == 'unverified'
