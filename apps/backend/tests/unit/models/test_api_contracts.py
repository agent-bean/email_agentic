from datetime import datetime, UTC
import uuid

import pytest
from pydantic import TypeAdapter, ValidationError

from email_agentic.main import create_app
from email_agentic.models.api import ActionRow
from email_agentic.models.sources import SourceInput
from email_agentic.platform.config import Settings


def test_source_union_discriminates_kinds_without_losing_provider_fields():
    row = dict(id=uuid.uuid4(), owner="owner@example.invalid", provider="google",
               source_id="event", created_at=datetime.now(UTC))
    source = TypeAdapter(SourceInput).validate_python({**row, "kind": "meeting", "content": {
        "summary": "Review", "etag": "revision", "start": {"date": "2030-01-01"},
    }})
    assert source.content.start.date == "2030-01-01"
    assert source.content.model_dump()["etag"] == "revision"
    with pytest.raises(ValidationError):
        TypeAdapter(SourceInput).validate_python({**row, "kind": "unknown", "content": {}})


def test_publication_status_rejects_unknown_state():
    with pytest.raises(ValidationError):
        ActionRow(id=uuid.uuid4(), kind="email", status="delivered_maybe", provider_id=None, error_code=None)


def test_all_json_endpoints_declare_response_contracts():
    schema = create_app(Settings.model_construct(environment="test")).openapi()
    for path, methods in schema["paths"].items():
        if path == "/api/v1/files/{file_id}":
            continue  # This endpoint returns immutable binary bytes, not JSON.
        for method, operation in methods.items():
            if method not in {"get", "post", "put"}:
                continue
            responses = [value for status, value in operation["responses"].items() if status.startswith("2")]
            assert responses, (path, method)
            for response in responses:
                assert response["content"]["application/json"]["schema"], (path, method)
