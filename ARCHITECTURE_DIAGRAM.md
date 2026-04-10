# MCP + A2A Weather: Complete Architecture Diagram and Implementation Inventory

This document maps the entire implemented architecture in this repository, including runtime flows, all implementation modules, and test coverage.

## 1) System-Level Architecture

```mermaid
flowchart LR
    U[User] -->|Text or Voice| ST[Weather_streamlit_app.py\nStreamlit Host UI]

    subgraph AppState[Streamlit Session State]
      MSG[messages list]
      LOGS[logs list]
      IDEMP[SQLiteA2AIdempotencyStore\nWeather result/a2a_idempotency.db]
      RESCTX[ResilienceContext]
      OBSCTX[ObservabilityContext]
    end

    ST --> MSG
    ST --> LOGS
    ST --> IDEMP
    ST --> RESCTX
    ST --> OBSCTX

    ST -->|MCP client config| CFG[server/weather.json]
    ST -->|create agent| MCPUSE[mcp-use MCPAgent + MCPClient]
    MCPUSE --> LLM[ChatGroq Models\nllama-3.3-70b-versatile etc.]

    ST -->|Supervisor orchestration| LG[LangGraph create_react_agent]
    LG --> HS[tool: agent_protocol_handshake]
    LG --> AWS[tool: ask_weather_specialist]

    HS --> RESCTX
    AWS -->|build_handoff| A2A[server/a2a_protocol.py]
    AWS --> IDEMP
    AWS --> RESCTX
    AWS --> OBSCTX

    AWS -->|specialist run query| MCPUSE

    MCPUSE -->|MCP transport| WS[server/weather.py FastMCP Server]
    WS --> SEC[server/security.py PolicyEngine]
    WS -->|US alerts| NWS[api.weather.gov]
    WS -->|global geocoding + forecast| OM[Open-Meteo APIs]

    WS --> MCPUSE --> LG --> ST --> U
```

## 2) Server-Side Implementation Architecture

```mermaid
flowchart TB
    subgraph server/weather.py
  W0[mcp FastMCP weather]
      W1[ProtocolError]
      W2[TOOL_CONTRACTS + protocol constants]
      W3[_serialize_ok / _serialize_error]
      W4[_validate_state / _validate_city_name / _coerce_coordinate]
      W5[_enforce_policy -> PolicyEngine.evaluate_tool_access]
      W6[get_capabilities]
      W7[negotiate_protocol]
      W8[get_alerts]
      W9[get_coordinates]
      W10[get_global_forecast]
      W11[echo_resource]
      W12[make_nws_request + format_alert]
    end

    subgraph server/security.py
      S1[DenyReason enum]
      S2[AgentIdentity dataclass]
      S3[PolicyDecision dataclass]
      S4[PolicyEngine\n- sign_identity\n- verify_identity_signature\n- evaluate_tool_access]
      S5[SignedHandoffMetadata dataclass]
    end

    subgraph server/a2a_protocol.py
      A1[A2AHandoffEnvelope dataclass\n- deadline_at/is_expired/remaining_seconds\n- to_dict/to_json]
      A2[A2AIdempotencyStore in-memory]
      A3[SQLiteA2AIdempotencyStore durable]
      A4[_make_idempotency_key]
      A5[build_handoff]
    end

    subgraph server/resilience.py
      R1[CircuitState enum]
      R2[RetryPolicy.backoff_duration]
      R3[CircuitBreakerConfig]
      R4[CircuitBreakerMetrics]
      R5[CircuitBreaker\n- record_success/failure\n- can_execute\n- state transitions]
      R6[ResilienceContext\n- get_breaker\n- execute_with_resilience]
    end

    subgraph server/observability.py
      O1[TraceContext]
      O2[StructuredEvent.to_json]
      O3[LatencyBucket.record]
      O4[MetricsCollector\n- counters/gauges\n- success_rate\n- latency buckets]
      O5[ObservabilityContext\n- new_trace/new_span\n- emit_event/emit_log\n- get_event_log_json/get_metrics_json]
    end

    W5 --> S4
    W8 --> W12
    W9 --> OM[Open-Meteo]
    W10 --> OM
    W8 --> NWS[NWS]
```

## 3) Runtime Sequence (Supervisor -> Specialist -> MCP Tools)

