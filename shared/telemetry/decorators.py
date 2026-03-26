"""
OTel decorators for tracing and metrics.
"""
import time
import functools
from typing import Callable, Any

from opentelemetry import trace, metrics

_tracer = trace.get_tracer("life-admin")
_meter = metrics.get_meter("life-admin")

# Pre-create histograms
_duration_histograms: dict[str, Any] = {}


def traced(span_name: str | None = None):
    """
    Decorator: wraps the function in an OTel span.

    Usage:
        @traced("bill_extraction")
        async def extract_bill(email): ...
    """
    def decorator(func: Callable) -> Callable:
        name = span_name or func.__qualname__

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            with _tracer.start_as_current_span(name) as span:
                try:
                    result = await func(*args, **kwargs)
                    span.set_status(trace.StatusCode.OK)
                    return result
                except Exception as e:
                    span.set_status(trace.StatusCode.ERROR, str(e))
                    span.record_exception(e)
                    raise

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            with _tracer.start_as_current_span(name) as span:
                try:
                    result = func(*args, **kwargs)
                    span.set_status(trace.StatusCode.OK)
                    return result
                except Exception as e:
                    span.set_status(trace.StatusCode.ERROR, str(e))
                    span.record_exception(e)
                    raise

        import asyncio
        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper

    return decorator


def measure_duration(metric_name: str, unit: str = "s", description: str = ""):
    """
    Decorator: emits a histogram metric with execution duration.

    Usage:
        @measure_duration("extractor.duration_seconds")
        async def extract_bill(email): ...
    """
    def decorator(func: Callable) -> Callable:
        if metric_name not in _duration_histograms:
            _duration_histograms[metric_name] = _meter.create_histogram(
                name=metric_name,
                unit=unit,
                description=description or f"Duration of {func.__qualname__}",
            )
        histogram = _duration_histograms[metric_name]

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            start = time.monotonic()
            try:
                return await func(*args, **kwargs)
            finally:
                elapsed = time.monotonic() - start
                histogram.record(elapsed)

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            start = time.monotonic()
            try:
                return func(*args, **kwargs)
            finally:
                elapsed = time.monotonic() - start
                histogram.record(elapsed)

        import asyncio
        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper

    return decorator
