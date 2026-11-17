"""Shared pytest setup.

- tests/unit:        pure logic, no database or network (fast).
- tests/integration: real HTTP through FastAPI into a real Postgres 18
                     (testcontainers, or TEST_DATABASE_URL in CI).

In-memory OpenTelemetry providers are installed here, before any `app.*` import.
setup_telemetry() keeps providers that already exist, so tests can inspect every span,
metric and log the app emits through the `telemetry` fixture.
"""

import logging
import os
from collections.abc import Iterator
from typing import Any

import pytest
from opentelemetry import metrics, trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import InMemoryLogRecordExporter, SimpleLogRecordProcessor
from opentelemetry.sdk.metrics import Counter, Histogram, MeterProvider
from opentelemetry.sdk.metrics.export import AggregationTemporality, InMemoryMetricReader
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

os.environ.setdefault("APP_ENV", "test")

span_exporter = InMemorySpanExporter()
log_exporter = InMemoryLogRecordExporter()
metric_reader = InMemoryMetricReader(
    # Delta: each collect returns only what happened since the previous one.
    preferred_temporality={
        Counter: AggregationTemporality.DELTA,
        Histogram: AggregationTemporality.DELTA,
    }
)
_tracer_provider = TracerProvider()
_tracer_provider.add_span_processor(SimpleSpanProcessor(span_exporter))
trace.set_tracer_provider(_tracer_provider)
metrics.set_meter_provider(MeterProvider(metric_readers=[metric_reader]))
_logger_provider = LoggerProvider()
_logger_provider.add_log_record_processor(SimpleLogRecordProcessor(log_exporter))
set_logger_provider(_logger_provider)


class Telemetry:
    def spans(self) -> tuple[ReadableSpan, ...]:
        return span_exporter.get_finished_spans()

    def logs(self) -> list[Any]:
        return [data.log_record for data in log_exporter.get_finished_logs()]

    def metrics(self) -> dict[str, list[Any]]:
        """Collect once: {metric name: [data points]} since the previous collect."""
        data = metric_reader.get_metrics_data()
        points: dict[str, list[Any]] = {}
        for resource_metrics in data.resource_metrics if data else []:
            for scope_metrics in resource_metrics.scope_metrics:
                for metric in scope_metrics.metrics:
                    points.setdefault(metric.name, []).extend(metric.data.data_points)
        return points


@pytest.fixture
def telemetry() -> Iterator[Telemetry]:
    """Start from empty exporters; INFO logs are enabled for the duration of the test."""
    from app.core.logging import configure_logging

    configure_logging(logging.INFO)
    span_exporter.clear()
    log_exporter.clear()
    metric_reader.get_metrics_data()  # drain
    yield Telemetry()
    configure_logging()
