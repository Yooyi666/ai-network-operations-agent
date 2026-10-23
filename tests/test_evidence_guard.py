"""No API key, no ground truth labels: public evidence guard regression tests."""
from netops_agent.evidence_guard import confirmed_evidence, next_confirmation_probe


def _case(cpu=90.94, interface=71.93, loss=3.9):
    return {"telemetry": {"telemetry": {
        "cpu_pct": cpu, "interface_util_pct": interface,
        "packet_loss_pct": loss, "bgp_peer_up": 1,
        "optical_rx_dbm": -15.35, "dns_lookup_ms": 65.26,
    }}}


def test_stale_cpu_telemetry_requires_independent_interface_confirmation():
    # Generic failure mode, not dependent on incident ID or private labels.
    observed = [{"probe": "cpu_process", "result": {
        "run_queue": 4, "total_cpu_pct": 35.53,
    }}]
    assert not confirmed_evidence(observed)
    assert next_confirmation_probe(_case(), observed, [
        "ping", "dns_query", "interface_counters", "bgp_status", "optical_power"
    ]) == "interface_counters"


def test_confirmed_congestion_allows_stopping():
    trace = [
        {"probe": "cpu_process", "result": {"run_queue": 4, "total_cpu_pct": 35.53}},
        {"probe": "interface_counters", "result": {"util_pct": 95.04, "egress_discards": 1570}},
    ]
    assert confirmed_evidence(trace)
    assert next_confirmation_probe(_case(), trace, ["dns_query"]) is None


def test_ping_is_symptom_not_confirmatory():
    trace = [{"probe": "ping", "result": {"rtt_ms": 190, "loss_pct": 12}}]
    assert not confirmed_evidence(trace)
    assert next_confirmation_probe(_case(), trace, ["interface_counters"]) == "interface_counters"


def test_failure_is_not_counted_as_evidence():
    trace = [{"probe": "cpu_process", "error": "TimeoutError"}]
    assert not confirmed_evidence(trace)
    assert next_confirmation_probe(_case(), trace, ["interface_counters"]) == "interface_counters"


def test_bounded_allowlist_and_no_duplicate_probe():
    trace = [{"probe": "cpu_process", "result": {"run_queue": 2}}]
    assert next_confirmation_probe(_case(), trace, ["cpu_process"]) is None
    assert next_confirmation_probe(_case(), trace, ["exec_shell"]) is None
    assert next_confirmation_probe(_case(), [], ["interface_counters"]) is None


def test_positive_bgp_dns_optical_cpu_live_signals():
    for probe, data in [
        ("bgp_status", {"session_state": "Idle"}),
        ("dns_query", {"timed_out": True}),
        ("optical_power", {"alarm": True}),
        ("cpu_process", {"total_cpu_pct": 94, "run_queue": 20}),
    ]:
        assert confirmed_evidence([{"probe": probe, "result": data}])


def test_normal_live_probe_does_not_confirm_telemetry_alert():
    assert not confirmed_evidence([{
        "probe": "cpu_process", "result": {"total_cpu_pct": 35, "run_queue": 4}
    }])
    assert not confirmed_evidence([{
        "probe": "interface_counters", "result": {"util_pct": 40, "egress_discards": 2}
    }])
