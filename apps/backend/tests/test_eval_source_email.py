import hashlib
import json

import httpx
import pytest

from evals.runner.collect import collect, prepare_cases
from evals.runner.source_email import bind_source_email


def case():
    return {"case_id": "TC-02", "dataset_version": "2", "fixture_status": "requires_case_source",
            "input": {"company_name": "Company", "domain": "example.com", "context": "Internal request"}}


def bundle():
    return {"dataset_version": "2", "source_document": {"slide": 5, "sha256": "source-hash"},
            "cases": {"TC-02": {
                "research_identity": {"company_name": "Company", "domain": "example.com"},
                "email": {"sender": "Contact", "company": "Company", "website": "https://example.com/new",
                          "website_original": "https://example.com/old", "body": "  Exact customer sentence.\n"},
                "supplements": {"attachment": {"origin": "execution_setup", "file": "reference.pdf"}},
            }}}


def test_case_source_preserves_body_and_corrected_url_without_transport_or_supplement_text():
    original = case()
    effective, provenance = bind_source_email(original, bundle())
    text = effective["input"]["source_email"]
    assert text == "Từ: Contact – Company\nWebsite: https://example.com/new\n\n  Exact customer sentence.\n"
    assert effective["input"]["context"] == "Internal request"
    assert "source_email" not in original["input"]
    assert provenance["authority"] == "assignment_slide"
    assert provenance["source_email_sha256"] == hashlib.sha256(text.encode()).hexdigest()
    assert provenance["email"]["website_original"] == "https://example.com/old"
    assert "reference.pdf" not in text and "From:" not in text and "Subject:" not in text


@pytest.mark.parametrize("field", ["sender", "company", "website", "body"])
def test_incomplete_case_source_is_rejected_instead_of_using_context(field):
    source = bundle()
    source["cases"]["TC-02"]["email"].pop(field)
    with pytest.raises(ValueError, match="requires"):
        bind_source_email(case(), source)


@pytest.mark.parametrize("change", ["version", "company", "case"])
def test_source_version_and_company_must_match_selected_case(change):
    source = bundle()
    if change == "version":
        source["dataset_version"] = "1"
    elif change == "company":
        source["cases"]["TC-02"]["research_identity"]["domain"] = "other.example"
    else:
        source["cases"] = {}
    with pytest.raises(ValueError):
        bind_source_email(case(), source)


def test_prepare_cases_saves_effective_input_and_private_source(tmp_path):
    case_path = tmp_path / "case.json"
    case_path.write_text(json.dumps(case()))
    inputs = tmp_path / "case-inputs.json"
    inputs.write_text(json.dumps(bundle()))
    output = tmp_path / "results"
    effective = prepare_cases([case_path], inputs, output)
    saved = json.loads((output / "tc-02-input.json").read_text())
    source = json.loads((output / "tc-02-source.json").read_text())
    assert saved == effective[0]
    assert source["source_email"] == saved["input"]["source_email"]
    assert (output / "tc-02-source.json").stat().st_mode & 0o777 == 0o600


def test_missing_or_legacy_source_fails_before_creating_outputs(tmp_path):
    case_path = tmp_path / "case.json"
    case_path.write_text(json.dumps(case()))
    with pytest.raises(FileNotFoundError):
        prepare_cases([case_path], tmp_path / "missing.json", tmp_path / "results")
    old = case()
    old["fixture_status"] = "requires_fixture_binding"
    case_path.write_text(json.dumps(old))
    with pytest.raises(ValueError, match="Legacy Gmail"):
        prepare_cases([case_path], tmp_path / "missing.json", tmp_path / "results")
    assert not (tmp_path / "results").exists()


def test_collector_posts_bound_email_separately_and_checks_exact_round_trip(tmp_path):
    prepared, _ = bind_source_email(case(), bundle())

    def respond(request):
        if request.method == "POST":
            assert json.loads(request.content) == prepared["input"]
            return httpx.Response(202, json={"id": "run-id"})
        return httpx.Response(200, json={
            "run": {**prepared["input"], "status": "draft_ready"}, "actions": [],
            "reports": [{"send_email": False, "save_kb": False, "quality": {}}],
        })

    with httpx.Client(transport=httpx.MockTransport(respond), base_url="http://127.0.0.1:8000") as client:
        result = collect(client, prepared, tmp_path, False, 1)
    assert result["dataset_version"] == "2" and result["status"] == "draft_ready"
    assert result["source_email_sha256"] == hashlib.sha256(prepared["input"]["source_email"].encode()).hexdigest()


def test_unbound_case_cannot_be_submitted_to_api(tmp_path):
    with pytest.raises(ValueError, match="authoritative"):
        collect(None, case(), tmp_path, False, 1)
