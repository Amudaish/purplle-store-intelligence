"""
scripts/generate_sample_events.py

Generates a realistic JSONL file of synthetic store events based on
store_layout.json.  Useful for seeding the database for development
and testing without requiring real CCTV footage.

Generates per store:
- N_VISITORS unique visitor sessions (non-staff)
- N_STAFF staff sessions
- Realistic event sequences: ENTRY → ZONE_ENTER/DWELL/EXIT × N → BILLING → EXIT
- Re-entry for ~10% of visitors
- Queue abandonments for ~20% of visitors who reach billing

Usage
-----
    python scripts/generate_sample_events.py \\
        --layout data/store_layout.json \\
        --output data/sample_events.jsonl \\
        --visitors 50 \\
        --staff 3
"""

from __future__ import annotations

import argparse
import json
import random
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List

_DEFAULT_LAYOUT = Path("data") / "store_layout.json"
_DEFAULT_OUTPUT = Path("data") / "sample_events.jsonl"

# Store hours base
_BASE_DATE = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)


def generate_visitor_session(
    store_id: str,
    camera_ids: List[str],
    zone_ids: List[str],
    shopping_zones: List[str],
    billing_zone: str,
    visitor_id: str,
    start_ts: datetime,
    is_staff: bool = False,
    include_purchase: bool = False,
    include_abandon: bool = False,
    is_reentry: bool = False,
) -> List[dict]:
    """Generate a realistic event sequence for one visitor session."""
    events = []
    ts = start_ts
    camera_id = random.choice(camera_ids)
    conf = round(random.uniform(0.75, 0.98), 3)

    def ev(event_type, zone_id=None, dwell_ms=None, extra_meta=None):
        return {
            "event_id": str(uuid.uuid4()),
            "store_id": store_id,
            "camera_id": camera_id,
            "visitor_id": visitor_id,
            "event_type": event_type,
            "timestamp": ts.isoformat(),
            "zone_id": zone_id,
            "dwell_ms": dwell_ms,
            "is_staff": is_staff,
            "confidence": conf,
            "metadata": extra_meta or {},
        }

    nonlocal_ts = [ts]

    def advance(seconds):
        nonlocal_ts[0] += timedelta(seconds=seconds)

    # ENTRY or REENTRY
    events.append(ev("REENTRY" if is_reentry else "ENTRY"))
    advance(random.randint(5, 15))

    # Zone visits (2–4 shopping zones)
    visited = random.sample(shopping_zones, k=min(random.randint(2, 4), len(shopping_zones)))
    for zone in visited:
        ts = nonlocal_ts[0]
        events.append({**ev("ZONE_ENTER", zone_id=zone), "timestamp": ts.isoformat()})
        dwell = random.randint(30_000, 300_000)  # 30s – 5 min
        advance(dwell // 1000)
        ts = nonlocal_ts[0]
        events.append({**ev("ZONE_EXIT", zone_id=zone, dwell_ms=dwell), "timestamp": ts.isoformat()})
        advance(random.randint(10, 30))

    # Billing queue
    if not is_staff:
        ts = nonlocal_ts[0]
        queue_depth = random.randint(0, 5)
        events.append({
            **ev("BILLING_QUEUE_JOIN", zone_id=billing_zone),
            "timestamp": ts.isoformat(),
            "metadata": {"queue_depth": queue_depth},
        })
        advance(random.randint(60, 300))  # wait 1–5 min

        if include_abandon:
            ts = nonlocal_ts[0]
            abandon_dwell = random.randint(60_000, 300_000)
            events.append({
                **ev("BILLING_QUEUE_ABANDON", zone_id=billing_zone, dwell_ms=abandon_dwell),
                "timestamp": ts.isoformat(),
            })
            advance(10)

    # EXIT
    ts = nonlocal_ts[0]
    total_dwell = int((ts - start_ts).total_seconds() * 1000)
    events.append({
        **ev("EXIT", dwell_ms=total_dwell),
        "timestamp": ts.isoformat(),
    })

    return events


def main() -> None:
    p = argparse.ArgumentParser(description="Generate sample store events JSONL")
    p.add_argument("--layout", default=str(_DEFAULT_LAYOUT))
    p.add_argument("--output", default=str(_DEFAULT_OUTPUT))
    p.add_argument("--visitors", type=int, default=50, help="Non-staff visitors per store")
    p.add_argument("--staff", type=int, default=3, help="Staff members per store")
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args()

    random.seed(args.seed)
    layout = json.loads(Path(args.layout).read_text())
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    all_events = []

    for store_id, store_data in layout.get("stores", {}).items():
        camera_ids = list(store_data.get("cameras", {}).keys())
        zones = store_data.get("zones", {})
        zone_ids = list(zones.keys())
        shopping_zones = [z for z, d in zones.items() if d.get("type") == "shopping"]
        billing_zones = [z for z, d in zones.items() if d.get("type") == "billing"]
        billing_zone = billing_zones[0] if billing_zones else "billing"

        store_ts = _BASE_DATE

        # Generate staff sessions
        for _ in range(args.staff):
            vid = f"staff_{uuid.uuid4().hex[:8]}"
            start = store_ts + timedelta(minutes=random.randint(0, 30))
            # Staff are present all day
            all_events.append({
                "event_id": str(uuid.uuid4()),
                "store_id": store_id,
                "camera_id": random.choice(camera_ids),
                "visitor_id": vid,
                "event_type": "ENTRY",
                "timestamp": start.isoformat(),
                "zone_id": None,
                "dwell_ms": None,
                "is_staff": True,
                "confidence": 0.95,
                "metadata": {},
            })

        # Generate customer sessions
        for i in range(args.visitors):
            vid = str(uuid.uuid4())
            start = store_ts + timedelta(minutes=random.randint(5, 600))
            include_purchase = random.random() < 0.35   # 35% convert
            include_abandon = not include_purchase and random.random() < 0.20
            is_reentry = i > 0 and random.random() < 0.10

            session_events = generate_visitor_session(
                store_id=store_id,
                camera_ids=camera_ids,
                zone_ids=zone_ids,
                shopping_zones=shopping_zones,
                billing_zone=billing_zone,
                visitor_id=vid,
                start_ts=start,
                is_staff=False,
                include_purchase=include_purchase,
                include_abandon=include_abandon,
                is_reentry=is_reentry,
            )
            all_events.extend(session_events)

        print(f"Generated events for {store_id}")

    # Sort by timestamp across all stores
    all_events.sort(key=lambda e: e["timestamp"])

    with open(output_path, "w", encoding="utf-8") as f:
        for event in all_events:
            f.write(json.dumps(event) + "\n")

    print(f"\nTotal events: {len(all_events)}")
    print(f"Written to: {output_path}")


if __name__ == "__main__":
    main()