```mermaid
sequenceDiagram
    participant User
    participant UI as Streamlit UI
    participant Sup as Supervisor Agent (LangGraph)
    participant Spec as Specialist MCPAgent
    participant A2A as A2A + Idempotency
    participant Res as ResilienceContext
    participant Obs as ObservabilityContext
    participant MCP as FastMCP weather server
    participant Ext as NWS/Open-Meteo APIs

    User->>UI: Ask weather question
    UI->>Sup: run_loop_safe() + messages

    alt No handshake in history
      Sup->>Spec: agent_protocol_handshake
      Spec->>Res: execute_with_resilience(handshake)
      Res-->>Spec: success/failure
    end

    Sup->>A2A: build_handoff(query, target_agent, seed)
    A2A-->>Sup: envelope(idempotency_key, deadline)

    alt Idempotency cache hit
      A2A-->>Sup: cached specialist result
    else Cache miss
      Sup->>Obs: emit a2a.handoff.created
      Sup->>Res: execute_with_resilience(specialist.run)
      Res->>Spec: call with timeout + retries + circuit breaker
      Spec->>MCP: tool calls via mcp-use
      MCP->>Ext: HTTP requests
      Ext-->>MCP: weather payload
      MCP-->>Spec: tool result
      Spec-->>Sup: specialist answer
      Sup->>A2A: store idempotent result
      Sup->>Obs: emit completion/retry/failure metrics
    end

    Sup-->>UI: final synthesized response
    UI-->>User: rendered answer + logs
```

## 4) Complete Implementation Inventory (All Implemented Modules)

### Root modules

- `main.py`
  - `main()`

- `Weather_streamlit_app.py`
  - Top-level setup:
    - Event loop policy for Windows
    - `nest_asyncio.apply()`
    - `load_dotenv()`
    - `st.set_page_config(...)`
    - session state keys: `messages`, `logs`, `a2a_idempotency_store`, `resilience_context`, `observability_context`
  - Functions:
    - `safe_image(path, caption=None, use_container_width=True)`
    - `add_log(message, type="info")`
    - `transcribe_audio(audio_bytes)`
    - `get_agent(model_name="llama-3.3-70b-versatile", callbacks=None)`
  - UI implementation:
    - Sidebar profile/project metadata
    - Five tabs: Project Demo, About Project, Tech Stack, Architecture, System Logs
    - Quick action grid (16 preset prompts)
    - Voice capture via `mic_recorder`
    - Chat export JSON/TXT, clear/reset controls
    - Graphviz architecture rendering
    - Real-time activity/system log panels and filters
  - Nested runtime classes/functions inside query execution path:
    - `UILogHandler(logging.Handler)` with `emit`
    - `UIStreamHandler(AsyncCallbackHandler)` with:
      - `__init__`
      - `on_llm_start`
      - `on_llm_new_token`
      - `on_llm_end`
    - `run_loop_safe()`
      - tool `ask_weather_specialist(query: str)`
        - `build_handoff(...)`
        - idempotency read/write
        - `ResilienceContext.get_breaker(...)`
        - callbacks: `on_retry_event`, `on_failure_event`
        - `execute_with_resilience(...)`
        - observability event emits for handoff/retry/completion/failure/circuit-breaker/error
      - tool `agent_protocol_handshake()`
        - handshake breaker and retry callbacks: `on_hs_retry`, `on_hs_failure`
        - specialist capability handshake call
      - LangGraph `create_react_agent` orchestration with system prompt

- `test_callback.py`
  - `MyAsyncHandler(AsyncCallbackHandler).on_llm_new_token(...)`
  - `test()` async demo

- `test_stream.py`
  - `test()` async demo for `agent.stream(...)`

- `test_stream_events.py`
  - `test()` async demo for `agent.stream_events(..., version="v2")`

### Server modules

- `server/weather.py`
  - Constants/config:
    - `NWS_API_BASE`, `USER_AGENT`, `SERVER_NAME`, `SERVER_VERSION`, `SCHEMA_VERSION`, `SUPPORTED_PROTOCOL_VERSIONS`
    - `TOOL_CONTRACTS`
    - `OPEN_METEO_GEO_URL`, `OPEN_METEO_API_URL`
  - Class:
    - `ProtocolError(Exception)` with `to_dict()`
  - Helper functions:
    - `_serialize_ok(data)`
    - `_serialize_error(error)`
    - `_enforce_policy(tool_name, agent_role="supervisor", region="US")`
    - `_validate_state(state)`
    - `_validate_city_name(city_name)`
    - `_coerce_coordinate(name, value, min_value, max_value)`
    - `_build_capabilities()`
    - `make_nws_request(url)`
    - `format_alert(feature)`
  - MCP tools/resources:
    - `get_capabilities()`
    - `negotiate_protocol(client_protocol_version)`
    - `get_alerts(state)`
    - `get_coordinates(city_name)`
    - `get_global_forecast(latitude, longitude)`
    - `echo_resource(message)` via `@mcp.resource("echo://{message}")`

- `server/a2a_protocol.py`
  - `A2AHandoffEnvelope` dataclass and methods:
    - `deadline_at`, `is_expired`, `remaining_seconds`, `to_dict`, `to_json`
  - `A2AIdempotencyStore` in-memory methods: `has`, `get`, `set`
  - `SQLiteA2AIdempotencyStore` methods:
    - `_connect`, `_ensure_schema`, `has`, `get`, `set`
  - `_make_idempotency_key(seed)`
  - `build_handoff(...)`

