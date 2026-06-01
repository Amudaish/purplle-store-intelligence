#!/usr/bin/env bash
# =============================================================================
# scripts/run_pipeline_all.sh
#
# Runs the CCTV detection pipeline for all 5 camera files in parallel.
# Each camera gets its own background process.  All output logs are written
# to data/logs/ and events are appended to data/events_output.jsonl.
#
# Prerequisites
# -------------
#   pip install -r pipeline/requirements.txt
#   Redis must be running on localhost:6379
#     → docker run -d -p 6379:6379 redis:7-alpine
#
# Usage
# -----
#   bash scripts/run_pipeline_all.sh [--model yolov8n.pt] [--frame-skip 2] [--device cpu]
#
# Defaults
# --------
#   model      : yolov8s.pt   (auto-downloaded on first run)
#   frame-skip : 2            (process every 2nd frame = 7.5 effective FPS)
#   device     : cpu
#   redis      : redis://localhost:6379/0
#   start-time : 2026-05-29T10:00:00  (matches POS transaction timestamps)
# =============================================================================

set -euo pipefail

# ── Configurable defaults ──────────────────────────────────────────────────────
MODEL="${MODEL:-yolov8s.pt}"
FRAME_SKIP="${FRAME_SKIP:-2}"
DEVICE="${DEVICE:-cpu}"
REDIS="${REDIS_URL:-redis://localhost:6379/0}"
LAYOUT="data/store_layout.json"
OUTPUT="data/events_output.jsonl"
START_TIME="2026-05-29T10:00:00"
CONF="0.40"

# ── Parse optional CLI flags ───────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --model)      MODEL="$2"; shift 2 ;;
        --frame-skip) FRAME_SKIP="$2"; shift 2 ;;
        --device)     DEVICE="$2"; shift 2 ;;
        --redis)      REDIS="$2"; shift 2 ;;
        *) echo "Unknown flag: $1"; exit 1 ;;
    esac
done

# ── Setup ──────────────────────────────────────────────────────────────────────
mkdir -p data/logs

echo "========================================================"
echo " Apex Retail — CCTV Pipeline (All 5 Cameras)"
echo "========================================================"
echo " Model      : $MODEL"
echo " Frame-skip : $FRAME_SKIP (every ${FRAME_SKIP}th frame)"
echo " Device     : $DEVICE"
echo " Redis      : $REDIS"
echo " Output     : $OUTPUT"
echo " Start time : $START_TIME"
echo "========================================================"
echo ""

# ── Seed the stores table (idempotent — safe to run every time) ───────────────
echo "Pre-flight: seeding stores table from $LAYOUT ..."
python3.11 scripts/seed_and_ingest.py \
    --layout "$LAYOUT" \
    --skip-ingest 2>&1 | grep -E '(INFO|WARNING|ERROR)'
echo ""

# Verify all video files exist before starting any process
MISSING=0
for CAM_NUM in 1 2 3 4 5; do
    VIDEO="data/CAM ${CAM_NUM}.mp4"
    if [[ ! -f "$VIDEO" ]]; then
        echo "ERROR: Missing video file: $VIDEO"
        MISSING=1
    else
        SIZE=$(du -h "$VIDEO" | cut -f1)
        echo "  ✓  $VIDEO  ($SIZE)"
    fi
done

if [[ $MISSING -eq 1 ]]; then
    echo ""
    echo "Aborting: one or more video files are missing."
    exit 1
fi
echo ""

# ── Camera → Store mapping ────────────────────────────────────────────────────
# CAM 1 → store_001 (Koramangala, Bangalore)  cam_entry
# CAM 2 → store_002 (Indiranagar, Bangalore)  cam_entry
# CAM 3 → store_003 (Bandra, Mumbai)          cam_entry
# CAM 4 → store_004 (Connaught Place, Delhi)  cam_entry
# CAM 5 → store_005 (Park Street, Kolkata)    cam_entry

declare -A STORE_MAP=(
    [1]="store_001"
    [2]="store_002"
    [3]="store_003"
    [4]="store_004"
    [5]="store_005"
)

declare -A STORE_LABELS=(
    [1]="Koramangala, Bangalore"
    [2]="Indiranagar, Bangalore"
    [3]="Bandra, Mumbai"
    [4]="Connaught Place, Delhi"
    [5]="Park Street, Kolkata"
)

PIDS=()

# ── Launch pipeline processes in parallel ─────────────────────────────────────
for CAM_NUM in 1 2 3 4 5; do
    VIDEO="data/CAM ${CAM_NUM}.mp4"
    STORE="${STORE_MAP[$CAM_NUM]}"
    LABEL="${STORE_LABELS[$CAM_NUM]}"
    LOG="data/logs/cam${CAM_NUM}_pipeline.log"

    echo "  Starting CAM ${CAM_NUM} → ${STORE} (${LABEL})"
    echo "    Log: ${LOG}"

    python3.11 -m pipeline.main \
        --video     "$VIDEO" \
        --store     "$STORE" \
        --camera    "cam_entry" \
        --layout    "$LAYOUT" \
        --redis     "$REDIS" \
        --output    "$OUTPUT" \
        --start-time "$START_TIME" \
        --frame-skip "$FRAME_SKIP" \
        --model     "$MODEL" \
        --conf      "$CONF" \
        --device    "$DEVICE" \
        > "$LOG" 2>&1 &

    PIDS+=($!)
    echo "    PID: ${PIDS[-1]}"
    echo ""
done

echo "========================================================"
echo " All 5 pipeline processes launched."
echo " PIDs: ${PIDS[*]}"
echo ""
echo " Monitor logs:"
for CAM_NUM in 1 2 3 4 5; do
    echo "   tail -f data/logs/cam${CAM_NUM}_pipeline.log"
done
echo ""
echo " Monitor all at once:"
echo "   tail -f data/logs/cam*.log"
echo ""
echo " Events are written to: $OUTPUT"
echo " Waiting for all processes to complete..."
echo "========================================================"

# ── Wait for all to complete ───────────────────────────────────────────────────
FAILED=0
for i in "${!PIDS[@]}"; do
    CAM_NUM=$((i + 1))
    PID="${PIDS[$i]}"
    if wait "$PID"; then
        echo "  ✓ CAM ${CAM_NUM} (PID $PID) — DONE"
    else
        EXIT_CODE=$?
        echo "  ✗ CAM ${CAM_NUM} (PID $PID) — FAILED (exit code $EXIT_CODE)"
        echo "    Check: data/logs/cam${CAM_NUM}_pipeline.log"
        FAILED=$((FAILED + 1))
    fi
done

echo ""
echo "========================================================"
if [[ $FAILED -eq 0 ]]; then
    echo " All 5 cameras processed successfully."
    # Count events generated
    if [[ -f "$OUTPUT" ]]; then
        EVENT_COUNT=$(wc -l < "$OUTPUT" | tr -d ' ')
        echo " Total events generated: ${EVENT_COUNT}"
    fi
else
    echo " WARNING: $FAILED camera(s) failed. Review logs above."
fi
echo "========================================================"

# ── Ingest JSONL events into API → PostgreSQL (populates KPI/funnel/heatmap) ─
echo ""
echo "Post-run: ingesting events into API (store_id already seeded) ..."
python3.11 scripts/seed_and_ingest.py \
    --events "$OUTPUT" \
    --skip-seed 2>&1 | grep -E '(INFO|WARNING|ERROR)'
echo ""
echo "Dashboard KPIs should now show live data."
echo "========================================================"
