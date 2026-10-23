"""Evaluation correctness and privacy boundaries; no paid model calls."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest

from netops_agent.evaluation import (
    LABELS, baseline_predict, load_labelled_cases, public_matches_private,
    summarise, wilson_interval, write_reports,
)
from netops_agent.simulator import generate_cases


def test_baseline_predict_on_public_metrics_200_cases():
    cases = generate_cases(seed=20261022, per_class=40)
    # Read ONLY the same public telemetry that the simulator endpoint exposes.
    for case in cases:
        public = {'telemetry': {'incident_id': case['incident_id'], 'telemetry': case['telemetry']}}
        assert baseline_predict(public) == case['ground_truth']


def test_wilson_bounds_and_failures():
    assert wilson_interval(0, 0) == (0.0, 1.0)
    lower, upper = wilson_interval(87, 100)
    assert 0 < lower < 0.87 < upper < 1
    with pytest.raises(ValueError):
        wilson_interval(101, 100)


def test_failed_cases_count_in_denominator_and_confusion():
    rows = [
        {'ground_truth': LABELS[0], 'prediction': LABELS[0], 'duration_ms': 10},
        {'ground_truth': LABELS[1], 'prediction': None, 'error_type': 'TimeoutError', 'duration_ms': 20},
        {'ground_truth': LABELS[2], 'prediction': LABELS[1], 'duration_ms': 30},
    ]
    s = summarise(rows)
    assert s['evaluated'] == 3 and s['correct'] == 1
    assert s['accuracy'] == pytest.approx(1/3)
    assert s['coverage'] == pytest.approx(2/3)
    assert s['confusion_matrix'][LABELS[1]]['error'] == 1
    assert s['error_types'] == {'TimeoutError': 1}


def test_dataset_hash_identity_and_private_labels(tmp_path: Path):
    cases = generate_cases(seed=13, per_class=1)
    f = tmp_path/'cases.jsonl'
    f.write_text('\n'.join(json.dumps(c) for c in cases)+'\n', encoding='utf-8')
    loaded, digest = load_labelled_cases(f)
    assert len(loaded) == 5 and len(digest) == 64
    assert public_matches_private({'incident_id': loaded[0]['incident_id'], 'telemetry': loaded[0]['telemetry']}, loaded[0])
    wrong = dict(loaded[0]['telemetry'], cpu_pct=-1000)
    assert not public_matches_private({'incident_id': loaded[0]['incident_id'], 'telemetry': wrong}, loaded[0])


def test_csv_json_reports(tmp_path: Path):
    out = tmp_path/'run.jsonl'
    report, matrix = write_reports([{'ground_truth': LABELS[0], 'prediction': LABELS[0]}], out, {'model':'baseline'})
    assert report.is_file() and matrix.is_file()
    assert json.loads(report.read_text())['accuracy'] == 1
    assert matrix.read_text().splitlines()[0].startswith('ground_truth,')


def test_preflight_detects_wrong_dataset():
    from scripts.evaluate import verify_dataset
    case = generate_cases(seed=31, per_class=1)[0]

    def handler(request: httpx.Request):
        payload = {'incident_id': case['incident_id'], 'telemetry': dict(case['telemetry'], cpu_pct=-1)}
        return httpx.Response(200, json=payload)

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url='http://simulator.test') as http:
            with pytest.raises(RuntimeError, match='DATASET MISMATCH'):
                await verify_dataset(http, [case])
    asyncio.run(run())


def test_resume_must_match_metadata(tmp_path: Path):
    from scripts.evaluate import load_completed
    out = tmp_path/'run.jsonl'
    row = {'incident_id':'INC-0001', 'dataset_sha256':'abc', 'mode':'baseline', 'model':'baseline'}
    out.write_text(json.dumps(row)+'\n', encoding='utf-8')
    assert list(load_completed(out, 'abc', 'baseline', 'baseline', True)) == ['INC-0001']
    with pytest.raises(ValueError, match='different dataset'):
        load_completed(out, 'changed', 'baseline', 'baseline', True)
    with pytest.raises(ValueError, match='Result file exists'):
        load_completed(out, 'abc', 'baseline', 'baseline', False)
