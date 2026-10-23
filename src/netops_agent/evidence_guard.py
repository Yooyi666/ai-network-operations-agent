"""Bounded, public-evidence-only backstop for ambiguous synthetic network triage.

The thresholds below are **illustrative synthetic-lab heuristics**, not operational
network policies. They never read the private incident label or ground truth.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

# Every candidate is a read-only probe from the public allowlist.
ALL_PROBES = (
    "bgp_status", "optical_power", "dns_query", "cpu_process",
    "interface_counters", "ping",
)


def confirmed_evidence(trace: Sequence[Mapping[str, Any]]) -> bool:
    """True only when at least one cause-specific live probe strongly supports a fault.

    A ping loss/RTT observation is a symptom, not a cause confirmation.
    Ignore missing, failed, or malformed probes. No ground-truth access.
    """
    for event in trace:
        result = event.get("result")
        if not isinstance(result, Mapping):
            continue
        probe = event.get("probe")
        if probe == "bgp_status" and result.get("session_state") == "Idle":
            return True
        if probe == "optical_power" and result.get("alarm") is True:
            return True
        if probe == "dns_query" and result.get("timed_out") is True:
            return True
        if probe == "cpu_process":
            if _at_least(result.get("total_cpu_pct"), 85) and _at_least(result.get("run_queue"), 15):
                return True
        if probe == "interface_counters":
            if _at_least(result.get("util_pct"), 90) and _at_least(result.get("egress_discards"), 100):
                return True
    return False


def _at_least(value: Any, bound: float) -> bool:
    try:
        return value is not None and float(value) >= bound
    except (ValueError, TypeError):
        return False


def _below(value: Any, bound: float) -> bool:
    try:
        return value is not None and float(value) < bound
    except (ValueError, TypeError):
        return False


def next_confirmation_probe(
    context: Mapping[str, Any],
    trace: Sequence[Mapping[str, Any]],
    available: Sequence[str],
) -> str | None:
    """Pick a safe *next* measurement if the LLM stops without direct confirmation.

    Never auto-probe before the first LLM decision. Never repeat probes, exceed the
    caller's allowed list, or choose an arbitrary URL/command. If there is already
    direct confirmatory evidence, leave the decision to the LLM.
    """
    if not trace or confirmed_evidence(trace):
        return None
    tel = context.get("telemetry", {})
    metrics = tel.get("telemetry", {}) if isinstance(tel, Mapping) else {}
    if not isinstance(metrics, Mapping):
        metrics = {}
    priorities: list[str] = []
    if metrics.get("bgp_peer_up") == 0:
        priorities.append("bgp_status")
    if _below(metrics.get("optical_rx_dbm"), -20):
        priorities.append("optical_power")
    if _at_least(metrics.get("dns_lookup_ms"), 800):
        priorities.append("dns_query")
    if _at_least(metrics.get("cpu_pct"), 85):
        priorities.append("cpu_process")
    if (_at_least(metrics.get("interface_util_pct"), 85)
            or _at_least(metrics.get("packet_loss_pct"), 2)):
        priorities.append("interface_counters")
    # Complete the bounded search when misleading measurements obscure the cause.
    priorities.extend(ALL_PROBES)
    allowed = set(available)
    already_used = {str(event.get("probe")) for event in trace}
    for candidate in priorities:
        if candidate in allowed and candidate not in already_used:
            return candidate
    return None