- `server/security.py`
  - `DenyReason` enum
  - `AgentIdentity` dataclass with `to_dict`
  - `PolicyDecision` dataclass with `to_dict`
  - `PolicyEngine`:
    - restrictions maps: `tool_role_restrictions`, `geographic_restrictions`
    - `sign_identity(identity)`
    - `verify_identity_signature(identity, signature)`
    - `evaluate_tool_access(tool_name, identity, intent_class="neutral", region="US")`
  - `SignedHandoffMetadata` dataclass with `to_dict`, `to_json`

- `server/resilience.py`
  - `CircuitState` enum
  - `RetryPolicy` dataclass with `backoff_duration(attempt)`
  - `CircuitBreakerConfig` dataclass
  - `CircuitBreakerMetrics` dataclass
  - `CircuitBreaker`:
    - `record_success`, `record_failure`, `can_execute`, `_transition_to`
  - `ResilienceContext`:
    - `get_breaker(name, config=None)`
    - `execute_with_resilience(call_name, coro_fn, timeout_s, on_retry, on_failure)`

- `server/observability.py`
  - `TraceContext` dataclass with `to_dict`
  - `StructuredEvent` dataclass with `to_json`
  - `LatencyBucket` with `record`, `to_dict`
  - `MetricsCollector`:
    - `increment_counter`, `set_gauge`, `record_latency`
    - `record_success`, `record_failure`, `record_retry`, `record_breaker_open`
    - `success_rate`, `to_dict`
  - `ObservabilityContext`:
    - `new_trace`, `new_span`
    - `emit_event`, `emit_log`
    - `get_event_log_json`, `get_metrics_json`

- `server/client.py`
  - `run_memory_chat()` async interactive CLI using MCPAgent with `memory_enabled=True`

### Test modules

- `tests/test_protocol_contracts.py`
  - `ProtocolContractTests(unittest.IsolatedAsyncioTestCase)`
  - Covers capability contract shape, protocol negotiation, parameter validation, and alert success formatting.

- `tests/test_a2a_protocol.py`
  - `A2AProtocolTests(unittest.TestCase)`
  - Covers handoff field population, deterministic idempotency keys, remaining deadline behavior, in-memory + SQLite store round-trips.

- `tests/test_security.py`
  - `AgentIdentityTests`
  - `PolicyEngineTests`
  - `SignedHandoffMetadataTests`
  - Covers signatures, role/geographic/intent policy decisions, unknown tool denial, metadata serialization.

- `tests/test_resilience.py`
  - `RetryPolicyTests`
  - `CircuitBreakerTests`
  - `ResilienceContextTests`
  - Covers backoff curve, breaker state transitions, timeout handling, retry callbacks, persistent failure behavior.

- `tests/test_observability.py`
  - `TestTraceContext`
  - `TestStructuredEvent`
  - `TestLatencyBucket`
  - `TestMetricsCollector`
  - `TestObservabilityContext`
  - `TestE2EObservabilityIntegration`
  - Covers trace/span generation, event serialization, histogram buckets, metrics aggregation, and cross-service trace correlation.

## 5) Configuration and Data Artifacts

- `server/weather.json`
  - MCP server launch config: runs `mcp run server/weather.py`

- `pyproject.toml`, `requirements.txt`
  - Python/package dependency manifest for Streamlit, MCP, LangChain, Groq, speech input, and async support.

- `assets/`
  - UI/architecture visual assets used by the Streamlit interface.

- `Weather result/`
  - Runtime persistence target for A2A idempotency SQLite DB.

- Documentation files:
  - `README.md`
  - `Project_Overview.md`
  - `PRODUCTION_ARCHITECTURE.md`
  - These document project intent, usage, and architecture progression.

## 6) Dependency Map (Implementation-Level)

```mermaid
flowchart TD
    WA[Weather_streamlit_app.py]
    W[server/weather.py]
    A2A[server/a2a_protocol.py]
    SEC[server/security.py]
    RES[server/resilience.py]
    OBS[server/observability.py]
    CL[server/client.py]
    CFG[server/weather.json]

    WA --> A2A
    WA --> RES
    WA --> OBS
    WA --> CFG
    WA --> W

    W --> SEC
    CL --> CFG
    CL --> W

    T1[tests/test_protocol_contracts.py] --> W
    T2[tests/test_a2a_protocol.py] --> A2A
    T3[tests/test_security.py] --> SEC
    T4[tests/test_resilience.py] --> RES
    T5[tests/test_observability.py] --> OBS
```

## 7) Notes on Scope

This inventory includes all first-party implementation files present in the repository tree shown in the workspace context:

- root python modules
- all `server/*.py` implementation modules
- all `tests/*.py` automated tests
- root demo/test scripts (`test_callback.py`, `test_stream.py`, `test_stream_events.py`)
- configuration/data artifacts used at runtime (`server/weather.json`, `Weather result/`)
