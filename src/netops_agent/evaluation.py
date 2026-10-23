"""Stage 4: strictly post-hoc scoring for synthetic network incidents.

Only the evaluator may access labels. Inference takes PUBLIC simulator data only.
This dataset's metrics are intentionally easy to threshold; report that limitation.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

from .simulator import ROOT_CAUSES

LABELS = tuple(ROOT_CAUSES)


def load_labelled_cases(path: Path) -> tuple[list[dict[str, Any]], str]:
    """Load PRIVATE labels into evaluator memory, never into agent prompts/tools."""
    raw = path.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    cases = [json.loads(line) for line in raw.decode('utf-8').splitlines() if line.strip()]
    if len(cases) != len({c['incident_id'] for c in cases}):
        raise ValueError('Duplicate incident IDs in evaluation dataset')
    if not cases or any(c.get('ground_truth') not in LABELS for c in cases):
        raise ValueError('Empty dataset or invalid ground truth labels')
    return cases, sha


def baseline_predict(public_context: Mapping[str, Any]) -> str:
    """Transparent telemetry-only, threshold-based baseline, no ground-truth access.

    These deterministic signals are nearly perfectly separable in dataset v1.
    A 100% baseline is plausible and must be disclosed, not weakened artificially.
    """
    metrics = public_context['telemetry']['telemetry']
    if metrics.get('bgp_peer_up') == 0:
        return 'bgp_session_down'
    if float(metrics.get('optical_rx_dbm', 0)) < -20:
        return 'optical_link_degradation'
    if float(metrics.get('dns_lookup_ms', 0)) > 800:
        return 'dns_resolution_failure'
    if float(metrics.get('cpu_pct', 0)) > 85:
        return 'cpu_saturation'
    if float(metrics.get('interface_util_pct', 0)) > 85:
        return 'interface_congestion'
    return 'unknown'



def baseline_tools_predict(probes: Mapping[str, Mapping[str, Any]]) -> str:
    """Rule baseline with read-only live diagnostic evidence for fairer comparison.

    Independent fixed decision logic; no ground_truth, logs or model involved.
    The v2 synthetic simulator guarantees one strong live diagnostic signal.
    """
    if probes.get('bgp_status', {}).get('session_state') == 'Idle':
        return 'bgp_session_down'
    if probes.get('optical_power', {}).get('alarm') is True:
        return 'optical_link_degradation'
    if probes.get('dns_query', {}).get('timed_out') is True:
        return 'dns_resolution_failure'
    if float(probes.get('cpu_process', {}).get('run_queue', 0)) >= 15:
        return 'cpu_saturation'
    if float(probes.get('interface_counters', {}).get('egress_discards', 0)) >= 500:
        return 'interface_congestion'
    return 'unknown'

def public_matches_private(public_telemetry: Mapping[str, Any], private_case: Mapping[str, Any]) -> bool:
    """Verify simulator and evaluator use the SAME dataset version, not cached data."""
    return (public_telemetry.get('incident_id') == private_case['incident_id']
            and public_telemetry.get('telemetry') == private_case['telemetry'])


def wilson_interval(correct: int, n: int, z: float = 1.959963984540054) -> tuple[float, float]:
    """Approximate 95% Wilson interval (descriptive, assumes independent cases)."""
    if n < 0 or not 0 <= correct <= n:
        raise ValueError('Invalid counts')
    if n == 0:
        return (0.0, 1.0)
    p = correct / n
    denom = 1 + z*z/n
    centre = (p + z*z/(2*n))/denom
    radius = (z/denom)*math.sqrt((p*(1-p)/n)+(z*z/(4*n*n)))
    return (max(0.0, centre-radius), min(1.0, centre+radius))


def summarise(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if not rows:
        raise ValueError('No evaluation rows')
    confusion = {true: {pred: 0 for pred in (*LABELS, 'unknown', 'error')} for true in LABELS}
    correct = successful = failed = degraded = 0
    by_error: Counter[str] = Counter()
    durations: list[float] = []
    for row in rows:
        true = str(row['ground_truth'])
        if true not in confusion:
            raise ValueError(f'Unknown label {true}')
        prediction = str(row.get('prediction') or 'error')
        if prediction not in confusion[true]:
            prediction = 'error'
        confusion[true][prediction] += 1
        is_error = bool(row.get('error_type'))
        failed += int(is_error)
        successful += int(not is_error)
        correct += int(not is_error and prediction == true)
        degraded += int(bool(row.get('degraded', False)))
        if is_error:
            by_error[str(row['error_type'])] += 1
        if isinstance(row.get('duration_ms'), (int, float)):
            durations.append(float(row['duration_ms']))
    n = len(rows)
    lower, upper = wilson_interval(correct, n)
    return {
        'evaluated': n,
        'correct': correct,
        'accuracy': correct/n,
        'accuracy_95pct_wilson': [lower, upper],
        'coverage': successful/n,
        'failed_cases': failed,
        'degraded_cases': degraded,
        'error_types': dict(sorted(by_error.items())),
        'avg_duration_ms': round(sum(durations)/len(durations), 2) if durations else None,
        'confusion_matrix': confusion,
        'classes': list(LABELS),
        'scoring': 'exact match; errors and missing predictions count as incorrect',
        'limitations': [
            'Dataset is synthetic; observations are not independent real-world network events.',
            'Generator v1 has deterministic class-separating telemetry; v2 includes stale or confounded telemetry but definitive simulated probes.',
            'A high score does not establish production network fault accuracy.',
            'Wilson interval is descriptive only given synthetic seeded data.',
        ],
    }


def write_reports(rows: Sequence[Mapping[str, Any]], output: Path, metadata: Mapping[str, Any]) -> tuple[Path, Path]:
    summary = dict(metadata)
    summary.update(summarise(rows))
    summary_file = output.with_suffix('.summary.json')
    confusion_file = output.with_suffix('.confusion.csv')
    summary_file.write_text(json.dumps(summary, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
    matrix = summary['confusion_matrix']
    with confusion_file.open('w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        columns = [*LABELS, 'unknown', 'error']
        w.writerow(['ground_truth', *columns])
        for label in LABELS:
            w.writerow([label, *[matrix[label][col] for col in columns]])
    return summary_file, confusion_file
