#!/usr/bin/env python3
"""Run bounded knowledge chunk embedding sidecar backfill batches."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "backend"
for path in (REPO_ROOT, BACKEND_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from app.database import AsyncSessionLocal  # noqa: E402

from modules.knowledge.backend.services.chunk_embedding_service import (  # noqa: E402
    backfill_chunk_embeddings,
    get_chunk_embedding_counts,
)


def _emit(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, default=str), flush=True)


async def _run(args: argparse.Namespace) -> None:
    started = time.perf_counter()
    embedded_total = 0
    cycle = 0
    stop_file = Path(args.stop_file).expanduser() if args.stop_file else None
    max_rows = max(1, int(args.total_limit or 1))
    while embedded_total < max_rows:
        if stop_file and stop_file.exists():
            _emit({"event": "stopped", "reason": "stop_file_exists", "stop_file": str(stop_file)})
            return
        remaining_budget = max_rows - embedded_total
        limit = min(max(1, int(args.chunk_limit or 1)), remaining_budget)
        cycle += 1
        cycle_started = time.perf_counter()
        async with AsyncSessionLocal() as db:
            result = await backfill_chunk_embeddings(
                db,
                owner_id=int(args.owner_id),
                profile_key=str(args.profile),
                dry_run=False,
                limit=limit,
                batch_size=int(args.batch_size),
            )
            counts = await get_chunk_embedding_counts(
                db,
                owner_id=int(args.owner_id),
                profile_key=str(args.profile),
            )
        embedded = int(result.get("embedded") or 0)
        embedded_total += embedded
        elapsed = time.perf_counter() - cycle_started
        _emit({
            "event": "batch_done",
            "cycle": cycle,
            "elapsed_seconds": round(elapsed, 3),
            "throughput_per_sec": round(embedded / elapsed, 3) if elapsed > 0 else 0,
            "embedded_total": embedded_total,
            "target_total": max_rows,
            "result": result,
            "counts": counts,
        })
        if embedded <= 0 and int(result.get("candidate_count") or 0) <= 0:
            _emit({"event": "complete", "reason": "no_candidates", "embedded_total": embedded_total})
            return
        if args.sleep_seconds > 0:
            await asyncio.sleep(float(args.sleep_seconds))
    _emit({
        "event": "complete",
        "reason": "target_reached",
        "embedded_total": embedded_total,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
    })


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--owner-id", type=int, default=4)
    parser.add_argument("--profile", default="qwen3-embedding-8b")
    parser.add_argument("--total-limit", type=int, default=10000)
    parser.add_argument("--chunk-limit", type=int, default=512)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--sleep-seconds", type=float, default=0.0)
    parser.add_argument("--stop-file", default="")
    args = parser.parse_args()
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
