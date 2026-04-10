# 🧪 Complete App Testing Guide

## Step 1: Start the Streamlit App

```bash
cd "/Users/sohanpatil/Downloads/MCP A2A Weather"
source .venv/bin/activate
streamlit run Weather_streamlit_app.py
```

**Expected Output:**
- Terminal shows: `You can now view your Streamlit app in your browser.`
- Browser automatically opens to: `http://localhost:8501`
- Page loads with dark theme, cyan header "WEATHER MCP AGENT"

---

## Step 2: Check Core UI Elements (Before Any Interaction)

### ✅ Sidebar
- [x] Developer name: "Sohan Patil" with GitHub/LinkedIn links
- [x] Project info card with "MCP-POWERED PRO" badge
- [x] Professional badge showing: "Data Scientist (AI/ML) | 4+ Yrs"

### ✅ 8 Navigation Tabs
Look for all tabs at the top:
1. 🚀 Project Demo
2. ℹ️ About Project
3. 🛠️ Tech Stack
4. 🏗️ Architecture
5. 📋 System Logs
6. ⚡ Resilience Hub (NEW)
7. 🔒 Security Audit (NEW)
8. 📊 Observability (NEW)

**If any tab is missing → Something went wrong with the code edit**

---

## Step 3: Test Tab 1 - Project Demo (Main Chat)

### Before Chat Interactions:
- [ ] 12 Quick Weather buttons visible (NY, London, Tokyo, etc.)
- [ ] 4 Weather landscape images displaying (or image placeholders if git-lfs issue)
- [ ] Model selector dropdown showing: "llama-3.3-70b-versatile" (default)
- [ ] Input text field with label "Query"
- [ ] Enter 🚀 and Stop ⏹️ buttons
- [ ] 4 Control buttons visible:
  - 🎤 Voice (Record/Stop)
  - 💾 Save (JSON/TXT export)
  - 🧹 Clear Chat
  - 🔄 Reset System

### Test Chat Interaction:
1. **Click any quick button** (e.g., "🗽 NY Weather")
2. **Expected:** 
   - Message appears in chat: "What is the current weather in New York?"
   - Status bar shows: "✨ SohanAI is doing its magic..."
   - Two cards appear:
     - 👤 **Supervisor Agent**: Waiting for Specialist...
     - 🌩️ **Weather Specialist**: Extracting MCP Data...

3. **Wait for response** (30-60 seconds):
   - Bot response appears with streaming text (words appear one at a time)
   - Supervisor & Specialist cards update to completion status
   - Response is added to chat history

4. **Check System Logs Tab** for these protocol messages:
   ```
   A2A_HANDOFF: {trace_id, task_id, deadline_ms, ...}
   A2A_COMPLETE: trace_id=... task_id=... elapsed=X.XXs
   ```

---

## Step 4: Test Tab 5 - System Logs

### Metrics Row (Top):
- [ ] TOTAL EVENTS: Should show > 0 after first query
- [ ] SUCCESS RATE: Should show percentage (e.g., 100%)
- [ ] SYSTEM ERRORS: Should show error count (0 if no failures)

### Log Filtering:
- [ ] Search box works (type anything, logs filter)
- [ ] Log Levels multiselect shows: INFO, SUCCESS, WARNING, ERROR, PROTOCOL
- [ ] Buttons work:
  - 🔄 Refresh (reruns page)
  - 🗑️ Clear (clears all logs)
  - 📄 Save TXT (downloads logs)
  - 💾 Save JSON (downloads logs)

### Log Types (Color coded):
- ℹ️ **INFO** (Blue) - General messages
- ✅ **SUCCESS** (Green) - Tool executed successfully
- ⚠️ **WARNING** (Yellow) - Non-critical issues
- ❌ **ERROR** (Red) - Actual errors/failures
- 📡 **PROTOCOL** (Cyan) - JSON-RPC requests/responses

**Expected Logs after chat interaction:**
```
[HH:MM:SS] INFO: Voice captured: ...
[HH:MM:SS] INFO: User Query: ...
[HH:MM:SS] PROTOCOL: 📡 SENT JSON-RPC REQUEST: {...}
[HH:MM:SS] SUCCESS: 📄 Tool result: ...
[HH:MM:SS] PROTOCOL: 📥 RCVD JSON-RPC RESPONSE: {...}
```

