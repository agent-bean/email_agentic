from opentelemetry import trace
from opentelemetry.context import Context
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_client import Counter, Histogram

TOOLS = Counter("email_tool_calls", "Tool outcomes", ["tool", "outcome"])
JOBS = Counter("email_jobs", "Job outcomes", ["kind", "outcome"])
DURATION = Histogram("email_job_seconds", "Job duration", ["kind"])


def configure(service, endpoint=""):
    provider = TracerProvider(resource=Resource.create({"service.name": service}))
    if endpoint:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
    trace.set_tracer_provider(provider)
    return provider


def tracer():
    return trace.get_tracer("email_agentic")


def current_trace_parent():
    # Persist only W3C IDs, never baggage, request headers or private payloads.
    carrier = {}
    TraceContextTextMapPropagator().inject(carrier)
    return carrier.get("traceparent")


def job_trace_context(job):
    value = job.get("trace_parent")
    carrier = {"traceparent": value} if isinstance(value, str) and len(value) <= 512 else {}
    context = TraceContextTextMapPropagator().extract(carrier, context=Context())
    parent = trace.get_current_span(context).get_span_context()
    # Human approval can take days. Resume is a new trace linked to its trigger.
    if job["kind"] in {"resume", "approval_resume"}:
        return Context(), [trace.Link(parent)] if parent.is_valid else []
    return context, []
