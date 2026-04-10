# ✅ Observability Verification Checklist

## Problem Fixed
The Performance Dashboard was showing empty counters for A2A handoffs and tool calls. These have now been instrumented.

## Changes Made
✅ **Added A2A Handoff Counter** (Weather_streamlit_app.py:790)
- Increments when a handoff is created
- Tracks total A2A orchestrations

✅ **Added Tool Calls Counter** (Weather_streamlit_app.py:859)
- Increments when specialist agent completes a call
- Tracks total tool invocations

## How to Verify It's Working

### Quick Test (1 minute)
```bash
python test_observability_working.py
```
This shows all metrics working in isolation.

### Full Integration Test (3 minutes)

1. **Start the app:**
   ```bash
   streamlit run Weather_streamlit_app.py
   ```

2. **Ask a weather question** in the Chat tab:
   - "What's the weather in New York?"

3. **Go to → Observability → Performance Dashboard**

4. **Verify these now show LIVE numbers (not 0):**
   | Metric | Before | After |
   |--------|--------|-------|
   | a2a_handoffs | ❌ 0 | ✅ 1+ |
   | tool_calls | ❌ 0 | ✅ 1+ |
   | Success Rate | ✅ Works | ✅ Works |
   | Latency | ✅ Works | ✅ Works |
   | Trace Events | ✅ Works | ✅ Works |

## What Each Counter Means

### `a2a_handoffs`
- **Increments when:** A question is forwarded to specialist agent
- **Tracked in:** app line 790
- **What it tracks:** Agent-to-Agent orchestration events

### `tool_calls`
- **Increments when:** Specialist agent successfully executes a tool
- **Tracked in:** app line 859
- **What it tracks:** MCP tool invocations (get_alerts, get_coordinates, etc.)

### Already Working ✅
- **Success Rate:** % of operations that succeeded
- **Total Operations:** (successes + failures)
- **Retries:** Retry attempts made
- **Breaker Opens:** Circuit breaker activations
- **Latency Percentiles:** Histogram of response times
- **Trace Events:** Correlation IDs and event timeline

## Export Metrics

In Performance Dashboard, click **📥 Download Metrics JSON** to get:
```json
{
  "counters": {
    "a2a_handoffs": 3,
    "tool_calls": 5,
    "api_requests": 15
  },
  "latency_buckets": {
    "weather-specialist": {
      "100ms": 2,
      "500ms": 1,
      "1000ms": 2
    }
  },
  "success_rate": 0.857,
  "success_count": 6,
  "failure_count": 1,
  "retry_count": 2,
  "breaker_open_count": 0
}
```

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Counters still showing 0 | Refresh the Streamlit app (Ctrl+R) |
| No events in Trace Events tab | Ask at least one question in Chat tab |
| Latency showing no bars | Wait for specialist call to complete |

## API Request Counter (Optional)

To also track raw API requests to NWS, add increment in `server/weather.py`:

```python
# After successful NWS API call in make_nws_request()
obs_ctx.metrics.increment_counter("api_requests")
```

However, this requires passing observability context through layers, so it's not critical for MVP.
