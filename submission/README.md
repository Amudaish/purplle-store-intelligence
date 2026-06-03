# Apex Retail Intelligence

> **Purplle Tech Challenge Submission**  
> End-to-end Store Intelligence Platform — from raw CCTV footage to production-ready analytics API and live dashboard.

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Problem Statement](#2-problem-statement)
3. [Architecture](#3-architecture)
4. [Tech Stack](#4-tech-stack)
5. [Docker Setup](#5-docker-setup)
6. [Local Setup (without Docker)](#6-local-setup-without-docker)
7. [API Endpoints](#7-api-endpoints)
8. [Dashboard Features](#8-dashboard-features)
9. [AI-Assisted Decisions](#9-ai-assisted-decisions)
10. [Folder Structure](#10-folder-structure)
11. [Future Improvements](#11-future-improvements)

---

## 1. Project Overview

Apex Retail Intelligence converts raw CCTV footage from physical stores into actionable retail analytics. The platform tracks every visitor from store entry through zone exploration, billing queue, and final purchase — computing the offline conversion funnel in real time.

**North star metric:** Offline Conversion Rate = (Visitors who made a purchase) / (Total unique visitors)

The system is composed of four loosely coupled layers:

| Layer | Technology | Purpose |
|---|---|---|
| Detection Pipeline | YOLOv8s + ByteTrack + OSNet | Converts raw video into structured events |
| Intelligence API | FastAPI + asyncpg + PostgreSQL | Ingests events, computes analytics |
| Streaming Bus | Redis Streams | Decouples pipeline from downstream consumers |
| Live Dashboard | Streamlit + Plotly | Real-time command centre for store managers |

---

## 2. Problem Statement

Apex Retail operates **40 stores across 8 cities**. Online analytics are mature, but **offline stores are a data blind spot**. Unlike e-commerce, physical stores have no native click stream — every customer journey is invisible.

Key challenges:
- **No visitor identity** — faces are blurred, no badges or loyalty cards scanned at entry
- **Multi-camera deduplication** — the same person passes through 3 cameras (entry, floor, billing); they must be counted once
- **Staff contamination** — store employees walk the floor constantly and must be excluded from all customer metrics
- **Edge cases** — group entry, re-entry, partial occlusion, billing queue abandonment, zero-traffic periods
- **Real-time requirement** — store managers need live KPIs, not next-day reports

---

## 3. Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│  CCTV Cameras  (5 stores × 3 cameras = 15 feeds)                   │
│  Entry Camera · Main Floor Camera · Billing Area Camera            │
└────────────────────────────┬────────────────────────────────────────┘
                             │ MP4 / RTSP  (1080p @ 15 FPS)
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Detection Pipeline  (pipeline/)                                    │
│                                                                     │
│  ┌──────────┐   ┌───────────┐   ┌────────┐   ┌──────────────────┐  │
│  │ YOLOv8s  │→  │ ByteTrack │→  │ OSNet  │→  │  Zone Engine +   │  │
│  │ detector │   │  tracker  │   │ Re-ID  │   │ Session Manager  │  │
│  └──────────┘   └───────────┘   └────────┘   └────────┬─────────┘  │
│                                                        │            │
│                                            EventEmitter │            │
└────────────────────────────────────────────────────────┼────────────┘
                                                         │
                              ┌──────────────────────────┘
                              │  Redis XADD + JSONL
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Intelligence API  (api/)   FastAPI + asyncpg                       │
│                                                                     │
│  POST /events/ingest    →  IngestionService                         │
│  GET  /stores/{id}/metrics  →  MetricsService                       │
│  GET  /stores/{id}/funnel   →  FunnelService                        │
│  GET  /stores/{id}/heatmap  →  HeatmapService                       │
│  GET  /stores/{id}/anomalies→  AnomalyService                       │
│  GET  /health                                                       │
└───────────────────────────┬─────────────────────────────────────────┘
                            │ HTTP + JSON
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Live Dashboard  (dashboard/)   Streamlit + Plotly                  │
│                                                                     │
│  Command Strip · KPI Cards · Operations Tab · Journey Analytics     │
│  Queue Intelligence · Risk & Anomalies · Live Event Feed            │
└─────────────────────────────────────────────────────────────────────┘
```

### Data Flow — Write Path (Event Ingestion)

```
POST /events/ingest (batch ≤ 500)
    │
    ├─► Pydantic v2 validation
    │
    ├─► IngestionService.ingest_batch()
    │     ├─► INSERT INTO events ON CONFLICT DO NOTHING   (idempotent dedup)
    │     ├─► _upsert_session()  →  update visitor_sessions read-model
    │     │     ├── reached_billing  ← set on BILLING_QUEUE_JOIN
    │     │     ├── made_purchase    ← set by POS matcher
    │     │     └── zones_visited[]  ← appended on ZONE_ENTER
    │     └─► Redis XADD  →  store_events stream
    │
    └─► BatchIngestResponse { accepted, rejected, errors }
```

### Data Flow — Read Path (Metrics Query)

```
GET /stores/{id}/metrics
    │
    └─► MetricsService.get_metrics()
          ├─► COUNT(DISTINCT visitor_id) WHERE is_staff=FALSE  → unique_visitors
          ├─► COUNT FILTER(made_purchase) / COUNT              → conversion_rate
          ├─► AVG(total_dwell_ms) WHERE exit_time IS NOT NULL  → avg_dwell_time_ms
          ├─► COUNT active billing sessions                    → queue_depth.current
          └─► COUNT(ABANDON) / COUNT(JOIN)                     → abandonment_rate
```

### Cross-Camera Deduplication

```
cam_entry:   track_id=7  →  OSNet embedding  →  cosine similarity  →  visitor_id="abc-123"
cam_floor:   track_id=3  →  OSNet embedding  →  cosine similarity  →  visitor_id="abc-123" ✓
cam_billing: track_id=1  →  OSNet embedding  →  cosine similarity  →  visitor_id="abc-123" ✓

Result: 1 unique visitor counted across all cameras, not 3.
```

---

## 4. Tech Stack

### Detection Pipeline

| Component | Library | Rationale |
|---|---|---|
| Object Detection | YOLOv8s (ultralytics) | Best accuracy/speed tradeoff on CPU; ~35 FPS at 640px |
| Multi-Object Tracking | ByteTrack (supervision) | Two-stage association handles occlusion in crowded retail scenes |
| Cross-Camera Re-ID | OSNet-x0.25 (ONNX) | 1.2 MB model; fast CPU inference; colour histogram fallback |
| Staff Classification | HSV histogram + dwell heuristic | Zero-shot; no labelled training data required |
| Zone Detection | Polygon intersection (custom) | Per-store zone geometry from `store_layout.json` |

### Intelligence API

| Component | Library / Version |
|---|---|
| Framework | FastAPI 0.115 |
| PostgreSQL driver | asyncpg 0.29 (native async; 2–5× faster than psycopg2) |
| Validation | Pydantic v2 |
| Logging | structlog (JSON, with trace_id + latency_ms) |
| Redis client | redis.asyncio 5.1 |
| Settings | pydantic-settings (env vars + .env) |

### Infrastructure

| Service | Image |
|---|---|
| PostgreSQL | postgres:16-alpine |
| Redis | redis:7-alpine |
| API | python:3.11-slim (custom) |
| Dashboard | python:3.11-slim (custom) |

### Dashboard

| Component | Library |
|---|---|
| Framework | Streamlit |
| Charts | Plotly |
| HTTP client | httpx |

---

## 5. Docker Setup

### Prerequisites

- Docker Desktop ≥ 4.x  
- Docker Compose ≥ 2.x

### Quick Start

```bash
# Clone the repository
git clone <repo-url>
cd "Antigravity works"

# (Optional) copy and review environment variables
cp .env.example .env

# Start all services
docker compose up
```

This starts:

| Container | Service | Port |
|---|---|---|
| `store_intel_postgres` | PostgreSQL 16 | 5432 |
| `store_intel_redis` | Redis 7 | 6379 |
| `store_intel_api` | FastAPI | **8000** |
| `store_intel_dashboard` | Streamlit | **8501** |

Services start in dependency order: postgres and redis reach `healthy` before the API starts. The API runs its schema migration on first boot and becomes healthy before the dashboard starts.

### Verify All Services Are Healthy

```bash
docker compose ps
```

Expected output:
```
NAME                   STATUS
store_intel_postgres   Up (healthy)
store_intel_redis      Up (healthy)
store_intel_api        Up (healthy)
store_intel_dashboard  Up
```

### URLs

| Service | URL |
|---|---|
| API (interactive docs) | http://localhost:8000/docs |
| API (ReDoc) | http://localhost:8000/redoc |
| API Health | http://localhost:8000/health |
| Live Dashboard | http://localhost:8501 |

### Seed Data (optional)

```bash
# Load store layouts
python scripts/load_store_layout.py

# Load POS transaction data
python scripts/load_pos_data.py

# Ingest sample events
python scripts/seed_and_ingest.py
```

### Run the Detection Pipeline

```bash
# Process a single camera feed
docker compose run --rm pipeline \
  python -m pipeline.main \
  --video data/CAM\ 1.mp4 \
  --store store_001 \
  --camera cam_entry \
  --redis redis://redis:6379/0 \
  --output data/events_output.jsonl \
  --start-time 2026-05-29T10:00:00 \
  --frame-skip 2
```

---

## 6. Local Setup (without Docker)

### Requirements

- Python 3.11
- PostgreSQL 16 running locally
- Redis 7 running locally

### Installation

```bash
# Create virtual environment
python3.11 -m venv .venv
source .venv/bin/activate

# Install API dependencies
pip install -r api/requirements.txt

# Install pipeline dependencies (optional)
pip install -r pipeline/requirements.txt
```

### Environment

```bash
cp .env.example .env
# Edit .env to point DATABASE_URL and REDIS_URL at your local instances
```

### Run

```bash
# API
PYTHONPATH=$(pwd) uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

# Dashboard (separate terminal)
PYTHONPATH=$(pwd)/dashboard streamlit run dashboard/app.py
```

### Run Tests

```bash
# All tests (requires running postgres + redis)
pytest tests/ -v

# With coverage report
pytest tests/ --cov=api --cov-report=term-missing
```

---

## 7. API Endpoints

All endpoints are documented interactively at **http://localhost:8000/docs**.

### `POST /events/ingest`

Batch ingest store events from the detection pipeline.

- Accepts up to **500 events** per request
- **Idempotent** — duplicate `event_id` values are silently ignored (`ON CONFLICT DO NOTHING`)
- Returns **HTTP 200** if all events accepted; **HTTP 207 Multi-Status** if any are rejected
- Per-event structured error detail in response body

**Request body:**
```json
{
  "events": [
    {
      "event_id": "uuid4",
      "store_id": "store_001",
      "camera_id": "cam_entry",
      "visitor_id": "uuid4",
      "event_type": "ENTRY",
      "timestamp": "2026-05-29T10:00:00Z",
      "zone_id": null,
      "dwell_ms": null,
      "is_staff": false,
      "confidence": 0.87,
      "metadata": {}
    }
  ]
}
```

**Supported event types:** `ENTRY` · `EXIT` · `REENTRY` · `ZONE_ENTER` · `ZONE_EXIT` · `ZONE_DWELL` · `BILLING_QUEUE_JOIN` · `BILLING_QUEUE_ABANDON`

---

### `GET /stores/{store_id}/metrics`

Returns aggregated KPIs for a store over a time window (default: last 24 hours).

**Response:**
```json
{
  "store_id": "store_001",
  "period_start": "2026-05-29T00:00:00Z",
  "period_end": "2026-05-29T23:59:59Z",
  "unique_visitors": 124,
  "conversion_rate": 0.142,
  "avg_dwell_time_ms": 437000,
  "queue_depth": {
    "current": 3,
    "avg": 2.1
  },
  "abandonment_rate": 0.18
}
```

Staff are **excluded** from all metrics.

---

### `GET /stores/{store_id}/funnel`

Returns the 4-stage conversion funnel with drop-off percentages.

**Funnel stages:**
1. **Entry** — unique visitors who entered the store
2. **Zone Visit** — visitors who entered at least one named zone
3. **Billing Queue** — visitors who joined the billing queue
4. **Purchase** — visitors matched to a POS transaction

**Response:**
```json
{
  "store_id": "store_001",
  "funnel": [
    { "stage": "entry",         "visitors": 124, "drop_off_pct": 0.0  },
    { "stage": "zone_visit",    "visitors": 108, "drop_off_pct": 12.9 },
    { "stage": "billing_queue", "visitors":  42, "drop_off_pct": 61.1 },
    { "stage": "purchase",      "visitors":  18, "drop_off_pct": 57.1 }
  ],
  "reentry_count": 7
}
```

---

### `GET /stores/{store_id}/heatmap`

Returns zone-level visit density and dwell time for the store floor plan.

Includes a `data_confidence` flag when fewer than 20 sessions exist (cold-start warning).

**Response:**
```json
{
  "store_id": "store_001",
  "zones": [
    {
      "zone_id": "zone_cosmetics",
      "visit_count": 87,
      "avg_dwell_ms": 62000,
      "heat_score": 0.91
    }
  ],
  "data_confidence": "high"
}
```

---

### `GET /stores/{store_id}/anomalies`

Detects operational anomalies using statistical baseline comparison.

**Three detectors:**

| Anomaly | Trigger | Severity |
|---|---|---|
| `QUEUE_SPIKE` | Current queue depth > 30-day average × threshold | high |
| `CONVERSION_DROP` | Today's rate < 30-day baseline × threshold | medium |
| `DEAD_ZONE` | Zone visit count < minimum in last hour when store is active | low |

**Response:**
```json
{
  "store_id": "store_001",
  "anomalies": [
    {
      "anomaly_type": "QUEUE_SPIKE",
      "severity": "high",
      "detected_at": "2026-05-29T14:32:00Z",
      "details": { "current_depth": 9, "avg_depth": 2.3 },
      "suggested_action": "Open an additional billing counter immediately."
    }
  ]
}
```

---

### `GET /health`

Returns the health of all system dependencies.

**Response:**
```json
{
  "status": "ok",
  "db_status": "ok",
  "redis_status": "ok",
  "last_event_at": "2026-05-29T14:30:00Z",
  "stale_feed": false,
  "uptime_s": 3612.4
}
```

- `status` is `"degraded"` and a `"warning": "STALE_FEED"` key is added if no events have arrived in the last 10 minutes
- `status` is `"error"` and HTTP 503 is returned if the database or Redis is unreachable

---

## 8. Dashboard Features

The Streamlit dashboard runs at **http://localhost:8501** and auto-refreshes every 30 seconds.

### Command Strip (persistent header)

Live KPI bar visible across all tabs:

| KPI | Description |
|---|---|
| Visitors | Unique customer count (staff excluded) |
| Conversion | Purchase rate with colour coding (green ≥15%, amber ≥8%, red <8%) |
| Abandonment | Billing queue abandonment rate |
| Avg Dwell | Average in-store time in seconds |
| Queue | Current billing queue depth |
| Store Score | Composite health score (0–100) |
| Hot Zone | Highest-traffic zone name and heat percentage |
| System Status | LIVE / STALE / ERROR pill with uptime and alert count |

### Tab 1 — Operations

- **Revenue Pulse** — conversion rate, basket value trend, and POS match statistics
- **Store Floor Intelligence** — interactive zone heatmap with visit density and dwell time
- **AI Decision Center** — rule-based action recommendations derived from live metrics (see §9)
- **Live Operational Feed** — scrolling stream of the last 30 events with colour-coded event types

### Tab 2 — Journey Analytics

- 4-stage conversion funnel (Plotly funnel chart) with absolute counts and drop-off percentages
- Zone engagement breakdown — top zones by visit count and average dwell
- Re-entry visitor tracking

### Tab 3 — Queue Intelligence

- Current vs. average queue depth
- Abandonment rate timeline
- Queue spike alert history

### Tab 4 — Risk & Anomalies

- Active anomaly cards with severity badges (`HIGH` / `MEDIUM` / `LOW`)
- Suggested remediation action per anomaly
- Historical anomaly log

---

## 9. AI-Assisted Decisions

All AI-assisted design decisions are documented in detail in [`docs/DESIGN.md`](docs/DESIGN.md) and [`docs/CHOICES.md`](docs/CHOICES.md). A summary follows.

### 1. CQRS Pattern for Analytics (AI-suggested)

**Problem:** Computing conversion rates from raw events requires expensive multi-join aggregations at read time.

**AI Influence:** An AI assistant suggested CQRS — maintaining a `visitor_sessions` read-model table updated progressively at write time. `reached_billing`, `made_purchase`, and `zones_visited` are set as events arrive, enabling O(1) funnel queries.

---

### 2. ByteTrack + OSNet Architecture (AI-validated)

**Problem:** Should Re-ID be integrated into the tracker?

**AI Influence:** An AI assistant confirmed the production-standard separation: ByteTrack handles within-camera temporal consistency (IoU-based, no model needed); OSNet handles cross-camera identity via embedding similarity. This keeps components independently testable and replaceable.

---

### 3. Session State Machine (AI-suggested)

**Problem:** When does a temporarily hidden visitor become an "exited" visitor?

**AI Influence:** An AI assistant recommended a formal state machine (`ABSENT → ACTIVE → EXITED → ACTIVE` via REENTRY) over naive time-window logic. `EXIT_TIMEOUT_FRAMES = 150` (10 s at 15 FPS) distinguishes occlusion from genuine exit, preventing false EXIT/ENTRY pairs.

---

### 4. Zero-Shot Staff Classification (AI-proposed)

**Problem:** No labelled training data for staff vs. customer classification.

**AI Influence:** An AI assistant proposed a cascaded two-signal classifier:
1. **Primary:** HSV colour histogram — if >55% of upper-body pixels fall in hue range 80–110 (teal/cyan, typical retail uniform), classify as staff
2. **Fallback:** Continuous in-store presence >60 s without shopping behaviour → staff

The AI assistant helped tune the HSV hue threshold to match Apex Retail's uniform colour.

---

### 5. HTTP 207 Multi-Status for Partial Batch Success (AI-suggested)

**Problem:** How should a batch ingest endpoint signal mixed outcomes?

**AI Influence:** An AI assistant pointed out that HTTP 207 Multi-Status (originally WebDAV) is semantically correct for partial-success batch operations — more precise than burying errors in a 200 body or rejecting the entire batch with 400.

---

### 6. Polling Dashboard over WebSocket (AI-recommended)

**Problem:** Real-time dashboard updates — polling vs. WebSocket?

**AI Influence:** An AI assistant recommended Streamlit's `st.rerun()` polling: Streamlit has no built-in WebSocket server; the API is stateless and horizontally scalable; 30-second intervals are sufficient for retail analytics. Result: `st.cache_data(ttl=30)` + `st.rerun()` — no boilerplate, no additional server.

---

### 7. Rule-Based Anomaly Detection Over ML (AI-guided)

**Problem:** Statistical anomaly detection requires historical data. Only 20 minutes of video per camera are provided.

**AI Influence:** An AI assistant recommended rule-based detectors with explicit cold-start suppression — each detector checks for sufficient data before firing (e.g., DEAD_ZONE requires at least 5 recent ENTRY events). ML-based approaches (Isolation Forest, Z-score) were rejected due to insufficient training data.

---

## 10. Folder Structure

```
Antigravity works/
│
├── api/                        # FastAPI Intelligence API
│   ├── config.py               # Settings (pydantic-settings, env vars)
│   ├── database.py             # asyncpg pool + idempotent schema init
│   ├── main.py                 # App factory + lifespan (startup/shutdown)
│   ├── middleware/             # StructuredLoggingMiddleware (JSON + trace_id)
│   ├── migrations/             # Alembic migration stubs
│   ├── models/                 # Pydantic request/response schemas
│   ├── routers/                # One file per endpoint
│   │   ├── anomalies.py        # GET /stores/{id}/anomalies
│   │   ├── funnel.py           # GET /stores/{id}/funnel
│   │   ├── health.py           # GET /health
│   │   ├── heatmap.py          # GET /stores/{id}/heatmap
│   │   ├── ingest.py           # POST /events/ingest
│   │   └── metrics.py          # GET /stores/{id}/metrics
│   └── services/               # Business logic
│       ├── anomaly_service.py  # QUEUE_SPIKE / CONVERSION_DROP / DEAD_ZONE
│       ├── funnel_service.py   # 4-stage funnel computation
│       ├── heatmap_service.py  # Zone heatmap aggregation
│       ├── ingestion.py        # Batch ingest + session upsert
│       ├── metrics_service.py  # KPI aggregation queries
│       └── pos_matcher.py      # POS transaction ↔ visitor session matching
│
├── pipeline/                   # CV Detection Pipeline
│   ├── main.py                 # CLI entry point (per-camera process)
│   ├── detector.py             # YOLOv8s wrapper
│   ├── tracker.py              # ByteTrack wrapper
│   ├── reid.py                 # OSNet Re-ID + Redis embedding store
│   ├── staff_classifier.py     # HSV histogram + dwell classifier
│   ├── zone_engine.py          # Polygon zone detection
│   ├── session_manager.py      # ABSENT/ACTIVE/EXITED state machine
│   └── event_emitter.py        # Structured event builder + Redis XADD
│
├── dashboard/                  # Streamlit Live Dashboard
│   ├── app.py                  # Page layout + tab routing
│   ├── data_layer.py           # All API calls and derived signals
│   ├── design_system.py        # CSS design tokens
│   └── components/             # Reusable dashboard components
│       ├── ai_action_center.py # AI Decision Center panel
│       ├── floor_intelligence.py # Zone heatmap panel
│       ├── journey_tab.py      # Funnel + zone engagement
│       ├── queue_tab.py        # Queue depth + abandonment
│       ├── revenue_pulse.py    # KPI + POS match panel
│       └── risk_tab.py         # Anomaly cards
│
├── tests/                      # Pytest test suite (>70% coverage)
│   ├── conftest.py             # Fixtures (test DB, event factories)
│   ├── assertions.py           # Challenge-provided assertions
│   ├── test_ingest.py          # Batch ingest + deduplication
│   ├── test_metrics.py         # KPI computation
│   ├── test_funnel.py          # Funnel stages
│   ├── test_heatmap.py         # Zone heatmap
│   ├── test_anomalies.py       # All three anomaly detectors
│   ├── test_health.py          # Health endpoint states
│   └── test_edge_cases.py      # Group entry, re-entry, staff, occlusion
│
├── scripts/                    # Utility scripts
│   ├── load_store_layout.py    # Seed store + zone data from JSON
│   ├── load_pos_data.py        # Seed POS transactions from CSV
│   ├── seed_and_ingest.py      # Generate + ingest sample events
│   └── run_pipeline_all.sh     # Process all 5 cameras in parallel
│
├── docs/
│   ├── DESIGN.md               # System architecture + AI decisions
│   └── CHOICES.md              # Technical decision log with alternatives
│
├── data/                       # Input data (gitignored large files)
│   ├── store_layout.json
│   ├── pos_transactions.csv
│   └── sample_events.jsonl
│
├── docker-compose.yml          # Full stack orchestration
├── Dockerfile.api              # API container
├── Dockerfile.dashboard        # Dashboard container
├── Dockerfile.pipeline         # Pipeline container (run per camera)
├── .env.example                # Environment variable template
└── yolov8s.pt                  # Pre-downloaded YOLOv8s weights
```

---

## 11. Future Improvements

### Scalability

- **Kafka** instead of Redis Streams for >100 cameras — consumer groups with lag monitoring, at-least-once delivery guarantees, and replay capability
- **Horizontal API scaling** behind NGINX with sticky sessions; asyncpg pool per replica tuned to `max_connections / replica_count`
- **TimescaleDB** hypertable on `events(timestamp)` for efficient time-range queries as event volume grows beyond tens of millions

### ML Pipeline

- **GPU inference** with TensorRT-optimised YOLOv8 for real-time processing without frame skipping
- **Transformer-based Re-ID** (e.g., TransReID) for higher cross-camera accuracy in challenging lighting conditions
- **Trained staff classifier** once labelled data is collected — a lightweight binary CNN on upper-body crops would outperform the heuristic approach

### Analytics

- **Predictive queue management** — LSTM model forecasting queue depth 15 minutes ahead, triggering pre-emptive counter opening
- **A/B testing framework** for store layout changes — compare conversion rates before/after planogram updates using the existing zone visit data
- **Customer segmentation** — cluster anonymous visitor behaviour patterns (dwell time, zone sequence, return frequency) without PII

### Production Hardening

- **Authentication** — OAuth2 / JWT bearer tokens on all API endpoints; per-store access control
- **Rate limiting** — per-client throttling on `/events/ingest` (token bucket, enforced at Redis)
- **CORS restriction** — replace `allow_origins=["*"]` with specific dashboard and admin origins
- **Secrets management** — AWS Secrets Manager or HashiCorp Vault for database credentials and API keys
- **TLS** — terminate HTTPS at load balancer; internal services communicate over HTTP within the VPC
- **Alembic migrations** — replace raw DDL in `database.py` with versioned Alembic migrations for safe schema evolution in production

### Observability

- **Prometheus metrics** — request rate, error rate, latency histograms, pool utilisation (expose via `/metrics`)
- **Grafana dashboards** — operational SLO dashboards, alert routing to PagerDuty for `QUEUE_SPIKE HIGH` severity
- **Distributed tracing** — propagate `trace_id` from pipeline → API → dashboard for end-to-end latency attribution

---

## Appendix — Environment Variables

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://store_intel:...@postgres:5432/store_intelligence` | asyncpg connection string |
| `DATABASE_URL_SYNC` | `postgresql://store_intel:...@postgres:5432/store_intelligence` | psycopg2 connection string |
| `REDIS_URL` | `redis://redis:6379/0` | Redis connection string |
| `API_HOST` | `0.0.0.0` | Uvicorn bind host |
| `API_PORT` | `8000` | Uvicorn bind port |
| `LOG_LEVEL` | `INFO` | Logging verbosity |
| `STALE_FEED_THRESHOLD_MINUTES` | `10` | Minutes before /health reports STALE_FEED |
| `MAX_BATCH_SIZE` | `500` | Maximum events per ingest request |
| `POS_MATCH_WINDOW_MINUTES` | `5` | Time window for POS↔session matching |

---

*Built for the Purplle Tech Challenge · Apex Retail Intelligence Platform*
