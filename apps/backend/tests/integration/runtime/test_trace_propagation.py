import uuid

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from email_agentic.platform import telemetry
from email_agentic.runtime.jobs import enqueue


@pytest.fixture
def tracing(monkeypatch):
    provider = TracerProvider()
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("propagation-test")
    monkeypatch.setattr("email_agentic.worker.tracer", lambda: tracer)
    yield tracer, exporter
    provider.shutdown()


async def test_enqueue_persists_only_w3c_trace_parent_and_preserves_dedupe(db, tracing):
    tracer, _ = tracing
    owner = "trace-owner"
    key = "trace-test:" + str(uuid.uuid4())
    with tracer.start_as_current_span("api.create"):
        parent = telemetry.current_trace_parent()
        async with db.transaction() as connection:
            await enqueue(connection, owner, "scan_email", None, key)
    # A later duplicate request must not change the original causal context.
    async with db.transaction() as connection:
        await enqueue(connection, owner, "scan_email", None, key)
    row = await db.one("SELECT trace_parent FROM jobs WHERE dedupe_key=%s", (key,))
    assert row["trace_parent"] == parent
    assert len(parent) == 55
