...Goal

Build a complete end-to-end Store Intelligence Platform starting from raw CCTV footage and ending with a production-ready analytics API and live dashboard.

Input:

Raw anonymized CCTV footage
store_layout.json
pos_transactions.csv
sample_events.jsonl
assertions.py

Output:

Detection pipeline
Event stream
Intelligence API
Live dashboard
Dockerized deployment

⸻

Business Problem

Apex Retail operates 40 stores across 8 cities.

Online analytics are mature, but offline stores are a data blind spot.

The objective is to generate accurate offline store analytics from CCTV footage and POS transaction data.

North Star Metric:

Offline Conversion Rate

Conversion Rate =
Visitors who completed a purchase /
Total unique visitors

⸻

System Pipeline

Raw CCTV Clips
→ Detection Layer
→ Event Stream
→ Intelligence API
→ Live Dashboard

⸻

Dataset

CCTV Clips

5 stores
3 cameras per store
Entry Camera
Main Floor Camera
Billing Area Camera
20 minutes per camera
1080p
15 FPS
Faces blurred
No audio

Additional Files

store_layout.json

Zone definitions
Camera coverage
Open hours

pos_transactions.csv

store_id
transaction_id
timestamp
basket_value_inr

sample_events.jsonl

Example event schema

assertions.py

Example tests

⸻

Edge Cases

Must handle:

Group Entry
Count individuals
Not groups
Staff Movement
Detect staff
Exclude from analytics
Re-entry
Same customer leaves and returns
Generate REENTRY event
Partial Occlusion
Customer partially hidden
Billing Queue Buildup
Queue depth tracking
Queue abandonment
Empty Store Periods
Zero traffic periods
Camera Overlap
Cross-camera deduplication

⸻

Part A - Detection Pipeline

Generate structured events from CCTV footage.

Recommended technologies:

YOLOv8 / YOLOv9 / RT-DETR
ByteTrack / DeepSORT
OSNet Re-ID
VLMs optional

Required Event Types:

ENTRY
EXIT
REENTRY
ZONE_ENTER
ZONE_EXIT
ZONE_DWELL
BILLING_QUEUE_JOIN
BILLING_QUEUE_ABANDON

⸻

Event Schema

{
event_id,
store_id,
camera_id,
visitor_id,
event_type,
timestamp,
zone_id,
dwell_ms,
is_staff,
confidence,
metadata
}

Requirements:

UUID event IDs
ISO timestamps
Confidence scores
Staff classification
Session tracking

⸻

Part B - Intelligence API

POST /events/ingest

Requirements:

Batch ingest
Up to 500 events
Deduplication
Idempotent
Partial success
Structured errors

GET /stores/{id}/metrics

Return:

Unique visitors
Conversion rate
Average dwell time
Queue depth
Abandonment rate

Exclude staff.

⸻

GET /stores/{id}/funnel

Funnel:

Entry
→ Zone Visit
→ Billing Queue
→ Purchase

Requirements:

Session-based
Drop-off percentages
Re-entry handling

⸻

GET /stores/{id}/heatmap

Return:

Zone visits
Average dwell
Heat score

Include:

data_confidence

when sessions < 20.

⸻

GET /stores/{id}/anomalies

Detect:

Queue Spike
Conversion Drop
Dead Zone

Return:

Severity
Suggested Action

⸻

GET /health

Return:

Service status
Last event timestamp
STALE_FEED warning

Trigger warning if event lag > 10 minutes.

⸻

Part C - Production Readiness

Requirements:

Docker Compose
Structured Logging
Graceful Degradation
Idempotency
Test Coverage >70%
README

Logging fields:

trace_id
store_id
endpoint
latency_ms
event_count
status_code

⸻

Part D - AI Engineering

Required Documents:

DESIGN.md

Must include:

AI-Assisted Decisions

Explain where AI influenced architecture.

CHOICES.md

Explain:

Detection model choice
Event schema design
API architecture choice

Include:

Alternatives considered
AI suggestions
Final decision

Tests

Every test file must contain:

PROMPT:

…

CHANGES MADE:

…

⸻

Part E - Bonus

Live Dashboard

Show real-time metric updates while events are being generated.

Web dashboard preferred over terminal dashboard.

⸻

Acceptance Criteria

docker compose up must:

Start successfully
Accept event ingestion
Serve metrics endpoint
Include DESIGN.md
Include CHOICES.md

⸻

Suggested Stack

Detection:

YOLOv8
ByteTrack
OSNet

Backend:

FastAPI

Database:

PostgreSQL

Validation:

Pydantic

Streaming:

Redis Streams

Dashboard:

Streamlit

Testing:

Pytest

Containerization:


Docker Compose

Logging:

Structured JSON Logs

⸻

Suggested Development Order

Architecture Design
Database Schema
Event Schema
FastAPI Skeleton
Event Ingestion
Metrics Endpoint
Funnel Endpoint
Heatmap Endpoint
Anomaly Detection
Detection Pipeline
Re-ID Logic
Dashboard
Tests
Documentation
Dockerization