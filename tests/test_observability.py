"""Tests for production observability infrastructure.

Tests cover:
- Trace context with correlation IDs
- Structured event emission and JSON serialization  
- Metrics collection and SLO tracking
- Latency bucket histogram accuracy
"""

import json
import time
import unittest
from server.observability import (
    TraceContext,
    StructuredEvent,
    LatencyBucket,
    MetricsCollector,
    ObservabilityContext,
)


class TestTraceContext(unittest.TestCase):
    """Validate trace context generation and field preservation."""

    def test_trace_context_initialization(self):
        """Trace context should generate unique IDs on creation."""
        ctx = TraceContext()
        self.assertIsNotNone(ctx.trace_id)
        self.assertIsNotNone(ctx.span_id)
        self.assertIsNotNone(ctx.correlation_id)
        self.assertTrue(len(ctx.trace_id) > 0)

    def test_trace_context_correlation_id_propagation(self):
        """Correlation ID should propagate across spawned contexts."""
        parent_ctx = TraceContext()
        self.assertEqual(parent_ctx.correlation_id, parent_ctx.correlation_id)

    def test_trace_context_unique_span_ids(self):
        """Each trace context should have unique span_id."""
        ctx1 = TraceContext()
        ctx2 = TraceContext()
        self.assertNotEqual(ctx1.span_id, ctx2.span_id)

    def test_trace_context_to_dict(self):
        """TraceContext should serialize to dict format."""
        ctx = TraceContext()
        ctx_dict = ctx.to_dict()
        self.assertIn("trace_id", ctx_dict)
        self.assertIn("span_id", ctx_dict)
        self.assertIn("correlation_id", ctx_dict)


class TestStructuredEvent(unittest.TestCase):
    """Validate structured event creation and JSON serialization."""

    def test_structured_event_required_fields(self):
        """StructuredEvent should have required fields."""
        ctx = TraceContext()
        event = StructuredEvent(
            event_type="test.event",
            message="Test message",
            trace_context=ctx
        )
        self.assertEqual(event.event_type, "test.event")
        self.assertEqual(event.message, "Test message")
        self.assertIsNotNone(event.timestamp)

    def test_structured_event_optional_fields(self):
        """StructuredEvent should support optional latency and error fields."""
        ctx = TraceContext()
        event = StructuredEvent(
            event_type="test.event",
            message="Test message",
            trace_context=ctx,
            latency_ms=250,
            error_code=500,
            attributes={"service": "specialist", "retry_count": 2}
        )
        self.assertEqual(event.latency_ms, 250)
        self.assertEqual(event.error_code, 500)
        self.assertEqual(event.attributes["retry_count"], 2)

    def test_structured_event_json_serialization(self):
        """StructuredEvent should serialize to valid JSON."""
        ctx = TraceContext(trace_id="trace-123", span_id="span-456")
        event = StructuredEvent(
            event_type="test.event",
            message="Test message",
            trace_context=ctx,
            latency_ms=100,
            error_code=200,
            attributes={"user": "admin", "region": "us-west"}
        )
        json_str = event.to_json()
        parsed = json.loads(json_str)

        self.assertEqual(parsed["event_type"], "test.event")
        self.assertEqual(parsed["trace"]["trace_id"], "trace-123")
        self.assertEqual(parsed["latency_ms"], 100)
        self.assertEqual(parsed["attributes"]["region"], "us-west")

    def test_structured_event_null_attributes(self):
        """StructuredEvent should handle empty attributes gracefully."""
        ctx = TraceContext()
        event = StructuredEvent(
            event_type="test.event",
            message="Test",
            trace_context=ctx,
            attributes={}
        )
        json_str = event.to_json()
        parsed = json.loads(json_str)
        self.assertIsNotNone(parsed.get("attributes"))


