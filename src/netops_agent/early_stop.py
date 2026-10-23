"""Optional synthetic-lab early-stop policy; never reads labels or private files.

This optimization acts only on concrete, *live* read-only diagnostic evidence,
not telemetry or an LLM confidence score. An ambiguous/conflicting signal forces
continued investigation (within the existing six-probe budget).

Thresholds are SYNTHETIC LAB definitions, not production network thresholds.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from .evidence_guard import confirmed_evidence

_CAUSE_BY_PROBE = {
    "bgp_status": "bgp_session_down",
    "optical_power": "optical_link_degradation",
    "dns_query": "dns_resolution_failure",
    "cpu_process": "cpu_saturation",
    "interface_counters": "interface_congestion",
}


def confirmed_causes(trace: Sequence[Mapping[str, Any]]) -> frozenset[str]:
    """Set of unambiguously supported root-cause signatures from live probes."""
    causes: set[str] = set()
    for event in trace:
        if "error" in event or not isinstance(event.get("result"), Mapping):
            continue
        cause = _CAUSE_BY_PROBE.get(event.get("probe"))
        if cause and confirmed_evidence([event]):
            causes.add(cause)
    return frozenset(causes)


def is_early_stop_safe(trace: Sequence[Mapping[str, Any]]) -> bool:
    """Need one cause-specific signature, not a ping or a mere telemetry alert."""
    return len(confirmed_causes(trace)) == 1
