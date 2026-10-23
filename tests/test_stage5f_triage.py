import pytest
from netops_agent.triage_decision import decide_disposition
from scripts.analyze_guard_coverage import summarize_guard


def verification(status, causes, review):
    return {'status': status, 'live_confirmed_causes': causes, 'review_required': review}


def test_supported_single_signature_is_accepted_without_remediation():
    d = decide_disposition({'root_cause': 'dns_resolution_failure'},
                           verification('supported',['dns_resolution_failure'],False))
    assert d['accepted_root_cause'] == 'dns_resolution_failure'
    assert d['review_required'] is False
    assert d['automatic_remediation_allowed'] is False


def test_contradicted_recheck_is_abstention_preserves_llm_guess():
    d = decide_disposition({'root_cause': 'interface_congestion'},
                           verification('contradicted',['dns_resolution_failure'],True))
    assert d['status'] == 'needs_human_review'
    assert d['accepted_root_cause'] is None
    assert d['provisional_root_cause'] == 'interface_congestion'


@pytest.mark.parametrize('status,causes', [('unverified',[]),
                ('ambiguous',['dns_resolution_failure','cpu_saturation'])])
def test_missing_or_conflicting_evidence_requires_review(status,causes):
    assert decide_disposition({'root_cause':'cpu_saturation'},
                              verification(status,causes,True))['accepted_root_cause'] is None


def test_fake_supported_flag_does_not_bypass_guard():
    d = decide_disposition({'root_cause': 'cpu_saturation'},
                           verification('supported',['dns_resolution_failure'],False))
    assert d['review_required'] is True


def test_summary_reports_coverage_and_does_not_count_review_as_success():
    rows = [
        {'correct':True,'prediction':'dns_resolution_failure','ground_truth':'dns_resolution_failure',
         'diagnosis_verification':{},'triage_decision':{'status':'accepted_in_synthetic_lab','accepted_root_cause':'dns_resolution_failure'}},
        {'correct':False,'prediction':'cpu_saturation','ground_truth':'dns_resolution_failure',
         'diagnosis_verification':{},'triage_decision':{'status':'needs_human_review','accepted_root_cause':None}},
        {'correct':False,'prediction':'interface_congestion','ground_truth':'dns_resolution_failure',
         'diagnosis_verification':{},'triage_decision':{'status':'accepted_in_synthetic_lab','accepted_root_cause':'interface_congestion'}},
    ]
    stats = summarize_guard(rows)
    assert stats['autonomous_coverage'] == 0.6667
    assert stats['selective_accuracy'] == 0.5
    assert stats['overall_auto_correct_fraction'] == 0.3333
    assert stats['incorrect_accepted'] == 1


def test_summary_rejects_missing_guard():
    with pytest.raises(ValueError):
        summarize_guard([{'correct':True}])
