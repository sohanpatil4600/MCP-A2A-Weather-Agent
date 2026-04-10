from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
import json
import time
import uuid
from collections import defaultdict


@dataclass
class TraceContext:
    """Trace context for correlating logs across service boundaries."""
    trace_id: str = field(default_factory=lambda: f"trace_{uuid.uuid4().hex[:16]}")
    span_id: str = field(default_factory=lambda: f"span_{uuid.uuid4().hex[:16]}")
    parent_span_id: str | None = None
    correlation_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "correlation_id": self.correlation_id,
        }


@dataclass
class StructuredEvent:
    """Structured log event for reliable parsing and correlation."""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    level: str = "INFO"
    event_type: str = "generic"
    message: str = ""
    trace_context: TraceContext = field(default_factory=TraceContext)
    latency_ms: float | None = None
    request_size_bytes: int | None = None
    response_size_bytes: int | None = None
    error: str | None = None
    error_code: int | None = None
    service: str = "unknown"
    resource: str = ""
    attributes: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        payload = {
            "timestamp": self.timestamp,
            "level": self.level,
            "event_type": self.event_type,
            "message": self.message,
            "trace": self.trace_context.to_dict(),
            "latency_ms": self.latency_ms,
            "request_size_bytes": self.request_size_bytes,
            "response_size_bytes": self.response_size_bytes,
            "error": self.error,
            "error_code": self.error_code,
            "service": self.service,
            "resource": self.resource,
            "attributes": self.attributes,
        }
        return json.dumps(payload)


class LatencyBucket:
    """Tracks latency in configurable buckets for SLO metrics."""
    def __init__(self, boundaries_ms: list[float] | None = None) -> None:
        self.boundaries_ms = boundaries_ms or [10, 50, 100, 500, 1000, 5000]
        self.buckets: dict[str, int] = defaultdict(int)

    def record(self, latency_ms: float) -> None:
        bucket_name = "inf"
        for boundary in self.boundaries_ms:
            if latency_ms <= boundary:
                bucket_name = f"{int(boundary)}ms"
                break
        self.buckets[bucket_name] += 1

    def to_dict(self) -> dict[str, int]:
        return dict(self.buckets)


class MetricsCollector:
    """Collects operational metrics for SLO tracking."""

    def __init__(self) -> None:
        self.counters: dict[str, int] = defaultdict(int)
        self.gauges: dict[str, float] = {}
        self.latency_percents: dict[str, LatencyBucket] = {}
        self.success_count = 0
        self.failure_count = 0
        self.retry_count = 0
        self.breaker_open_count = 0

    def increment_counter(self, name: str, value: int = 1) -> None:
        self.counters[name] += value

    def set_gauge(self, name: str, value: float) -> None:
        self.gauges[name] = value

    def record_latency(self, service_name: str, latency_ms: float) -> None:
        if service_name not in self.latency_percents:
            self.latency_percents[service_name] = LatencyBucket()
        self.latency_percents[service_name].record(latency_ms)

    def record_success(self) -> None:
        self.success_count += 1

    def record_failure(self) -> None:
        self.failure_count += 1

    def record_retry(self) -> None:
        self.retry_count += 1

    def record_breaker_open(self) -> None:
        self.breaker_open_count += 1

    def success_rate(self) -> float:
        total = self.success_count + self.failure_count
        if total == 0:
            return 1.0
        return self.success_count / total

    def to_dict(self) -> dict[str, Any]:
        return {
            "counters": dict(self.counters),
            "gauges": self.gauges,
            "success_rate": self.success_rate(),
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "retry_count": self.retry_count,
            "breaker_open_count": self.breaker_open_count,
            "latency_buckets": {
                service: bucket.to_dict()
                for service, bucket in self.latency_percents.items()
            },
        }


class ObservabilityContext:
    """Central observability context for tracing and metrics."""

    def __init__(self) -> None:
        self.current_trace = TraceContext()
        self.metrics = MetricsCollector()
        self.event_log: list[StructuredEvent] = []

    def new_trace(self) -> TraceContext:
        self.current_trace = TraceContext()
        return self.current_trace

    def new_span(self, parent_span_id: str | None = None) -> TraceContext:
        span = TraceContext(
            trace_id=self.current_trace.trace_id,
            correlation_id=self.current_trace.correlation_id,
            parent_span_id=parent_span_id or self.current_trace.span_id,
        )
        return span

    def emit_event(self, event: StructuredEvent) -> None:
        self.event_log.append(event)

    def emit_log(
        self,
        level: str = "INFO",
        event_type: str = "generic",
        message: str = "",
        service: str = "unknown",
        resource: str = "",
        latency_ms: float | None = None,
        error: str | None = None,
        error_code: int | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> None:
        event = StructuredEvent(
            level=level,
            event_type=event_type,
            message=message,
            trace_context=self.current_trace,
            latency_ms=latency_ms,
            error=error,
            error_code=error_code,
            service=service,
            resource=resource,
            attributes=attributes or {},
        )
        self.emit_event(event)

    def get_event_log_json(self) -> str:
        lines = [event.to_json() for event in self.event_log]
        return "\n".join(lines)

    def get_metrics_json(self) -> str:
        return json.dumps(self.metrics.to_dict(), indent=2)
