# DESIGN.md — System Architecture & AI-Assisted Decisions

## Overview

The Apex Retail Store Intelligence Platform is a full-stack analytics system that converts raw CCTV footage into actionable retail insights. It comprises four loosely coupled layers:

```
┌─────────────────────────────────────────────────────────────────────┐
│  CCTV Cameras (5 stores × 3 cameras = 15 video feeds)              │
└─────────────────────────────┬───────────────────────────────────────┘
                              │ mp4 / RTSP stream
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Detection Pipeline  (pipeline/)                                    │
│  YOLOv8s → ByteTrack → OSNet Re-ID → Zone Engine → Session Manager │
│  → EventEmitter → Redis Streams + JSONL                             │
└─────────────────────────────┬───────────────────────────────────────┘
                              │ Redis XADD / JSONL
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Intelligence API  (api/)  FastAPI + asyncpg                        │
│  POST /events/ingest                                                │
│  GET /stores/{id}/metrics  | funnel | heatmap | anomalies           │
│  GET /health                                                        │
└───────┬─────────────────────────────────────────────────────────────┘
        │ HTTP / JSON
        ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Live Dashboard  (dashboard/)  Streamlit + Plotly                   │
│  KPI Cards | Funnel Chart | Zone Heatmap | Anomaly Alerts           │
│  Live Event Feed                                                    │
└─────────────────────────────────────────────────────────────────────┘
```

---

## AI-Assisted Decisions

### 1. Architecture: Event-Driven with Read-Model Aggregates

**Problem:** Computing analytics (conversion rate, dwell time, funnel stages) directly from raw events requires expensive multi-join queries at read time.

**AI Influence:** An AI assistant suggested the CQRS (Command Query Responsibility Segregation) pattern — maintaining separate write models (events table) and read models (visitor_sessions) updated at write time. This insight significantly shaped the database schema design.

**Implementation:** The `visitor_sessions` table is a running aggregate updated by the ingestion service on each event. Fields like `reached_billing`, `made_purchase`, and `zones_visited` are progressively set as events arrive, enabling O(1) funnel computation.

---

### 2. Pipeline: Separation of Tracking vs. Re-ID

**Problem:** Should Re-ID be integrated into the tracker, or kept separate?

**AI Influence:** An AI assistant highlighted that ByteTrack + Re-ID is the standard production architecture — ByteTrack handles within-camera temporal consistency while Re-ID handles cross-camera identity. Coupling them would limit modularity.

**Implementation:**
- `tracker.py` (ByteTrack) produces ephemeral `track_id` values scoped to a single camera session
- `reid.py` (OSNet) maps `track_id` → persistent `visitor_id` stored in Redis
- This separation allows the pipeline to be extended with additional cameras without modifying the tracker

---

### 3. Session Management: State Machine vs. Time Windows

**Problem:** When should an EXIT event be emitted? A visitor might be temporarily occluded for several frames.

**AI Influence:** An AI assistant suggested treating session management as a formal state machine (ABSENT → ACTIVE → EXITED → ACTIVE via REENTRY) rather than simple time-window logic. This correctly handles the re-entry edge case where a visitor leaves and returns within the same recording window.

**Key design:** The `EXIT_TIMEOUT_FRAMES = 150` (10 seconds @ 15 FPS) distinguishes momentary occlusion from genuine store exit, preventing spurious EXIT/ENTRY event pairs.

---

### 4. Staff Classification: Without Labelled Data

**Problem:** No labelled training data for staff vs. customer classification was provided.

**AI Influence:** An AI assistant proposed two zero-shot classification strategies:
1. Appearance-based (uniform colour histogram)
2. Behaviour-based (persistent long-dwell pattern)

Both were implemented as a cascaded classifier: colour histogram first (lower latency), dwell-time as fallback. The AI assistant helped tune the HSV hue threshold (80–110) to match typical teal/cyan retail uniforms.

---

### 5. Anomaly Detection: Baselines Without Historical Data

**Problem:** Statistical anomaly detection requires historical baseline data, but the challenge provides only 20 minutes of video per camera.

**AI Influence:** An AI assistant suggested implementing the detection logic against a 30-day window baseline, and gracefully handling the cold-start period by suppressing anomalies when insufficient historical data exists (e.g., the DEAD_ZONE detector requires at least 5 recent ENTRY events before firing).

**Implementation:** Each detector has a minimum data requirement check before computing the anomaly. This prevents false positives during initial deployment.