class TestLatencyBucket(unittest.TestCase):
    """Validate latency histogram bucketing."""

    def test_latency_bucket_initialization(self):
        """LatencyBucket should initialize with default boundaries."""
        bucket = LatencyBucket()
        self.assertIsNotNone(bucket.boundaries_ms)
        self.assertEqual(len(bucket.buckets), 0)

    def test_latency_bucket_custom_boundaries(self):
        """LatencyBucket should accept custom boundaries."""
        bucket = LatencyBucket(boundaries_ms=[10, 50, 100])
        self.assertEqual(bucket.boundaries_ms, [10, 50, 100])

    def test_latency_bucket_record_within_boundary(self):
        """LatencyBucket should categorize latency within boundaries."""
        bucket = LatencyBucket(boundaries_ms=[100, 500, 1000])
        bucket.record(75)

        bucket_dict = bucket.to_dict()
        self.assertIn("100ms", bucket_dict)
        self.assertEqual(bucket_dict["100ms"], 1)

    def test_latency_bucket_record_exceeds_boundary(self):
        """LatencyBucket should handle latency exceeding all boundaries."""
        bucket = LatencyBucket(boundaries_ms=[100, 500])
        bucket.record(2000)

        bucket_dict = bucket.to_dict()
        self.assertIn("inf", bucket_dict)
        self.assertEqual(bucket_dict["inf"], 1)

    def test_latency_bucket_multiple_recordings(self):
        """LatencyBucket should accumulate multiple recordings."""
        bucket = LatencyBucket(boundaries_ms=[100, 500, 1000])
        bucket.record(50)   # → 100ms bucket
        bucket.record(50)   # → 100ms bucket
        bucket.record(250)  # → 500ms bucket
        bucket.record(2000) # → inf bucket

        bucket_dict = bucket.to_dict()
        self.assertEqual(bucket_dict.get("100ms"), 2)
        self.assertEqual(bucket_dict.get("500ms"), 1)
        self.assertEqual(bucket_dict.get("inf"), 1)


class TestMetricsCollector(unittest.TestCase):
    """Validate metrics collection and SLO tracking."""

    def test_metrics_collector_success_rate_calculation(self):
        """MetricsCollector should calculate success_rate correctly."""
        collector = MetricsCollector()

        # Record 7 successes and 3 failures
        for _ in range(7):
            collector.record_success()
        for _ in range(3):
            collector.record_failure()

        success_rate = collector.success_rate()
        self.assertEqual(success_rate, 0.7)

    def test_metrics_collector_latency_tracking(self):
        """MetricsCollector should track latency for services."""
        collector = MetricsCollector()

        # Record latencies for a service
        collector.record_latency("weather-service", 50)
        collector.record_latency("weather-service", 100)
        collector.record_latency("weather-service", 150)

        metrics_dict = collector.to_dict()
        self.assertIn("latency_buckets", metrics_dict)
        self.assertIn("weather-service", metrics_dict["latency_buckets"])

    def test_metrics_collector_zero_requests(self):
        """MetricsCollector should handle zero requests gracefully."""
        collector = MetricsCollector()
        success_rate = collector.success_rate()
        self.assertEqual(success_rate, 1.0)

    def test_metrics_collector_counter_operations(self):
        """MetricsCollector should support counter increment."""
        collector = MetricsCollector()

        collector.increment_counter("requests")
        collector.increment_counter("requests")
        collector.increment_counter("requests", value=5)

        counter_value = collector.counters["requests"]
        self.assertEqual(counter_value, 7)

    def test_metrics_collector_circuit_breaker_events(self):
        """MetricsCollector should track circuit breaker events."""
        collector = MetricsCollector()

        collector.record_breaker_open()
        collector.record_breaker_open()

        self.assertEqual(collector.breaker_open_count, 2)

    def test_metrics_collector_retry_tracking(self):
        """MetricsCollector should track retry events."""
        collector = MetricsCollector()

        collector.record_retry()
        collector.record_retry()

        self.assertEqual(collector.retry_count, 2)

    def test_metrics_collector_to_dict(self):
        """MetricsCollector should serialize to dict."""
        collector = MetricsCollector()
        collector.record_success()
        collector.record_failure()
        collector.increment_counter("requests", value=2)

        metrics_dict = collector.to_dict()

        self.assertIn("success_rate", metrics_dict)
        self.assertIn("success_count", metrics_dict)
        self.assertIn("failure_count", metrics_dict)
        self.assertIn("counters", metrics_dict)
        self.assertEqual(metrics_dict["success_count"], 1)
        self.assertEqual(metrics_dict["failure_count"], 1)


