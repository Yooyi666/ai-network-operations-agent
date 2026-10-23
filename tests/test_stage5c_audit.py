"""Tests for the standalone, offline Stage 5C audit."""
import importlib.util
from pathlib import Path

import pytest

AUDIT = Path(__file__).resolve().parents[1] / "scripts" / "audit_early_stop.py"
spec = importlib.util.spec_from_file_location("audit_early_stop", AUDIT)
audit_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit_module)


def item(incident, truth, guess, mode, ms=100.0, tools=4, applied=False):
    return {"incident_id":incident,"ground_truth":truth,"prediction":guess,
            "correct":truth==guess,"duration_ms":ms,"tool_calls":tools,
            "http_requests":tools+3,"dataset_sha256":"hash1","mode":"openai",
            "model":"gpt-4.1-mini","early_stop":mode,"early_stop_applied":applied}


def test_transitions():
    before={"INC-0001":item("INC-0001","a","a","off"),"INC-0002":item("INC-0002","b","bad","off")}
    after={"INC-0001":item("INC-0001","a","wrong","on",ms=40,tools=1,applied=True),"INC-0002":item("INC-0002","b","b","on",ms=60,tools=1,applied=True)}
    s, rows=audit_module.audit(before,after)
    assert s["transitions"]=={"both_correct":0,"regression":1,"recovery":1,"both_incorrect":0}
    assert s["accuracy_difference_pp"]==0
    assert s["early_stop_regressions_count"]==1
    assert rows[0]["latency_saved_ms"]==60


def test_rejects_mismatched_ids():
    b={"INC-0001":item("INC-0001","a","a","off")}
    a={"INC-0002":item("INC-0002","a","a","on")}
    with pytest.raises(ValueError,match="Unmatched"):
        audit_module.audit(b,a)


def test_rejects_mismatched_dataset():
    b={"INC-0001":item("INC-0001","a","a","off")}
    a={"INC-0001":item("INC-0001","a","a","on")}
    a["INC-0001"]["dataset_sha256"]="hash2"
    with pytest.raises(ValueError,match="dataset_sha256"):
        audit_module.audit(b,a)


def test_rejects_wrong_modes():
    b={"INC-0001":item("INC-0001","a","a","on")}
    a={"INC-0001":item("INC-0001","a","a","on")}
    with pytest.raises(ValueError,match="early_stop=off"):
        audit_module.audit(b,a)


def test_load_checks_duplicate_ids(tmp_path):
    f=tmp_path/"a.jsonl"
    import json
    line=json.dumps(item("INC-0001","a","a","off"))
    f.write_text(line+'\n'+line+'\n',encoding="utf-8")
    with pytest.raises(ValueError,match="Duplicate"):
        audit_module.load_rows(f)


def test_load_validates_correct_bool(tmp_path):
    f=tmp_path/"b.jsonl"
    import json
    d=item("INC-0001","a","a","off");d['correct']='True'
    f.write_text(json.dumps(d),encoding="utf-8")
    with pytest.raises(ValueError,match="Non-boolean"):
        audit_module.load_rows(f)