---

## Step 5: Test Tab 6 - Resilience Hub ⚡ (NEW)

### Sub-tab 1: Circuit Breakers
**First interaction should populate it**

Look for cards showing:
- [ ] Service name (e.g., "weather-specialist")
- [ ] State indicator: ✅ **CLOSED** (green) / ⚠️ **HALF_OPEN** (yellow) / 🔴 **OPEN** (red)
- [ ] Metrics:
  - Total Requests: (number)
  - Successes: (number)
  - Failure Rate: (percentage)

- [ ] Expandable details showing:
  - failure_threshold
  - recovery_timeout_s
  - current_failures (should be 0 if CLOSED)
  - last_failure (timestamp or "Never")
  - half_open_successes

**Expected behavior:**
- First few requests: state = "closed", failures = 0
- If 5+ failures happen: state transitions to "open", showing recovery timeout

### Sub-tab 2: Retry Metrics
Should show a table:
| Attempt | Duration (sec) | Cumulative (sec) |
|---------|----------------|------------------|
| 1       | 0.1XX          | 0.1XX            |
| 2       | 0.2XX          | 0.3XX            |
| 3       | 0.4XX          | 0.8XX            |
| 4       | 0.8XX          | 1.6XX            |
| 5       | 1.6XX          | 3.2XX            |

**This shows exponential backoff working correctly**

### Sub-tab 3: Failure Patterns
Should show a bar chart (initially empty):
- [ ] Chart title shows "Success" and "Failures" for each service
- [ ] After errors/retries, bars appear visualizing the ratio

---

## Step 6: Test Tab 7 - Security Audit 🔒 (NEW)

### Sub-tab 1: Policy Decisions
Check the following sections:

**RBAC Tool Restrictions** (should show):
```
- get_alerts: supervisor, admin
- get_coordinates: supervisor, specialist, admin
- get_global_forecast: supervisor, specialist, admin
```

**Geographic Restrictions Table:**
| Role       | Allowed Regions |
|------------|-----------------|
| guest      | US              |
| supervisor | US, Global      |
| specialist | US, Global      |
| admin      | US, Global      |

**Policy Violation Examples** (3 cards):
- [ ] ❌ Violation: Insufficient Role (guest cannot access get_alerts)
- [ ] ❌ Violation: Geographic Restriction (guest cannot access Europe)
- [ ] ✅ Allowed: Admin Access (admin can access globally)

### Sub-tab 2: Agent Identity
Should show 2 sample identity certificates:
- [ ] supervisor-agent: Role = "supervisor", Status = "✅ Valid"
- [ ] weather-specialist: Role = "specialist", Status = "✅ Valid"

Shows HMAC signature verification code example

### Sub-tab 3: Access Events
Shows audit log with 4 sample events:
- [ ] Each event has: [timestamp] ACTION label (✅ ALLOW or ❌ DENY)
- [ ] Shows: agent → tool (reason)

---

## Step 7: Test Tab 8 - Observability Metrics 📊 (NEW)

### Sub-tab 1: SLO Metrics
Shows 4 cards:
- [ ] ✅ Success Rate: X.X% (should increase after interactions)
- [ ] 📊 Total Operations: 0 (increases with each query)
- [ ] 🔄 Retries: 0 (increases if failures occur)
- [ ] 🔴 Breaker Opens: 0 (increases if circuit breaker opens)

**SLO Definitions Table:**
| Service              | SLO Target | Alert Threshold | Status        |
|----------------------|-----------|-----------------|---------------|
| A2A Handoff          | < 2000ms  | > 2500ms        | ✅ On Track   |
| Weather Specialist   | < 5000ms  | > 6000ms        | ✅ On Track   |
| MCP Tool Call        | < 1000ms  | > 1200ms        | ✅ On Track   |

### Sub-tab 2: Latency Percentiles
Should be empty initially. After first interaction:
- [ ] Bar chart appears showing distribution across latency buckets
- [ ] Table shows: Latency Bucket | Count | Cumulative %