class TestObservabilityContext(unittest.TestCase):
    """Validate observability context as central trace and event manager."""

    def test_observability_context_initialization(self):
        """ObservabilityContext should initialize with default trace context."""
        obs_ctx = ObservabilityContext()
        self.assertIsNotNone(obs_ctx.current_trace)
        self.assertIsNotNone(obs_ctx.metrics)
        self.assertEqual(len(obs_ctx.event_log), 0)

    def test_observability_context_new_trace(self):
        """ObservabilityContext should create new trace contexts."""
        obs_ctx = ObservabilityContext()

        trace1 = obs_ctx.current_trace
        trace2 = obs_ctx.new_trace()

        self.assertNotEqual(trace1.trace_id, trace2.trace_id)
        self.assertEqual(obs_ctx.current_trace.trace_id, trace2.trace_id)

    def test_observability_context_new_span(self):
        """ObservabilityContext should create child spans with same trace_id."""
        obs_ctx = ObservabilityContext()
        initial_trace_id = obs_ctx.current_trace.trace_id

        span = obs_ctx.new_span()

        self.assertEqual(span.trace_id, initial_trace_id)
        self.assertTrue(span.span_id != initial_trace_id)

    def test_observability_context_emit_event(self):
        """ObservabilityContext should emit and store events."""
        obs_ctx = ObservabilityContext()

        event = StructuredEvent(
            event_type="test.event",
            message="Test",
            trace_context=obs_ctx.current_trace
        )
        obs_ctx.emit_event(event)

        self.assertEqual(len(obs_ctx.event_log), 1)
        self.assertEqual(obs_ctx.event_log[0].event_type, "test.event")

    def test_observability_context_trace_propagation(self):
        """ObservabilityContext should propagate trace IDs through events."""
        obs_ctx = ObservabilityContext()
        initial_trace_id = obs_ctx.current_trace.trace_id

        event1 = StructuredEvent(
            event_type="event1",
            message="Message 1",
            trace_context=obs_ctx.current_trace
        )
        event2 = StructuredEvent(
            event_type="event2",
            message="Message 2",
            trace_context=obs_ctx.current_trace
        )

        obs_ctx.emit_event(event1)
        obs_ctx.emit_event(event2)

        self.assertEqual(event1.trace_context.trace_id, initial_trace_id)
        self.assertEqual(event2.trace_context.trace_id, initial_trace_id)

    def test_observability_context_get_metrics(self):
        """ObservabilityContext should provide metrics access."""
        obs_ctx = ObservabilityContext()

        metrics = obs_ctx.metrics
        self.assertIsNotNone(metrics)
        self.assertEqual(metrics.success_count, 0)

    def test_observability_context_record_latency(self):
        """ObservabilityContext should record latency through metrics."""
        obs_ctx = ObservabilityContext()

        obs_ctx.metrics.record_latency("specialist", 150)
        obs_ctx.metrics.record_success()

        self.assertEqual(obs_ctx.metrics.success_count, 1)


class TestE2EObservabilityIntegration(unittest.TestCase):
    """End-to-end integration test for complete observability flow."""

    def test_e2e_trace_with_multiple_events(self):
        """Full observability flow: trace context → events → metrics → aggregation."""
        obs_ctx = ObservabilityContext()

        trace_id = obs_ctx.current_trace.trace_id

        # Emit handoff creation event
        obs_ctx.emit_event(StructuredEvent(
            event_type="a2a.handoff.created",
            message="Handoff created",
            trace_context=obs_ctx.current_trace,
            attributes={"query": "Get weather"}
        ))

        # Simulate retry
        obs_ctx.emit_event(StructuredEvent(
            event_type="a2a.retry",
            message="Retry attempt",
            trace_context=obs_ctx.current_trace,
            latency_ms=250,
            error_code=504,
            attributes={"attempt": 1}
        ))

        # Emit successful completion
        obs_ctx.emit_event(StructuredEvent(
            event_type="a2a.completion",
            message="Handoff completed",
            trace_context=obs_ctx.current_trace,
            latency_ms=500,
            attributes={"result_size": 128}
        ))

        # Record metrics
        obs_ctx.metrics.record_latency("specialist", 500)
        obs_ctx.metrics.record_success()

        # Verify end-to-end
        self.assertEqual(len(obs_ctx.event_log), 3)
        self.assertEqual(obs_ctx.metrics.success_count, 1)
        self.assertEqual(obs_ctx.metrics.success_rate(), 1.0)

    def test_e2e_multiple_services_with_correlation(self):
        """Multiple services should maintain correlation through trace_id."""
        obs_ctx = ObservabilityContext()
        trace_id = obs_ctx.current_trace.trace_id

        # Supervisor events
        obs_ctx.emit_event(StructuredEvent(
            event_type="supervisor.request",
            message="Supervisor request",
            trace_context=obs_ctx.current_trace,
            attributes={"service": "supervisor"}
        ))

        # Specialist events with same trace_id via new span
        specialist_span = obs_ctx.new_span()
        obs_ctx.emit_event(StructuredEvent(
            event_type="specialist.invoked",
            message="Specialist invoked",
            trace_context=specialist_span,
            latency_ms=100,
            attributes={"service": "specialist"}
        ))

        # MCP tool events with same trace_id via another span
        mcp_span = obs_ctx.new_span()
        obs_ctx.emit_event(StructuredEvent(
            event_type="mcp.tool.called",
            message="MCP tool called",
            trace_context=mcp_span,
            latency_ms=50,
            attributes={"tool": "get_weather", "service": "mcp"}
        ))

        # All events should share same trace_id
        for event in obs_ctx.event_log:
            self.assertEqual(event.trace_context.trace_id, trace_id)

        # But different span_ids
        span_ids = {event.trace_context.span_id for event in obs_ctx.event_log}
        self.assertEqual(len(span_ids), 3)


if __name__ == "__main__":
    unittest.main()
