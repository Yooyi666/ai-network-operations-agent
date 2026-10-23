"""Seeded synthetic incident generation. Ground truth is for offline evaluation only."""
from __future__ import annotations

import random
from typing import Any

ROOT_CAUSES = (
    "dns_resolution_failure",
    "bgp_session_down",
    "interface_congestion",
    "cpu_saturation",
    "optical_link_degradation",
)

# All causes can appear on every device. Device ID must not reveal the label.
_DEVICE_POOL = (
    "edge-router-01",
    "edge-router-02",
    "agg-router-01",
    "agg-router-02",
    "core-router-01",
    "core-router-02",
)


def _round(value: float) -> float:
    return round(value, 2)


def _make_one(rng: random.Random, cause: str, incident_id: str) -> dict[str, Any]:
    # Some normal telemetry overlaps across classes; diagnostic probes provide stronger evidence.
    metrics = {
        "cpu_pct": _round(rng.uniform(20, 53)),
        "interface_util_pct": _round(rng.uniform(22, 66)),
        "packet_loss_pct": _round(rng.uniform(0.1, 3.1)),
        "rtt_ms": _round(rng.uniform(12, 65)),
        "dns_lookup_ms": _round(rng.uniform(16, 120)),
        "bgp_peer_up": 1,
        "optical_rx_dbm": _round(rng.uniform(-13, -6)),
    }
    logs = [
        "INFO telemetry exporter scrape successful",
        "INFO interface counters sampled over 60s window",
    ]
    if cause == "dns_resolution_failure":
        metrics["dns_lookup_ms"] = _round(rng.uniform(950, 2700))
        logs.append("WARN recursive resolver upstream query deadline exceeded")
    elif cause == "bgp_session_down":
        metrics["bgp_peer_up"] = 0
        metrics["packet_loss_pct"] = _round(rng.uniform(7, 24))
        metrics["rtt_ms"] = _round(rng.uniform(120, 310))
        logs.append("WARN bgpd peer FSM moved from Established to Idle")
    elif cause == "interface_congestion":
        metrics["interface_util_pct"] = _round(rng.uniform(87, 99.5))
        metrics["packet_loss_pct"] = _round(rng.uniform(4, 14))
        metrics["rtt_ms"] = _round(rng.uniform(90, 250))
        logs.append("WARN ifmgr egress queue discards increasing")
    elif cause == "cpu_saturation":
        metrics["cpu_pct"] = _round(rng.uniform(89, 99))
        metrics["rtt_ms"] = _round(rng.uniform(86, 265))
        logs.append("WARN scheduler runnable queue above usual range")
    elif cause == "optical_link_degradation":
        metrics["optical_rx_dbm"] = _round(rng.uniform(-28, -21))
        metrics["packet_loss_pct"] = _round(rng.uniform(9, 38))
        metrics["rtt_ms"] = _round(rng.uniform(130, 330))
        logs.append("WARN transceiver received power out of nominal range")
    else:
        raise ValueError(f"Unsupported cause: {cause}")

    # Adds noise to teach evidence triangulation rather than keyword-only classification.
    distractors = [
        "INFO NTP synchronization completed",
        "INFO config commit audit entry recorded",
        "NOTICE stale ARP cache entries reaped",
        "INFO link aggregation member count stable",
    ]
    logs.append(rng.choice(distractors))
    rng.shuffle(logs)

    probes = {
        "ping": {"rtt_ms": metrics["rtt_ms"], "loss_pct": metrics["packet_loss_pct"]},
        "dns_query": {"latency_ms": metrics["dns_lookup_ms"], "timed_out": metrics["dns_lookup_ms"] > 800},
        "bgp_status": {"session_state": "Established" if metrics["bgp_peer_up"] else "Idle"},
        "interface_counters": {"util_pct": metrics["interface_util_pct"], "egress_discards": 850 if cause == "interface_congestion" else rng.randint(0, 18)},
        "cpu_process": {"total_cpu_pct": metrics["cpu_pct"], "run_queue": rng.randint(20, 50) if cause == "cpu_saturation" else rng.randint(1, 5)},
        "optical_power": {"rx_dbm": metrics["optical_rx_dbm"], "alarm": metrics["optical_rx_dbm"] < -20},
    }
    return {
        "incident_id": incident_id,
        "device_id": rng.choice(_DEVICE_POOL),
        "severity": rng.choice(["P2", "P3"]),
        "telemetry": metrics,
        "logs": logs,
        "probes": probes,
        "ground_truth": cause,  # NEVER expose to agent-facing HTTP endpoints.
    }


def generate_cases(seed: int = 42, per_class: int = 40) -> list[dict[str, Any]]:
    """Deterministic, balanced 200-case dataset when per_class=40."""
    if per_class < 1:
        raise ValueError("per_class must be at least 1")
    rng = random.Random(seed)
    labels = [cause for cause in ROOT_CAUSES for _ in range(per_class)]
    rng.shuffle(labels)
    return [_make_one(rng, cause, f"INC-{i:04d}") for i, cause in enumerate(labels, start=1)]
