#!/usr/bin/env python3
"""
Quick test to verify observability instrumentation is working.
Shows which counters, latencies, and events are being tracked.
"""

from server.observability import ObservabilityContext, StructuredEvent, TraceContext
import json
import time

def test_counters():
    """Test that counters work and display in metrics."""
    print("=" * 60)
    print("🧪 Testing Counters")
    print("=" * 60)
    
    obs_ctx = ObservabilityContext()
    
    # Simulate what the app does
    print("\n1️⃣  Simulating A2A handoff creation...")
    obs_ctx.metrics.increment_counter("a2a_handoffs")
    print(f"   ✅ a2a_handoffs counter = {obs_ctx.metrics.counters.get('a2a_handoffs', 0)}")
    
    print("\n2️⃣  Simulating tool call completion...")
    obs_ctx.metrics.increment_counter("tool_calls")
    print(f"   ✅ tool_calls counter = {obs_ctx.metrics.counters.get('tool_calls', 0)}")
    
    print("\n3️⃣  Simulating API requests...")
    obs_ctx.metrics.increment_counter("api_requests", value=3)
    print(f"   ✅ api_requests counter = {obs_ctx.metrics.counters.get('api_requests', 0)}")
    
    return obs_ctx

def test_latency():
    """Test that latency tracking works."""
    print("\n" + "=" * 60)
    print("⏱️  Testing Latency Tracking")
    print("=" * 60)
    
    obs_ctx = ObservabilityContext()
    
    print("\n1️⃣  Recording latencies for weather-specialist...")
    for latency in [150, 320, 450, 890, 2100]:
        obs_ctx.metrics.record_latency("weather-specialist", latency)
        print(f"   📊 Recorded {latency}ms")
    
    print("\n2️⃣  Checking latency distribution...")
    if obs_ctx.metrics.latency_percents:
        latency_data = obs_ctx.metrics.latency_percents["weather-specialist"].to_dict()
        for bucket, count in sorted(latency_data.items(), key=lambda x: x[0]):
            print(f"   Bucket {bucket:5s}: {count} calls")
    
    return obs_ctx

def test_events():
    """Test that structured events are logged."""
    print("\n" + "=" * 60)
    print("🔍 Testing Structured Event Logging")
    print("=" * 60)
    
    obs_ctx = ObservabilityContext()
    
    print("\n1️⃣  Emitting A2A handoff event...")
    trace = obs_ctx.current_trace
    obs_ctx.emit_event(StructuredEvent(
        event_type="a2a.handoff.created",
        trace_context=trace,
        attributes={"task_id": "task_123", "query": "weather in NYC"}
    ))
    print(f"   ✅ Event logged: a2a.handoff.created")
    
    print("\n2️⃣  Emitting completion event...")
    obs_ctx.emit_event(StructuredEvent(
        event_type="a2a.completion",
        trace_context=trace,
        latency_ms=1250,
        attributes={"result_length": 512}
    ))
    print(f"   ✅ Event logged: a2a.completion")
    
    print("\n3️⃣  Checking event log...")
    print(f"   📋 Total events logged: {len(obs_ctx.event_log)}")
    for i, event in enumerate(obs_ctx.event_log, 1):
        print(f"   Event {i}: {event.event_type} (trace_id: {event.trace_context.trace_id[:8]}...)")
    
    return obs_ctx

def test_success_rate():
    """Test success rate calculation."""
    print("\n" + "=" * 60)
    print("📈 Testing Success Rate Tracking")
    print("=" * 60)
    
    obs_ctx = ObservabilityContext()
    
    print("\n1️⃣  Recording 8 successes and 2 failures...")
    for _ in range(8):
        obs_ctx.metrics.record_success()
    for _ in range(2):
        obs_ctx.metrics.record_failure()
    
    success_rate = obs_ctx.metrics.success_rate()
    print(f"   ✅ Success Rate = {success_rate * 100:.1f}%")
    print(f"   ✅ Total Operations = {obs_ctx.metrics.success_count + obs_ctx.metrics.failure_count}")
    
    return obs_ctx

def test_performance_dashboard():
    """Show what the Performance Dashboard will display."""
    print("\n" + "=" * 60)
    print("📊 Performance Dashboard Output")
    print("=" * 60)
    
    # Simulate user interactions
    obs_ctx = ObservabilityContext()
    
    # Handoff 1
    obs_ctx.metrics.increment_counter("a2a_handoffs")
    obs_ctx.metrics.record_latency("weather-specialist", 1200)
    obs_ctx.metrics.record_success()
    obs_ctx.metrics.increment_counter("tool_calls")
    
    # Handoff 2
    obs_ctx.metrics.increment_counter("a2a_handoffs")
    obs_ctx.metrics.record_latency("weather-specialist", 950)
    obs_ctx.metrics.record_success()
    obs_ctx.metrics.increment_counter("tool_calls")
    
    # Handoff 3 (failed)
    obs_ctx.metrics.increment_counter("a2a_handoffs")
    obs_ctx.metrics.record_failure()
    obs_ctx.metrics.record_retry()
    
    print("\n🎯 Operation Counters (what Performance Dashboard shows):")
    print(f"   a2a_handoffs: {obs_ctx.metrics.counters.get('a2a_handoffs', 0)} ✅")
    print(f"   tool_calls:   {obs_ctx.metrics.counters.get('tool_calls', 0)} ✅")
    print(f"   api_requests: {obs_ctx.metrics.counters.get('api_requests', 0)} (set if tracking API calls)")
    
    print("\n📈 Metrics Summary:")
    print(f"   Success Rate:        {obs_ctx.metrics.success_rate() * 100:.1f}%")
    print(f"   Total Operations:    {obs_ctx.metrics.success_count + obs_ctx.metrics.failure_count}")
    print(f"   Retries:             {obs_ctx.metrics.retry_count}")
    print(f"   Breaker Opens:       {obs_ctx.metrics.breaker_open_count}")
    
    return obs_ctx

if __name__ == "__main__":
    print("\n")
    print("🔬 OBSERVABILITY SYSTEM TEST")
    print("━" * 60)
    
    test_counters()
    test_latency()
    test_events()
    test_success_rate()
    obs_ctx = test_performance_dashboard()
    
    print("\n" + "=" * 60)
    print("📥 Full Metrics JSON (what gets exported):")
    print("=" * 60)
    print(json.dumps(obs_ctx.metrics.to_dict(), indent=2))
    
    print("\n✅ ALL TESTS COMPLETE!")
    print("━" * 60)
    print("\n📌 To verify in the app:")
    print("   1. Run: streamlit run Weather_streamlit_app.py")
    print("   2. Ask a weather question in Chat tab")
    print("   3. Go to Observability tab → Performance Dashboard")
    print("   4. Check that counters are incrementing ↑↑↑")
    print()
