"""Fast, no-API, no-LangGraph required tests for evidence-gated early stopping."""
from netops_agent.early_stop import confirmed_causes, is_early_stop_safe


def event(probe, **result):
    return {"probe": probe, "result": result}


def test_not_on_empty_trace_or_telemetry_only():
    assert not is_early_stop_safe([])


def test_ping_loss_is_only_a_symptom():
    assert not is_early_stop_safe([event("ping", loss_pct=30, rtt_ms=200)])


def test_stale_cpu_metric_needs_live_confirmation():
    trace = [event("cpu_process", total_cpu_pct=35.53, run_queue=4)]
    assert not is_early_stop_safe(trace)


def test_all_five_specific_causes_confirmed():
    probes = [
        event("bgp_status", session_state="Idle"),
        event("optical_power", alarm=True),
        event("dns_query", timed_out=True),
        event("cpu_process", total_cpu_pct=92, run_queue=16),
        event("interface_counters", util_pct=95, egress_discards=1570),
    ]
    for probe in probes:
        assert is_early_stop_safe([probe])


def test_conflicting_positive_live_evidence_disables_early_stop():
    trace = [event("cpu_process", total_cpu_pct=95, run_queue=19),
             event("interface_counters", util_pct=95, egress_discards=400)]
    assert len(confirmed_causes(trace)) == 2
    assert not is_early_stop_safe(trace)


def test_failed_probe_is_not_evidence():
    assert not is_early_stop_safe([{"probe": "bgp_status", "error": "TimeoutError",
                                   "result": {"session_state": "Idle"}}])


def test_unknown_probe_not_trusted():
    assert not is_early_stop_safe([event("exec_shell", session_state="Idle")])


def test_duplicates_do_not_create_conflicting_causes():
    trace = [event("bgp_status", session_state="Idle"), event("bgp_status", session_state="Idle")]
    assert confirmed_causes(trace) == frozenset({"bgp_session_down"})
