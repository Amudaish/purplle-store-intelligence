# CHOICES.md — Technical Decision Log

## Detection Model Choice

### Decision: YOLOv8s (Small) via ultralytics

| Option | Accuracy | Speed (CPU) | Notes |
|--------|----------|-------------|-------|
| YOLOv8n | Medium | Very fast | Sacrifices accuracy at 1080p |
| **YOLOv8s** | **Good** | **Fast** | **Best accuracy-speed tradeoff on CPU** |
| YOLOv8m | High | Moderate | Overkill for 15 FPS requirement |
| RT-DETR | Very High | Slow | Requires GPU; no CPU-friendly ONNX export easily |

**Rationale:** The challenge specifies 1080p @ 15 FPS footage. YOLOv8s achieves ~35+ FPS on CPU for 640px inference, comfortably processing 15 FPS video with frame-skip=2. It achieves ~45 AP on COCO persons — sufficient for crowded retail environments.

**AI Suggestion considered:** An AI assistant suggested RT-DETR for superior accuracy. Rejected because:
- RT-DETR requires GPU for real-time performance
- The challenge explicitly lists YOLOv8 in the suggested stack
- Operational complexity of managing a GPU inference container is disproportionate

**Final decision:** YOLOv8s — best tradeoff for the stated constraints.

---

## Tracker Choice

### Decision: ByteTrack (via supervision library)

| Option | Re-ID dependency | Occlusion handling | Maturity |
|--------|-----------------|-------------------|----------|
| **ByteTrack** | **None (IoU-based)** | **Strong (two-stage)** | **Production-grade** |
| DeepSORT | Requires Re-ID model | Good | Well-known but slower |
| SORT | None | Weak | Too simple for retail occlusion |
| OC-SORT | None | Very strong | More complex, less tooling |

**Rationale:** ByteTrack's two-stage association (high-confidence detections first, then low-confidence) is specifically designed for crowded scenes with partial occlusion — exactly the retail floor scenario. It requires no Re-ID model for within-camera tracking, reserving OSNet for cross-camera deduplication only.

**AI Suggestion considered:** DeepSORT was suggested as the default well-known option. Rejected because ByteTrack consistently outperforms DeepSORT in crowded multi-person tracking benchmarks and has simpler operational requirements.

---

## Re-ID Model Choice

### Decision: OSNet-x0.25 (ONNX, histogram fallback)

| Option | Accuracy | Size | Inference speed |
|--------|----------|------|----------------|
| **OSNet-x0.25** | **Good** | **Small (1.2 MB)** | **Fast on CPU** |
| OSNet-x1.0 | Higher | Larger (5.3 MB) | Slower |
| ResNet50-IBN | High | 25 MB | Slow |
| Market1501 features | Baseline | N/A | Fast |

**Rationale:** The challenge requires cross-camera deduplication with 5 stores × 3 cameras. OSNet-x0.25 was specifically designed for resource-constrained deployment. The ONNX export allows inference without torchreid as a dependency. A colour-histogram fallback ensures the pipeline always produces a visitor_id even if the ONNX model is unavailable.

---

## Event Schema Design

### Decision: Flat schema with rich metadata field

```json
{
  "event_id":   "uuid4",
  "store_id":   "store_001",
  "camera_id":  "cam_entry",
  "visitor_id": "uuid4",
  "event_type": "ENTRY",
  "timestamp":  "ISO 8601 UTC",
  "zone_id":    null,
  "dwell_ms":   null,
  "is_staff":   false,
  "confidence": 0.87,
  "metadata":   {}
}
```

**Alternatives considered:**
1. **Separate tables per event type** — rejected: over-normalisation increases join complexity for analytics queries
2. **Nested payload object** — rejected: makes SQL aggregations harder; JSONB metadata field handles extensibility
3. **EAV (entity-attribute-value)** — rejected: known anti-pattern for analytics workloads

**AI Suggestion considered:** Using an event sourcing pattern with separate aggregate tables. Adopted partially: the `visitor_sessions` table is a read-model that is progressively updated from events, avoiding expensive on-the-fly aggregations.

