from collections import Counter

import pytest

from netops_agent.simulator import ROOT_CAUSES, generate_cases


def test_200_balanced_and_unique_incidents():
    cases = generate_cases()
    assert len(cases) == 200
    assert len({c["incident_id"] for c in cases}) == 200
    assert Counter(c["ground_truth"] for c in cases) == {cause: 40 for cause in ROOT_CAUSES}


def test_reproducible_generation():
    assert generate_cases() == generate_cases()
    assert generate_cases(seed=42) != generate_cases(seed=43)


def test_probes_and_telemetry_available():
    for item in generate_cases():
        assert len(item["logs"]) >= 3
        assert "ping" in item["probes"]
        assert "bgp_status" in item["probes"]
        assert "rtt_ms" in item["telemetry"]


def test_invalid_dataset_size():
    with pytest.raises(ValueError):
        generate_cases(per_class=0)


def test_device_id_does_not_encode_ground_truth():
    cases = generate_cases()
    device_labels = {}
    for case in cases:
        device_labels.setdefault(case["device_id"], set()).add(case["ground_truth"])
    assert all(len(labels) >= 3 for labels in device_labels.values())
