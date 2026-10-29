from copy import deepcopy
import pytest
from evals.regression import capture, check


def output():
    return {'run': {'company_name': 'Example', 'domain': 'example.com', 'source_email': 'Original request'},
            'reports': [{'id': 'report', 'markdown': 'Fact [source](https://example.com/source)',
                         'email_subject': 'Discussion', 'email_body': 'Thank you for your request.',
                         'recipients': {'to': ['partner@example.invalid']}, 'send_email': False, 'save_kb': False}],
            'approvals': [{'report_id': 'report', 'status': 'approved'}],
            'evidence': [{'url': 'https://example.com/source'}]}


def test_approved_reference_is_immutable_and_changed_content_requires_review(tmp_path):
    original = output()
    baseline = capture(original, tmp_path / 'reference.json')
    assert check(baseline, original)['regression_passed']
    with pytest.raises(FileExistsError):
        capture(original, tmp_path / 'reference.json')
    candidate = deepcopy(original)
    candidate['reports'][0]['email_body'] = 'Different reply'
    result = check(baseline, candidate)
    assert result['structural_passed'] and result['content_review_required'] and not result['regression_passed']
    baseline['output']['run']['domain'] = 'changed.example'
    with pytest.raises(ValueError, match='checksum'):
        check(baseline, candidate)


def test_unapproved_outputs_cannot_become_accepted_references(tmp_path):
    candidate = output()
    candidate['approvals'][0]['status'] = 'pending'
    with pytest.raises(ValueError, match='approved'):
        capture(candidate, tmp_path / 'reference.json')


def test_regression_detects_source_replacement_unknown_urls_and_action_changes(tmp_path):
    original = output()
    baseline = capture(original, tmp_path / 'reference.json')
    candidate = deepcopy(original)
    candidate['run']['source_email'] = 'Rewritten request'
    candidate['reports'][0]['email_body'] += ' https://unsupported.example/'
    candidate['reports'][0]['send_email'] = True
    result = check(baseline, candidate)
    assert not result['checks']['same_input']
    assert not result['checks']['no_unsupported_urls']
    assert not result['checks']['same_recipients_and_actions']
    assert result['factual_accuracy'] == 'not_evaluated'
