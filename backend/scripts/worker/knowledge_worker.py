#!/usr/bin/env python3
"""Knowledge worker entrypoint for the V2 knowledge pipeline."""

import asyncio
import logging
import os
import signal
import sys
from argparse import ArgumentParser

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from scripts.worker.knowledge_worker_runtime import (  # noqa: E402
    acquire_task,
    main_loop,
    process_catalog,
    process_task,
    request_shutdown,
)


def _signal_handler(sig: int, frame: object) -> None:
    logging.getLogger("knowledge_worker").info(
        "Received signal %s, shutting down gracefully...", sig
    )
    request_shutdown()


def _build_parser() -> ArgumentParser:
    parser = ArgumentParser(description="Knowledge worker")
    parser.add_argument("--interval", type=int, default=15, help="Poll interval in seconds")
    parser.add_argument("--lease-minutes", type=int, default=30, help="Lease duration in minutes")
    parser.add_argument("--once", action="store_true", help="Run one round and exit")
    parser.add_argument("--catalog", type=int, help="Process a single catalog and exit")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")
    return parser


def main() -> None:
    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)
    args = _build_parser().parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    if args.catalog:
        asyncio.run(process_catalog(args.catalog))
    else:
        asyncio.run(main_loop(
            interval=args.interval,
            lease_minutes=args.lease_minutes,
            once=args.once,
        ))


if __name__ == "__main__":
    main()


__all__ = ["acquire_task", "main_loop", "process_task"]
