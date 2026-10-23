"""Offline latency analyzer tests; never contacts LLM, Redis or simulator."""
import importlib.util
import json
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location('analyze_latency', Path(__file__).resolve().parents[1]/'scripts'/'analyze_latency.py')
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


def row(i, duration, *, error=None, ok=True, fp='hash1', model='gpt-4.1-mini'):
    return dict(incident_id=f'INC-{i:04d}', duration_ms=duration, error_type=error,
                correct=ok, tool_calls=2, http_requests=5, dataset_sha256=fp,
                mode='openai', model=model)


def test_nearest_rank():
    assert mod.percentile([10, 20, 30, 40, 50], 0.95) == 50
    assert mod.percentile([10, 20, 30, 40, 50], 0.5) == 30


def test_summary_excludes_failed_latency_but_counts_errors():
    report = mod.summarise([row(1, 100), row(2, 200), row(3, 999, error='TimeoutError', ok=False)])
    assert report['samples'] == 3
    assert report['success_samples'] == 2
    assert report['failed_samples'] == 1
    assert report['latency_ms_success_only']['p95'] == 200
    assert report['avg_tool_calls'] == 2
    assert report['accuracy'] == 0.6667


def test_file_load_rejects_duplicates(tmp_path):
    f = tmp_path/'x.jsonl'
    f.write_text(json.dumps(row(1, 100))+'\n'+json.dumps(row(1, 200)))
    with pytest.raises(ValueError, match='Duplicate'):
        mod.read_rows(f)


def test_reject_nonfinite_duration(tmp_path):
    f = tmp_path/'x.jsonl'
    f.write_text(json.dumps(row(1, -1)))
    with pytest.raises(ValueError, match='duration_ms'):
        mod.read_rows(f)


def test_paired_compare_and_guard():
    before = [row(1, 100), row(2, 200)]
    after = [row(1, 80), row(2, 110)]
    report = mod.compare(before, after)
    assert report['paired_successful_cases'] == 2
    assert report['paired_p95_ms_before'] == 200
    assert report['paired_p95_ms_after'] == 110
    assert report['paired_p95_change_percent'] == -45
    with pytest.raises(ValueError, match='SHA256'):
        mod.compare(before, [row(1, 80, fp='bad'), row(2, 110, fp='bad')])
    with pytest.raises(ValueError, match='identical incident IDs'):
        mod.compare(before, [row(1, 80)])


def test_mixed_dataset_rejected():
    with pytest.raises(ValueError, match='Mixed dataset'):
        mod.summarise([row(1, 100), row(2, 200, fp='hash2')])
