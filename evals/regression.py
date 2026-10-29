"""Private, offline regression references from owner-approved outputs, not factual golden truth."""
import argparse
import hashlib
import json
import os
from pathlib import Path

from evals.golden import canonical
from evals.scoring.score import normalize, source_links


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def content(output):
    report = output['reports'][0]
    return {key: report[key] for key in ('markdown', 'email_subject', 'email_body', 'recipients', 'send_email', 'save_kb')}


def source(output):
    return {key: output['run'].get(key) for key in
            ('company_name', 'domain', 'context', 'source_email', 'source_message', 'source_meeting')}


def capture(output, path):
    report = output['reports'][0]
    if not any(a['report_id'] == report['id'] and a['status'] == 'approved' for a in output['approvals']):
        raise ValueError('Latest report must be approved by its owner')
    baseline = {'version': 1, 'kind': 'owner_accepted_reference', 'output': output,
                'output_sha256': digest(output)}
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with path.open('x') as handle:
        os.chmod(path, 0o600)
        json.dump(baseline, handle, ensure_ascii=False, indent=2)
    return baseline


def check(baseline, candidate):
    expected = baseline['output']
    if baseline.get('kind') != 'owner_accepted_reference' or digest(expected) != baseline['output_sha256']:
        raise ValueError('Accepted reference checksum or kind is invalid')
    original, report = content(expected), content(candidate)
    evidence = {normalize(item['url']) for item in candidate.get('evidence', [])}
    cited = source_links(report['markdown'])
    unknown = (cited | source_links(report['email_body'])) - evidence
    markers = ('[DỮ LIỆU MẪU]', 'DỮ LIỆU GIẢ LẬP', '[TC-')
    checks = {
        'same_input': source(expected) == source(candidate),
        'report_and_email_present': all(isinstance(report[k], str) and report[k].strip()
                                        for k in ('markdown', 'email_subject', 'email_body')),
        'no_unsupported_urls': not unknown,
        'citation_count_not_reduced': len(cited & evidence) >= len(source_links(original['markdown'])),
        'no_dataset_markers_in_email': not any(marker.casefold() in report['email_body'].casefold()
                                               or marker.casefold() in report['email_subject'].casefold() for marker in markers),
        'same_recipients_and_actions': all(report[k] == original[k] for k in ('recipients', 'send_email', 'save_kb')),
    }
    identical = digest(report) == digest(original)
    return {'structural_passed': all(checks.values()), 'checks': checks,
            'accepted_content_unchanged': identical, 'content_review_required': not identical,
            'regression_passed': all(checks.values()) and identical,
            'factual_accuracy': 'not_evaluated', 'product_acceptance': 'not_evaluated',
            'reference_sha256': baseline['output_sha256'], 'candidate_sha256': digest(candidate)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    save = commands.add_parser('capture')
    save.add_argument('--export', type=Path, required=True)
    save.add_argument('--baseline', type=Path, required=True)
    run = commands.add_parser('check')
    run.add_argument('--baseline', type=Path, required=True)
    run.add_argument('--candidate', type=Path, required=True)
    run.add_argument('--result', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'capture':
        capture(json.loads(args.export.read_text()), args.baseline)
        print('Owner-approved reference captured privately; factual golden unchanged')
    else:
        result = check(json.loads(args.baseline.read_text()), json.loads(args.candidate.read_text()))
        args.result.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        args.result.write_text(json.dumps(result, indent=2) + '\n')
        args.result.chmod(0o600)
        print('Regression passed:', result['regression_passed'], '; content review required:', result['content_review_required'])
        if not result['regression_passed']:
            raise SystemExit(1)


if __name__ == '__main__':
    main()