**Example after query:**
| Latency   | Count | Cumulative % |
|-----------|-------|--------------|
| 100ms     | 2     | 20%          |
| 500ms     | 5     | 70%          |
| 1000ms    | 2     | 90%          |
| 5000ms    | 1     | 100%         |

### Sub-tab 3: Trace Events
Shows: "Total Events Logged: X"
- [ ] Each event shows blue boxes with:
  - Trace ID
  - Event type
  - Timestamp

**Examples of events:**
- a2a.handoff.created
- a2a.retry
- a2a.completion
- a2a.error

### Sub-tab 4: Performance Dashboard
Shows two JSON blocks:
- [ ] **Operation Counters:**
  ```json
  {
    "a2a_handoffs": 0,
    "tool_calls": 0,
    "api_requests": 0
  }
  ```

- [ ] **Gauge Metrics:**
  ```json
  {
    "active_spans": 0
  }
  ```

- [ ] **Download Metrics JSON** button at bottom

---

## Step 8: Test Interactive Features

### Voice Input:
1. Click 🎤 **Record** button
2. Speak clearly: "What is the weather in London?"
3. Click **Stop** button
4. **Expected:** Transcribed text appears in chat
5. Response is generated automatically

### Export Chat:
1. Click 📥 **JSON** button → downloads JSON file with chat history
2. Click 📄 **TXT** button → downloads TXT file with formatted chat

### Model Switching:
1. Change dropdown to "llama-3.1-8b-instant"
2. Confirm toast message: "Processing with MCP Agent..."
3. Ask another question
4. Response comes from the new model

### Clear/Reset:
1. Click 🧹 **Clear Chat** → Chat history disappears, logs remain
2. Click 🔄 **Reset System** → System resets completely

---

## Step 9: Verify All Tab 2 & 3 Content (Should Display)

### Tab 2: About Project
Should show markdown with:
- Executive summary
- A2A architecture diagram
- Code highlights
- MCP concepts

### Tab 3: Tech Stack
Should show:
- Technology cards (3 columns)
- Filter buttons (All Layers, Intelligence, Frontend, Connectivity)
- Component details (AI Core, Application, Data Source)
- Interactive Component Details section

### Tab 4: Architecture
Should show:
- Architecture visualization with flow arrows
- Graphviz diagram (visual graph)
- Data Flow Simulation section
- Component Deep Dive tabs

---

## Step 10: Test Error Scenarios (Optional)

### Scenario 1: Network Error (Simulate)
1. Disconnect internet briefly
2. Try to query
3. **Expected:** Error message in Specialist card, logged as ERROR

### Scenario 2: Timeout Simulation
1. Query with very complex request
2. **Expected:** After 15s timeout, A2A_TIMEOUT logged

### Scenario 3: Repeated Requests (Idempotency)
1. Ask same question twice in a row
2. **Expected:** Second request should hit cache (A2A_DEDUPE_HIT in logs)

---

## ✅ Final Verification Checklist

**Before submitting:**

- [ ] All 8 tabs load without errors
- [ ] Chat interaction works (text and voice)
- [ ] Protocol logs show JSON-RPC requests/responses
- [ ] Resilience Hub shows circuit breaker state
- [ ] Security Audit shows policy restrictions
- [ ] Observability shows SLO metrics
- [ ] Export functions (JSON, TXT, Metrics) work
- [ ] Model switching works
- [ ] No console errors in terminal
- [ ] All emojis and colors display correctly
- [ ] Footer with GitHub/LinkedIn links is visible

---

## 🔴 Common Issues & Fixes

| Issue | Solution |
|-------|----------|
| Images not loading | Git-LFS issue, show placeholder |
| Voice recording error | Check browser microphone permissions |
| Chat response is slow | Normal (Groq API latency), check logs |
| Logs not updating | Check if st.session_state initialized |
| New tabs not appearing | Clear browser cache, restart app |
| Metrics all showing 0 | Expected before first interaction |
| Circuit breaker not visible | Needs to be triggered on first error |

---

## 🎯 Expected Performance Metrics

**After 5 successful queries:**
- Total Events: ~20-30
- Success Rate: 100%
- Latency: 2000-5000ms (Groq LPU processing)
- Retries: 0 (if no errors)
- Circuit Breaker State: CLOSED

