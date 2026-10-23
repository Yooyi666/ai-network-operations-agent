"""Synthetic stress benchmark v2: mixed evidence, misleading telemetry, no label disclosure.

Methodology is fixed BEFORE any paid LLM evaluation. This is a training/evaluation
lab; not an empirical sample of production incidents. A single primary cause is
assigned per case, with unrelated background alerts and possibly stale metrics.
"""
from __future__ import annotations

import random
from typing import Any

from .simulator import ROOT_CAUSES, _DEVICE_POOL

LOG_HINTS = {
    'dns_resolution_failure': 'WARN recursive query retried after upstream resolution delay',
    'bgp_session_down': 'WARN routing neighbor keepalive exchange interrupted',
    'interface_congestion': 'WARN outgoing queue drop counter increased in traffic burst',
    'cpu_saturation': 'WARN scheduler runnable backlog grew on control plane',
    'optical_link_degradation': 'WARN transceiver signal received below expected range',
}
GENERAL_LOGS = (
    'INFO interface counters sampled over 60s interval',
    'INFO packet capture collector disconnected briefly',
    'INFO time synchronisation drift correction applied',
    'WARN management plane saw transient high latency',
    'NOTICE routing daemon process restarted last week',
    'INFO telemetry exporter scrape successful',
)


def make_stress_cases(seed: int = 20261101, per_class: int = 40) -> list[dict[str, Any]]:
    """Return shuffled balanced cases, deterministic for a fixed seed.

    Telemetry is sometimes stale/incomplete and may include a non-causal alarm.
    A relevant *live* diagnostic probe is expected to confirm the true cause.
    The simulator exposes these fields except ``ground_truth`` via its fixed API.
    """
    if per_class < 1:
        raise ValueError('per_class must be >=1')
    rng = random.Random(seed)
    causes = [cause for cause in ROOT_CAUSES for _ in range(per_class)]
    rng.shuffle(causes)
    cases: list[dict[str, Any]] = []
    for i, cause in enumerate(causes, 1):
        metrics: dict[str, Any] = {
            'cpu_pct': round(rng.uniform(27, 78), 2),
            'interface_util_pct': round(rng.uniform(34, 83), 2),
            'packet_loss_pct': round(rng.uniform(0.2, 10), 2),
            'rtt_ms': round(rng.uniform(30, 225), 2),
            'dns_lookup_ms': round(rng.uniform(35, 560), 2),
            'bgp_peer_up': 1,
            'optical_rx_dbm': round(rng.uniform(-18.7, -7.5), 2),
        }
        # Primary telemetry signature is often missing due to stale scrapes.
        if rng.random() < 0.60:
            if cause == 'dns_resolution_failure':
                metrics['dns_lookup_ms'] = round(rng.uniform(900, 2100), 2)
            elif cause == 'bgp_session_down':
                metrics['bgp_peer_up'] = 0
            elif cause == 'interface_congestion':
                metrics['interface_util_pct'] = round(rng.uniform(88, 99), 2)
            elif cause == 'cpu_saturation':
                metrics['cpu_pct'] = round(rng.uniform(88, 99), 2)
            else:
                metrics['optical_rx_dbm'] = round(rng.uniform(-28, -21), 2)
        # Independent unrelated/transient abnormal metric, for confounding.
        alternatives = [x for x in ROOT_CAUSES if x != cause]
        if rng.random() < 0.35:
            distraction = rng.choice(alternatives)
            if distraction == 'dns_resolution_failure':
                metrics['dns_lookup_ms'] = round(rng.uniform(840, 1500), 2)
            elif distraction == 'bgp_session_down':
                metrics['bgp_peer_up'] = 0
            elif distraction == 'interface_congestion':
                metrics['interface_util_pct'] = round(rng.uniform(86, 96), 2)
            elif distraction == 'cpu_saturation':
                metrics['cpu_pct'] = round(rng.uniform(86, 96), 2)
            else:
                metrics['optical_rx_dbm'] = round(rng.uniform(-26, -20.5), 2)
        # Some missing logs, and some misleading historical messages.
        logs = list(rng.sample(GENERAL_LOGS, k=2))
        if rng.random() < 0.70:
            logs.append(LOG_HINTS[cause])
        if rng.random() < 0.20:
            logs.append('INFO historic event (not active): ' + LOG_HINTS[rng.choice(alternatives)])
        rng.shuffle(logs)

        # Live read-only probe outputs provide independent corroborating evidence.
        # Unlike stale telemetry, one strongly discriminative probe is assumed.
        probes = {
            'ping': {
                'rtt_ms': round(rng.uniform(120, 270), 2),
                'loss_pct': round(rng.uniform(4, 23), 2),
            },
            'dns_query': {
                'latency_ms': round(rng.uniform(1000, 3000), 2) if cause == 'dns_resolution_failure' else round(rng.uniform(18, 400), 2),
                'timed_out': cause == 'dns_resolution_failure',
            },
            'bgp_status': {'session_state': 'Idle' if cause == 'bgp_session_down' else 'Established'},
            'interface_counters': {
                'util_pct': round(rng.uniform(92, 99), 2) if cause == 'interface_congestion' else round(rng.uniform(23, 84), 2),
                'egress_discards': rng.randint(600, 1800) if cause == 'interface_congestion' else rng.randint(0, 70),
            },
            'cpu_process': {
                'total_cpu_pct': round(rng.uniform(94, 99), 2) if cause == 'cpu_saturation' else round(rng.uniform(21, 75), 2),
                'run_queue': rng.randint(20, 48) if cause == 'cpu_saturation' else rng.randint(1, 7),
            },
            'optical_power': {
                'rx_dbm': round(rng.uniform(-30, -23), 2) if cause == 'optical_link_degradation' else round(rng.uniform(-19, -6), 2),
                'alarm': cause == 'optical_link_degradation',
            },
        }
        cases.append({
            'incident_id': f'INC-{i:04d}',
            'device_id': rng.choice(_DEVICE_POOL),
            'severity': rng.choice(['P2', 'P3']),
            'telemetry': metrics,
            'logs': logs,
            'probes': probes,
            'ground_truth': cause,
        })
    return cases