---

### 6. API Design: Partial Success (207 Multi-Status)

**Problem:** The challenge requires batch ingest with deduplication and partial success — how should the HTTP status code reflect mixed outcomes?

**AI Influence:** An AI assistant pointed out that HTTP 207 Multi-Status (from WebDAV, but semantically correct here) is the appropriate status code for partial-success batch operations, rather than returning 200 with error details buried in the body or 400 for the entire batch.

**Implementation:** The `/events/ingest` endpoint returns 207 when any events are rejected and 200 when all are accepted. The response body always includes per-event error details.

---

### 7. Dashboard: Auto-Refresh vs. WebSocket

**Problem:** The challenge asks for real-time metric updates while events are being generated. Should the dashboard use polling or WebSocket?

**AI Influence:** An AI assistant recommended Streamlit's `st.rerun()` polling over WebSocket for the following reasons:
- Streamlit has no built-in WebSocket server; a custom WebSocket requires significant boilerplate
- The API is already stateless and horizontally scalable — polling is appropriate
- 30-second refresh intervals are sufficient for retail analytics (not millisecond trading)

**Implementation:** The dashboard uses `st.cache_data(ttl=30)` + `time.sleep(interval)` + `st.rerun()` to simulate real-time updates without blocking the event loop.

---

## Data Flow Detail

### Event Ingestion (Write Path)

```
POST /events/ingest (batch: up to 500 events)
    │
    ├─► Pydantic validation (EventIn schema)
    │
    ├─► IngestionService.ingest_batch()
    │     ├─► INSERT INTO events ON CONFLICT DO NOTHING  (dedup)
    │     ├─► _upsert_session() — update visitor_sessions read-model
    │     └─► Redis XADD → store_events stream
    │
    └─► BatchIngestResponse (accepted, rejected, errors)
```

### Metrics Query (Read Path)

```
GET /stores/{id}/metrics
    │
    └─► MetricsService.get_metrics()
          ├─► COUNT(DISTINCT visitor_id) WHERE is_staff=FALSE  → unique_visitors
          ├─► COUNT FILTER(made_purchase) / COUNT             → conversion_rate
          ├─► AVG(total_dwell_ms) WHERE exit_time IS NOT NULL → avg_dwell
          ├─► COUNT active billing sessions                   → queue_depth.current
          ├─► AVG(metadata->>'queue_depth') WHERE BILLING_JOIN → queue_depth.avg
          └─► COUNT(ABANDON) / COUNT(JOIN)                   → abandonment_rate
```

### Cross-Camera Visitor Deduplication

```
cam_entry: track_id=7 → OSNet embedding → cosine sim → visitor_id="abc-123"
cam_floor: track_id=3 → OSNet embedding → cosine sim → visitor_id="abc-123" (match!)
cam_billing: track_id=1 → OSNet embedding → cosine sim → visitor_id="abc-123" (match!)

Result: 1 unique visitor counted, not 3
```

---

## Production Readiness Checklist

| Requirement | Implementation |
|------------|----------------|
| Docker Compose | `docker-compose.yml` — postgres, redis, api, dashboard |
| Structured Logging | `structlog` JSON logs with trace_id, store_id, latency_ms |
| Graceful Degradation | Redis failure → API continues; DB failure → 503 on health |
| Idempotency | `ON CONFLICT DO NOTHING` on event_id PK |
| Test Coverage >70% | pytest suite covering all 6 endpoints + edge cases |
| DESIGN.md | This document |
| CHOICES.md | `docs/CHOICES.md` |

---

## Security Considerations (Production Hardening)

The following items are intentionally omitted for the challenge scope but required for production:

1. **Authentication** — Add OAuth2/JWT bearer token validation on all endpoints
2. **Rate limiting** — Add per-client rate limiting on `/events/ingest`
3. **CORS restriction** — Replace `allow_origins=["*"]` with specific dashboard origin
4. **Secrets management** — Move DB credentials to AWS Secrets Manager or Vault
5. **TLS** — Terminate HTTPS at the load balancer; internal services use HTTP

---

## Scalability Notes

- The API is stateless and can scale horizontally behind a load balancer
- asyncpg connection pool (min=2, max=10) should be tuned per replica count
- Redis Streams support consumer groups for parallel event processing
- The pipeline can process multiple cameras in parallel (one process per camera)
- For >100 cameras, consider a message queue (Kafka) between pipeline and API