**Final decision:** Flat schema matches the challenge spec exactly. `metadata` JSONB field handles event-specific data (e.g. `queue_depth` on BILLING_QUEUE_JOIN) without schema migration.

---

## API Architecture Choice

### Decision: FastAPI + asyncpg (no ORM)

| Option | Performance | Code complexity | Async support |
|--------|------------|----------------|---------------|
| **FastAPI + asyncpg** | **Excellent** | **Low** | **Native** |
| FastAPI + SQLAlchemy Async | Good | Medium | Yes |
| Django REST + psycopg2 | Moderate | High | Limited |
| Flask + SQLAlchemy | Good | Medium | Limited |

**Rationale:**
- asyncpg is the fastest PostgreSQL driver for Python, outperforming psycopg2 by 2–5×
- No ORM means direct SQL control for complex analytics aggregations (window functions, FILTER clauses)
- FastAPI's native Pydantic v2 integration provides schema validation with no extra libraries
- The challenge explicitly suggests FastAPI

**AI Suggestion considered:** SQLAlchemy Async was suggested for its migration tooling (Alembic). Partially adopted: Alembic is included in requirements.txt but schema is managed by raw DDL in database.py for simplicity in this challenge context.

---

## Staff Classification Approach

### Decision: HSV colour histogram + dwell-time fallback

**Alternatives considered:**
1. **Trained binary classifier** — rejected: no labelled training data provided; requires model training infrastructure
2. **Badge/ID card detection** — rejected: requires camera resolution and angle cooperation; faces are blurred in the dataset
3. **Entry-time pattern** (staff enter before store opens) — rejected: too fragile for 20-minute video clips
4. **Colour histogram** — adopted as primary: Apex Retail uniforms have a distinctive brand colour

**Heuristics chosen:**
- Primary: If >55% of upper-body crop pixels fall within the staff uniform hue range (HSV: 80–110 = teal/cyan), classify as staff
- Fallback: Continuous in-store presence for >60 seconds without typical shopping behaviour → staff

---

## Database Schema Decisions

### Decision: visitor_sessions as a read-model aggregate

Rather than computing conversion funnels purely from events at query time (which would require expensive multi-join queries), the `visitor_sessions` table is maintained as a running aggregate that is updated on each event ingest. This trades write complexity for read performance.

**Key fields:**
- `reached_billing` — set True on BILLING_QUEUE_JOIN (enables funnel stage 3)
- `made_purchase` — set True by POS matcher (enables funnel stage 4)
- `zones_visited` — PostgreSQL TEXT[] for zone visit history without a join table
- `is_reentry` — set True on REENTRY events for funnel re-entry reporting

---

## Streaming Architecture

### Decision: Redis Streams (XADD/XREAD)

**Alternatives considered:**
- Kafka — rejected: operational overhead for a 5-store pilot; Redis Streams provide the same ordered event log semantics
- PostgreSQL LISTEN/NOTIFY — rejected: limited to 8KB payloads and poor replay capability
- WebSocket direct from pipeline — rejected: coupling between CV pipeline and dashboard

**Redis Streams advantages:**
- Persistent ordered event log (unlike Redis Pub/Sub which drops messages)
- Consumer groups for reliable delivery to multiple downstream consumers
- `maxlen` trimming to prevent unbounded memory growth
- Native support in both redis-py (sync) and redis.asyncio

---

## Anomaly Detection Approach

### Decision: Statistical baseline comparison (no ML)

**Three detectors implemented:**
1. **QUEUE_SPIKE**: current depth vs. 30-day average × multiplier
2. **CONVERSION_DROP**: today's rate vs. 30-day baseline × threshold
3. **DEAD_ZONE**: zone visits in last hour below minimum when store is active

**Alternative considered:** Isolation Forest or Z-score anomaly detection. Rejected because:
- Requires sufficient historical data (30+ days) to calibrate
- The challenge only provides 20 minutes of video per camera
- Rule-based detection is transparent and debuggable

**AI Suggestion considered:** Using a sliding window IQR approach. Adopted partially: the 30-day window acts as a rolling baseline.
