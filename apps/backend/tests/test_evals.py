import hashlib
import json
from datetime import datetime, UTC
import pytest
from evals.golden import Golden, Fact, digest, load_locked, validate_sources
from evals.scoring.score import score


def test_golden_refuses_unreviewed_and_modified_snapshot(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("A controlled unit-test source, not company data.")
    golden = Golden(
        case_id="TC-01",
        version="1",
        company_name="Example",
        domain="example.com",
        reference_time=datetime.now(UTC),
        source_mode="frozen",
        status="draft",
    )
    with pytest.raises(ValueError):
        validate_sources(golden, tmp_path)
    golden.facts = [
        Fact(
            id="f1",
            statement="Controlled fact",
            source_file="source.txt",
            source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
            locator="line 1",
        )
    ]
    golden.reviewer = "Human test reviewer"
    golden.readiness_checklist = ["identity"]
    golden.status = "locked"
    document = {"golden": golden.model_dump(mode="json")}
    document["sha256"] = digest(document["golden"])
    document["review_sha256"] = digest({**document["golden"], "status": "reviewed"})
    path = tmp_path / "golden.json"
    path.write_text(json.dumps(document))
    assert load_locked(path)[0].case_id == "TC-01"
    source.write_text("changed")
    with pytest.raises(ValueError, match="checksum"):
        load_locked(path)


def test_score_does_not_claim_accuracy_without_bound_manual_review():
    golden = Golden(
        case_id="TC-01",
        version="1",
        company_name="Example",
        domain="example.com",
        reference_time=datetime.now(UTC),
        source_mode="live",
        status="locked",
        reviewer="Reviewer",
        facts=[
            Fact(
                id="f1",
                statement="Controlled fact",
                source_file="source",
                source_sha256="0" * 64,
                locator="line 1",
            )
        ],
        readiness_checklist=["identity"],
    )
    output = {
        "run": {
            "company_name": "Example",
            "domain": "example.com",
            "created_at": datetime.now(UTC).isoformat(),
            "elapsed_seconds": 1,
            "config": {"target_seconds": 42},
        },
        "reports": [{"markdown": "Text [source](https://example.com)"}],
        "evidence": [{"url": "https://example.com"}],
    }
    result = score(output, golden, "checksum")
    assert result["eligible"] is False
    assert result["completeness"] is None
    assert result["source_target_met"] is False


def test_manual_review_is_bound_to_exact_output():
    from evals.golden import canonical

    golden = Golden(
        case_id="TC-01",
        version="1",
        company_name="Example",
        domain="example.com",
        reference_time=datetime.now(UTC),
        source_mode="live",
        status="locked",
        reviewer="Human reviewer",
        facts=[
            Fact(
                id="f1",
                statement="Controlled fact",
                source_file="source",
                source_sha256="0" * 64,
                locator="line 1",
            )
        ],
        readiness_checklist=["identity"],
    )
    output = {
        "run": {
            "company_name": "Example",
            "domain": "example.com",
            "created_at": datetime.now(UTC).isoformat(),
            "elapsed_seconds": 2,
            "config": {"target_seconds": 42},
        },
        "reports": [{"markdown": "Controlled report"}],
        "evidence": [],
    }
    review = {
        "reviewer": "Human reviewer",
        "output_sha256": hashlib.sha256(canonical(output)).hexdigest(),
        "golden_sha256": "locked-hash",
        "facts": {"f1": "correct_with_evidence"},
        "readiness": {"identity": True},
    }
    result = score(output, golden, "locked-hash", review)
    assert result["eligible"] is True and result["completeness"] == 1
    independent = {**review, "reviewer_kind": "independent_agent"}
    assert score(output, golden, "locked-hash", independent)["eligible"] is False
    assert result["passed"] is False  # No cited sources; a fact review alone is insufficient.
    output["reports"][0]["markdown"] = "Changed after review"
    assert score(output, golden, "locked-hash", review)["eligible"] is False


@pytest.mark.parametrize("email", [
    "See https://outside.invalid/source.",
    "See [source](https://outside.invalid/source).",
    "See <https://outside.invalid/source>.",
])
def test_scoring_checks_email_urls_and_counts_bare_report_links(email):
    golden = Golden(case_id="TC-01", version="1", company_name="Example", domain="example.com",
                    reference_time=datetime.now(UTC), source_mode="live", status="draft")
    output = {
        "run": {"company_name": "Example", "domain": "example.com",
                "created_at": datetime.now(UTC).isoformat(), "config": {"target_seconds": 42}},
        "reports": [{"markdown": "Source https://example.com/source_(one).", "email_body": email}],
        "evidence": [{"url": "https://example.com/source_(one)"}],
    }
    result = score(output, golden, "checksum")
    assert result["cited_supported_urls"] == 1
    assert result["unsupported_urls"] == ["https://outside.invalid/source"]
    assert result["eligible"] is False and result["completeness"] is None


@pytest.fixture
def reviewed_timed_output():
    from evals.golden import canonical

    golden = Golden(
        case_id="TC-01", version="1", company_name="Example", domain="example.com",
        reference_time=datetime(2026, 10, 29, tzinfo=UTC), source_mode="live", status="locked",
        reviewer="Human reviewer",
        facts=[Fact(id="f1", statement="Controlled fact", source_file="source",
                    source_sha256="0" * 64, locator="line 1")],
        readiness_checklist=["identity"],
    )
    urls = [f"https://example.com/document/{index}" for index in range(12)]
    output = {
        "run": {
            "company_name": "Example", "domain": "example.com",
            "created_at": "2026-10-29T00:00:00+00:00", "elapsed_seconds": 20,
            "config": {"target_seconds": 42, "timing": {
                "version": 1, "received_at": "2026-10-29T00:00:00+00:00",
                "identity_wait_started_at": "2026-10-29T00:00:05+00:00",
                "identity_confirmed_at": "2026-10-29T00:01:05+00:00",
            }},
        },
        "reports": [{"markdown": "\n".join(urls), "quality": {
            "timing_basis": "active_processing", "markdown_ready_at": "2026-10-29T00:01:40+00:00",
            "prd_elapsed_seconds": 1, "prd_time_target_met": True,
        }}],
        "evidence": [{"url": url} for url in urls],
    }

    def evaluate():
        review = {
            "reviewer": "Human reviewer", "output_sha256": hashlib.sha256(canonical(output)).hexdigest(),
            "golden_sha256": "locked-hash", "facts": {"f1": "correct_with_evidence"},
            "readiness": {"identity": True}, "distinct_sources_verified": True,
            "news_freshness_passed": True,
        }
        return score(output, golden, "locked-hash", review)

    return output, evaluate


def test_prd_score_counts_queue_and_excludes_only_recorded_identity_wait(reviewed_timed_output):
    output, evaluate = reviewed_timed_output
    result = evaluate()
    assert result["passed"] is True
    assert result["prd_elapsed_seconds"] == 40  # 100 wall seconds minus 60 waiting for human.
    assert result["identity_wait_seconds"] == 60
    assert result["elapsed_seconds"] == 20
    output["reports"][0]["quality"]["markdown_ready_at"] = "2026-10-29T00:01:43+00:00"
    result = evaluate()
    assert result["prd_elapsed_seconds"] == 43
    assert result["time_target_met"] is False
    assert result["passed"] is False  # Active time and runtime pass flag cannot override timestamps.


@pytest.mark.parametrize("missing", ["timing", "identity_confirmed_at", "markdown_ready_at"])
def test_prd_score_requires_complete_timestamps(reviewed_timed_output, missing):
    output, evaluate = reviewed_timed_output
    if missing == "timing":
        del output["run"]["config"]["timing"]
    elif missing == "markdown_ready_at":
        del output["reports"][0]["quality"][missing]
    else:
        del output["run"]["config"]["timing"][missing]
    result = evaluate()
    assert result["eligible"] is True  # Bound human fact review remains usable.
    assert result["completeness"] == 1
    assert result["prd_elapsed_seconds"] is None
    assert result["time_target_met"] is None
    assert result["passed"] is False


@pytest.mark.parametrize("confirmed", [
    "invalid", "2026-10-29T00:01:05", "2026-10-28T23:59:00+00:00", "2026-10-29T00:02:00+00:00",
])
def test_prd_score_rejects_invalid_or_inconsistent_timing(reviewed_timed_output, confirmed):
    output, evaluate = reviewed_timed_output
    output["run"]["config"]["timing"]["identity_confirmed_at"] = confirmed
    result = evaluate()
    assert result["prd_elapsed_seconds"] is None
    assert result["passed"] is False
