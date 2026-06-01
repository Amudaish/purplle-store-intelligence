"""
Pipeline main — CLI entry-point that processes one CCTV camera video file
through the full detection → tracking → Re-ID → zone → session → event
pipeline and publishes structured events to Redis Streams and a JSONL file.

Video files (data/ directory)
------------------------------
    CAM 1.mp4  →  store_001  cam_entry    (Koramangala, Bangalore)
    CAM 2.mp4  →  store_002  cam_entry    (Indiranagar, Bangalore)
    CAM 3.mp4  →  store_003  cam_entry    (Bandra, Mumbai)
    CAM 4.mp4  →  store_004  cam_entry    (Connaught Place, Delhi)
    CAM 5.mp4  →  store_005  cam_entry    (Park Street, Kolkata)

NOTE: File names contain spaces — always quote the --video path.

Single camera usage
--------------------
    python -m pipeline.main \\
        --video  "data/CAM 1.mp4" \\
        --store  store_001 \\
        --camera cam_entry \\
        --layout data/store_layout.json \\
        --redis  redis://localhost:6379/0 \\
        --output data/events_output.jsonl \\
        --start-time "2026-05-29T10:00:00" \\
        --frame-skip 2 \\
        --model  yolov8s.pt \\
        --conf   0.40

Run all 5 cameras in parallel (see scripts/run_pipeline_all.sh)
----------------------------------------------------------------
    bash scripts/run_pipeline_all.sh

Multiple cameras run as independent processes; Re-ID deduplication
across cameras is handled by shared Redis embeddings.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import structlog

# ── Structlog configuration ────────────────────────────────────────────────────
structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer(),
    ],
)
logger = structlog.get_logger(__name__)


def build_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="CCTV Store Intelligence Pipeline")
    p.add_argument("--video",   required=True,  help="Path to input video file")
    p.add_argument("--store",   required=True,  help="Store ID, e.g. store_001")
    p.add_argument("--camera",  required=True,  help="Camera ID, e.g. cam_entry")
    p.add_argument("--layout",  default="data/store_layout.json",
                   help="Path to store_layout.json")
    p.add_argument("--redis",   default="redis://localhost:6379/0",
                   help="Redis URL")
    p.add_argument("--output",  default="data/events_output.jsonl",
                   help="JSONL output file path")
    p.add_argument("--start-time", default=None,
                   help="ISO timestamp for frame 0 (default: file mtime or now)")
    p.add_argument("--frame-skip", type=int, default=1,
                   help="Process every Nth frame (1 = all, 2 = half, etc.)")
    p.add_argument("--model",   default="yolov8s.pt", help="YOLOv8 model path")
    p.add_argument("--conf",    type=float, default=0.40,
                   help="Detection confidence threshold")
    p.add_argument("--device",  default="cpu",
                   help="Inference device: cpu | cuda | mps")
    return p.parse_args()


def resolve_start_time(args: argparse.Namespace) -> datetime:
    if args.start_time:
        ts = datetime.fromisoformat(args.start_time)
        return ts.replace(tzinfo=timezone.utc) if ts.tzinfo is None else ts
    video_path = Path(args.video)
    if video_path.exists():
        mtime = video_path.stat().st_mtime
        return datetime.fromtimestamp(mtime, tz=timezone.utc)
    return datetime.now(tz=timezone.utc)


def main() -> int:
    args = build_args()

    # ── Dependencies ──────────────────────────────────────────────────────────
    try:
        import cv2  # type: ignore
        import redis as redis_lib  # type: ignore
    except ImportError as exc:
        logger.error("Missing dependency", error=str(exc))
        return 1

    from pipeline.detector import PersonDetector
    from pipeline.tracker import PersonTracker
    from pipeline.reid import ReIDModule
    from pipeline.staff_classifier import StaffClassifier
    from pipeline.zone_engine import ZoneEngine, load_zones_from_layout
    from pipeline.session_manager import SessionManager
    from pipeline.event_emitter import EventEmitter

    # ── Load store layout ─────────────────────────────────────────────────────
    layout_path = Path(args.layout)
    if not layout_path.exists():
        logger.error("Store layout file not found", path=str(layout_path))
        return 1
    store_layout = json.loads(layout_path.read_text())

    zones = load_zones_from_layout(store_layout, args.store)
    if not zones:
        logger.warning("No zones found for store", store_id=args.store)

    # Determine camera resolution to compute scale factor for zone polygons
    # (Zone polygons in store_layout.json use floor-plan units 0–100/300;
    #  we need to map camera pixel space → floor-plan space.
    #  For this pipeline we detect the video resolution at runtime and set a
    #  simple scale factor.  A proper homography would be calibrated per-camera.)
    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        logger.error("Cannot open video file", path=args.video)
        return 1

    frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 15.0

    # Simple scale: map 1920×1080 → layout coordinate space
    # The layout uses coordinates ~0–100/0–300 depending on store.
    # We read the bounding box of all zones to get max x/y in layout space.
    if zones:
        all_pts = [z.polygon for z in zones]
        import numpy as np
        all_pts_arr = np.concatenate(all_pts, axis=0)
        max_x_layout = float(all_pts_arr[:, 0].max())
        max_y_layout = float(all_pts_arr[:, 1].max())
    else:
        max_x_layout, max_y_layout = float(frame_width), float(frame_height)

    scale_x = max_x_layout / frame_width
    scale_y = max_y_layout / frame_height

    logger.info(
        "Video opened",
        width=frame_width,
        height=frame_height,
        total_frames=total_frames,
        fps=fps,
        scale_x=round(scale_x, 4),
        scale_y=round(scale_y, 4),
    )

    # ── Initialise pipeline components ───────────────────────────────────────
    redis_client = None
    try:
        redis_client = redis_lib.from_url(args.redis, decode_responses=False)
        redis_client.ping()
        logger.info("Redis connected", url=args.redis)
    except Exception as exc:
        logger.warning("Redis unavailable — events will only be written to JSONL",
                       error=str(exc))

    start_ts = resolve_start_time(args)

    detector = PersonDetector(
        model_path=args.model,
        conf_threshold=args.conf,
        device=args.device,
    )
    tracker = PersonTracker(frame_rate=int(fps))
    reid = ReIDModule(redis_client=redis_client, store_id=args.store)
    staff_clf = StaffClassifier()
    zone_engine = ZoneEngine(
        zones=zones,
        frame_rate=int(fps),
        scale_x=scale_x,
        scale_y=scale_y,
    )
    session_mgr = SessionManager(frame_rate=int(fps))
    emitter = EventEmitter(
        redis_client=redis_client,
        store_id=args.store,
        camera_id=args.camera,
        video_start_ts=start_ts,
        frame_rate=int(fps),
        output_path=Path(args.output),
    )

    # ── Main processing loop ─────────────────────────────────────────────────
    frame_idx = 0
    processed = 0
    log_every = max(1, int(fps * 30))  # log every 30 seconds of video

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            frame_idx += 1

            # Frame skip — process every Nth frame
            if (frame_idx % args.frame_skip) != 0:
                continue

            processed += 1

            # 1. Detect persons
            detections = detector.detect(frame)

            # 2. Track across frames
            tracks = tracker.update(detections, frame_idx)

            # 3. Re-ID: assign global visitor_id per track
            visitor_map: dict[int, str] = {}
            is_staff_track: dict[int, bool] = {}
            for track in tracks:
                visitor_id = reid.get_or_create_visitor_id(track.track_id, track.crop)
                visitor_map[track.track_id] = visitor_id
                is_staff_flag = staff_clf.classify(track.track_id, track.crop, frame_idx)
                is_staff_track[track.track_id] = is_staff_flag

            # Build visitor→is_staff map for session manager
            visitor_staff_map: dict[str, bool] = {}
            for tid, vid in visitor_map.items():
                visitor_staff_map[vid] = is_staff_track.get(tid, False)

            # 4. Zone events
            zone_events = zone_engine.update(
                tracks=tracks,
                frame_idx=frame_idx,
                visitor_map=visitor_map,
                is_staff_map=is_staff_track,
            )

            # Emit zone events
            for ze in zone_events:
                is_staff = visitor_staff_map.get(ze.visitor_id, False)
                conf = 0.8  # zone events inherit detection confidence avg
                if ze.event_type == "ZONE_ENTER":
                    emitter.emit_zone_enter(ze.visitor_id, ze.zone_id, frame_idx, conf, is_staff)
                elif ze.event_type == "ZONE_EXIT":
                    emitter.emit_zone_exit(ze.visitor_id, ze.zone_id, ze.dwell_ms or 0, frame_idx, conf, is_staff)
                elif ze.event_type == "ZONE_DWELL":
                    emitter.emit_zone_dwell(ze.visitor_id, ze.zone_id, ze.dwell_ms or 0, frame_idx, conf, is_staff)

                if ze.extra_event_type == "BILLING_QUEUE_JOIN":
                    emitter.emit_billing_queue_join(
                        ze.visitor_id, frame_idx, conf, is_staff,
                        queue_depth=zone_engine.get_queue_depth(),
                    )
                elif ze.extra_event_type == "BILLING_QUEUE_ABANDON":
                    emitter.emit_billing_queue_abandon(
                        ze.visitor_id, frame_idx, conf, is_staff,
                        dwell_ms=ze.dwell_ms or 0,
                    )

            # 5. Session events (ENTRY / EXIT / REENTRY)
            active_visitor_ids = list(visitor_map.values())
            session_events = session_mgr.update(active_visitor_ids, visitor_staff_map, frame_idx)

            avg_conf = (
                sum(t.confidence for t in tracks) / len(tracks)
                if tracks else 0.5
            )
            for se in session_events:
                is_staff = visitor_staff_map.get(se.visitor_id, False)
                if se.event_type == "ENTRY":
                    emitter.emit_entry(se.visitor_id, se.frame_idx, avg_conf, is_staff)
                elif se.event_type == "EXIT":
                    dwell = session_mgr.get_dwell_ms(se.visitor_id, se.frame_idx)
                    emitter.emit_exit(se.visitor_id, se.frame_idx, avg_conf, is_staff, dwell)
                elif se.event_type == "REENTRY":
                    emitter.emit_reentry(se.visitor_id, se.frame_idx, avg_conf, is_staff)

            # Periodic progress log
            if processed % log_every == 0:
                pct = (frame_idx / total_frames * 100) if total_frames > 0 else 0
                summary = session_mgr.summary()
                logger.info(
                    "Progress",
                    frame=frame_idx,
                    pct=round(pct, 1),
                    total_emitted=emitter._total_emitted,
                    **summary,
                )

    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    finally:
        cap.release()
        emitter.close()

    summary = session_mgr.summary()
    logger.info(
        "Pipeline complete",
        store_id=args.store,
        camera_id=args.camera,
        frames_processed=processed,
        total_events=emitter._total_emitted,
        **summary,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
