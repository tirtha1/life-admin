"""
OpenTelemetry setup — traces → Tempo, metrics → Prometheus, logs → Loki.
Call setup_telemetry(service_name) once at service startup.
"""
import os
import logging
import structlog

from opentelemetry import trace, metrics
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk.resources import Resource

OTLP_ENDPOINT = os.environ.get("OTLP_ENDPOINT", "http://localhost:4317")
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")


def _configure_structlog(service_name: str) -> None:
    """Configure structlog for JSON output with trace context injection."""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            # Add service name to every log line
            structlog.processors.CallsiteParameterAdder(
                [structlog.processors.CallsiteParameter.FILENAME,
                 structlog.processors.CallsiteParameter.LINENO]
            ),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, LOG_LEVEL.upper(), logging.INFO)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def setup_telemetry(service_name: str) -> None:
    """
    Initialize OTel SDK. Call once at startup before importing instrumented libs.

    Args:
        service_name: Identifies this service in traces/metrics (e.g. "ingestion", "processor")
    """
    resource = Resource.create(
        {
            "service.name": service_name,
            "service.version": os.environ.get("APP_VERSION", "1.0.0"),
            "deployment.environment": os.environ.get("ENVIRONMENT", "development"),
        }
    )

    # ─── Traces → Tempo ───────────────────────────────────────────────────────
    tracer_provider = TracerProvider(resource=resource)
    otlp_span_exporter = OTLPSpanExporter(endpoint=OTLP_ENDPOINT, insecure=True)
    tracer_provider.add_span_processor(BatchSpanProcessor(otlp_span_exporter))
    trace.set_tracer_provider(tracer_provider)

    # ─── Metrics → Prometheus ─────────────────────────────────────────────────
    otlp_metric_exporter = OTLPMetricExporter(endpoint=OTLP_ENDPOINT, insecure=True)
    metric_reader = PeriodicExportingMetricReader(otlp_metric_exporter, export_interval_millis=15_000)
    meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
    metrics.set_meter_provider(meter_provider)

    # ─── Logs → structured JSON ───────────────────────────────────────────────
    _configure_structlog(service_name)

    # ─── Auto-instrumentation ─────────────────────────────────────────────────
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        FastAPIInstrumentor().instrument()
    except ImportError:
        pass

    try:
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
        SQLAlchemyInstrumentor().instrument()
    except ImportError:
        pass

    try:
        from opentelemetry.instrumentation.redis import RedisInstrumentor
        RedisInstrumentor().instrument()
    except ImportError:
        pass

    try:
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
        HTTPXClientInstrumentor().instrument()
    except ImportError:
        pass

    import structlog
    log = structlog.get_logger()
    log.info("Telemetry initialized", service=service_name, otlp_endpoint=OTLP_ENDPOINT)
