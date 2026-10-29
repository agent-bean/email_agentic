import hashlib
import json

import pytest

from evals.review_bundle import build


def test_review_reader_checks_sources_escapes_content_and_never_changes_golden(tmp_path):
    source = tmp_path / "source.json"
    source.write_text("<script>unsafe()</script>")
    golden = tmp_path / "v2.json"
    value = {
        "golden": {
            "case_id": "TC-01",
            "version": "2",
            "company_name": "Example",
            "domain": "example.com",
            "reference_time": "2026-10-29T00:00:00Z",
            "source_mode": "live",
            "status": "draft",
            "reviewer": None,
            "facts": [
                {
                    "id": "fact-1",
                    "statement": "Fact to review",
                    "source_file": "source.json",
                    "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                    "locator": "body",
                }
            ],
            "readiness_checklist": ["evidence"],
        }
    }
    golden.write_text(json.dumps(value))
    before = golden.read_bytes()
    page = build([golden])
    assert "&lt;script&gt;unsafe()&lt;/script&gt;" in page and "<script>" not in page
    assert "chờ review" in page and golden.read_bytes() == before
    source.write_text("Changed source")
    with pytest.raises(ValueError, match="checksum"):
        build([golden])
