import uuid
from types import SimpleNamespace

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from email_agentic.platform import telemetry
from email_agentic.runtime.jobs import enqueue
from email_agentic.worker import Worker


@pytest.fixture
def tracing(monkeypatch):
    provider = TracerProvider()
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("propagation-test")
    monkeypatch.setattr("email_agentic.worker.tracer", lambda: tracer)
    yield tracer, exporter
    provider.shutdown()


@pytest.mark.parametrize("kind", ["research", "resume", "approval_resume"])
async def test_worker_restores_queue_context_before_creating_child_task(tracing, kind):
    tracer, exporter = tracing
    with tracer.start_as_current_span("request") as request:
        parent = telemetry.current_trace_parent()
        request_context = request.get_span_context()

    finished = []

    async def finish(job):
        finished.append(job["id"])

    worker = Worker(SimpleNamespace(jobs=SimpleNamespace(finish=finish)), None)

    async def handle(job):
        with tracer.start_as_current_span("tool.read"):
            pass

    worker.handle = handle
    job = {"id": uuid.uuid4(), "kind": kind, "attempt": 1, "trace_parent": parent}
    await worker.process(job)
    spans = {span.name: span for span in exporter.get_finished_spans()}
    worker_span = spans["job." + kind]
    assert finished == [job["id"]]
    assert spans["tool.read"].parent.span_id == worker_span.context.span_id
    assert spans["tool.read"].context.trace_id == worker_span.context.trace_id
    if kind == "research":
        assert worker_span.parent.span_id == request_context.span_id
        assert worker_span.parent.is_remote
        assert worker_span.context.trace_id == request_context.trace_id
    else:
        assert worker_span.parent is None
        assert worker_span.context.trace_id != request_context.trace_id
        assert len(worker_span.links) == 1
        assert worker_span.links[0].context.span_id == request_context.span_id
        assert worker_span.links[0].context.trace_id == request_context.trace_id
        assert worker_span.links[0].context.is_remote


@pytest.mark.parametrize("value", [None, "", "not-a-trace", "x" * 513, 123])
def test_invalid_persisted_context_never_breaks_work_or_inherits_ambient_request(tracing, value):
    tracer, _ = tracing
    with tracer.start_as_current_span("unrelated"):
        context, links = telemetry.job_trace_context({"kind": "research", "trace_parent": value})
    assert not trace.get_current_span(context).get_span_context().is_valid
    assert not links


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
