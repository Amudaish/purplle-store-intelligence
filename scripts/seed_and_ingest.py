"""
scripts/seed_and_ingest.py

Two-step bootstrap for the analytics pipeline:

  Step 1 — Seed the `stores` table from data/store_layout.json
            (required before any events can be ingested — FK constraint)

  Step 2 — Replay data/events_output.jsonl into the API via POST /events/ingest
            This populates the `events` and `visitor_sessions` tables so that
            the KPI / funnel / heatmap endpoints return real data.

Usage
-----
    python scripts/seed_and_ingest.py [--layout data/store_layout.json]
                                      [--events data/events_output.jsonl]
                                      [--api    http://localhost:8000]
                                      [--batch  100]

Run this once after the CCTV pipeline has finished generating events.
Re-running is safe — both steps are fully idempotent.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import time as dtime
import logging
import sys
from pathlib import Path

import asyncpg
import httpx

import os

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# Prefer DATABASE_URL env var (set automatically on Render) over hardcoded default
_ENV_DSN = os.getenv("DATABASE_URL", "")
if _ENV_DSN:
    # Render provides postgres:// or postgresql://; asyncpg needs postgresql://
    _ENV_DSN = _ENV_DSN.replace("postgres://", "postgresql://", 1).replace(
        "postgresql+asyncpg://", "postgresql://", 1
    )

_DEFAULT_DSN    = _ENV_DSN or "postgresql://store_intel:store_intel_pass@localhost:5432/store_intelligence"
_DEFAULT_LAYOUT = Path("data/store_layout.json")
_DEFAULT_EVENTS = Path("data/events_output.jsonl")
_DEFAULT_API    = os.getenv("API_BASE_URL", "http://localhost:8000")
_DEFAULT_BATCH  = 100


# ── Step 1: Seed stores table ─────────────────────────────────────────────────

async def seed_stores(layout_path: Path, dsn: str) -> int:
    """Upsert all stores from store_layout.json into the stores table."""
    data = json.loads(layout_path.read_text(encoding="utf-8"))
    stores = data.get("stores", {})
    if not stores:
        logger.error("No stores found in %s", layout_path)
        return 0

    def _parse_time(s: str) -> dtime:
        h, m = s.split(":")
        return dtime(int(h), int(m))

    conn = await asyncpg.connect(dsn)
    count = 0
    try:
        for store_id, store in stores.items():
            open_t  = _parse_time(store.get("open_time",  "09:00"))
            close_t = _parse_time(store.get("close_time", "21:00"))
            await conn.execute(
                """
                INSERT INTO stores (store_id, store_name, city, open_time, close_time, layout)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (store_id) DO UPDATE
                    SET store_name = EXCLUDED.store_name,
                        city       = EXCLUDED.city,
                        open_time  = EXCLUDED.open_time,
                        close_time = EXCLUDED.close_time,
                        layout     = EXCLUDED.layout
                """,
                store_id,
                store.get("name"),
                store.get("city"),
                open_t,
                close_t,
                json.dumps(store),
            )
            logger.info("  Upserted store: %s (%s)", store_id, store.get("name"))
            count += 1
    finally:
        await conn.close()

    logger.info("Step 1 complete — %d stores seeded.", count)
    return count


# ── Step 2: Replay JSONL events into API ──────────────────────────────────────

def load_jsonl(path: Path) -> list[dict]:
    events = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError as exc:
                logger.warning("Skipping malformed JSONL line: %s", exc)
    return events


def chunk(lst: list, size: int):
    for i in range(0, len(lst), size):
        yield lst[i : i + size]


def ingest_events(events: list[dict], api_base: str, batch_size: int) -> tuple[int, int]:
    """POST events to /events/ingest in batches. Returns (accepted, rejected)."""
    url = f"{api_base}/events/ingest"
    total_accepted = 0
    total_rejected = 0

    with httpx.Client(timeout=30.0) as client:
        for i, batch in enumerate(chunk(events, batch_size)):
            resp = client.post(url, json={"events": batch})

            if resp.status_code not in (200, 207):
                logger.error(
                    "Batch %d/%d — HTTP %d: %s",
                    i + 1, (len(events) + batch_size - 1) // batch_size,
                    resp.status_code, resp.text[:200],
                )
                total_rejected += len(batch)
                continue

            result = resp.json()
            accepted = result.get("accepted", 0)
            rejected = result.get("rejected", 0)
            errors   = result.get("errors", [])
            total_accepted += accepted
            total_rejected += rejected

            if errors:
                for err in errors[:3]:  # show first 3 errors per batch
                    logger.warning("  Event error: [%s] %s", err.get("error"), err.get("message"))
                if len(errors) > 3:
                    logger.warning("  ... and %d more errors in this batch", len(errors) - 3)

            logger.info(
                "  Batch %d — sent %d | accepted %d | rejected %d",
                i + 1, len(batch), accepted, rejected,
            )

    return total_accepted, total_rejected


# ── CLI ───────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Seed stores + replay events into API")
    p.add_argument("--layout", default=str(_DEFAULT_LAYOUT))
    p.add_argument("--events", default=str(_DEFAULT_EVENTS))
    p.add_argument("--api",    default=_DEFAULT_API)
    p.add_argument("--dsn",    default=_DEFAULT_DSN)
    p.add_argument("--batch",  type=int, default=_DEFAULT_BATCH)
    p.add_argument("--skip-seed",  action="store_true",
                   help="Skip Step 1 (stores already seeded)")
    p.add_argument("--skip-ingest", action="store_true",
                   help="Skip Step 2 (only seed stores)")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    layout_path = Path(args.layout)
    events_path = Path(args.events)

    # ── Step 1 ────────────────────────────────────────────────────────────────
    if not args.skip_seed:
        if not layout_path.exists():
            logger.error("Layout file not found: %s", layout_path)
            return 1
        logger.info("=== Step 1: Seeding stores table ===")
        n = asyncio.run(seed_stores(layout_path, args.dsn))
        if n == 0:
            logger.error("No stores seeded — aborting.")
            return 1
    else:
        logger.info("Step 1 skipped.")

    # ── Step 2 ────────────────────────────────────────────────────────────────
    if not args.skip_ingest:
        if not events_path.exists():
            logger.error("Events file not found: %s", events_path)
            return 1

        logger.info("=== Step 2: Ingesting events from %s ===", events_path)
        events = load_jsonl(events_path)
        logger.info("  Loaded %d events from JSONL", len(events))

        if not events:
            logger.warning("No events to ingest.")
            return 0

        # Verify API is reachable
        try:
            health = httpx.get(f"{args.api}/health", timeout=5.0)
            logger.info("  API health: %s", health.json().get("status"))
        except Exception as exc:
            logger.error("  API unreachable at %s: %s", args.api, exc)
            return 1

        accepted, rejected = ingest_events(events, args.api, args.batch)
        logger.info(
            "Step 2 complete — total accepted: %d, total rejected: %d",
            accepted, rejected,
        )

        if rejected > 0:
            logger.warning(
                "%d events were rejected. Check errors above.", rejected
            )
    else:
        logger.info("Step 2 skipped.")

    logger.info("Done. Refresh the dashboard to see live KPIs.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
