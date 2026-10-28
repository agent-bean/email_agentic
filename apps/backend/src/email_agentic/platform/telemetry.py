from opentelemetry import trace
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
