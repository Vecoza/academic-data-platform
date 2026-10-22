"""Command line entry point: python -m ingestion."""

from __future__ import annotations

import argparse
import logging
import time
from collections.abc import Sequence
from datetime import timedelta

from academic_platform.config import DatabaseSettings
from ingestion.pipeline import DEFAULT_OVERLAP, run_ingestion

logger = logging.getLogger(__name__)


def non_negative_int(value: str) -> int:
    number = int(value)
    if number < 0:
        raise argparse.ArgumentTypeError(f"must not be negative, got {value}")
    return number


def table_list(value: str) -> list[str]:
    return [name.strip() for name in value.split(",") if name.strip()]


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m ingestion",
        description="Load new and changed operational rows into the warehouse raw layer.",
    )
    parser.add_argument(
        "--mode",
        choices=("incremental", "full"),
        default="incremental",
        help="incremental reads rows changed since the watermark; full reads every row",
    )
    parser.add_argument(
        "--tables",
        type=table_list,
        help="comma-separated tables of the public schema (default: all)",
    )
    parser.add_argument(
        "--overlap-minutes",
        type=non_negative_int,
        default=int(DEFAULT_OVERLAP.total_seconds() // 60),
        help="re-read this many minutes before the watermark (default: 10)",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    args = parse_args(argv)
    started = time.perf_counter()
    try:
        results = run_ingestion(
            source=DatabaseSettings.from_env(),
            target=DatabaseSettings.for_warehouse(),
            mode=args.mode,
            tables=args.tables,
            overlap=timedelta(minutes=args.overlap_minutes),
        )
    except ValueError as error:
        logger.error("%s", error)
        return 2
    failed = [result.table for result in results if result.status != "succeeded"]
    logger.info(
        "mode=%s tables=%d failed=%d inserted=%d deleted=%d seconds=%.2f",
        args.mode,
        len(results),
        len(failed),
        sum(result.inserted for result in results),
        sum(result.deleted for result in results),
        time.perf_counter() - started,
    )
    if failed:
        logger.error("Failed tables: %s", ", ".join(failed))
        return 1
    return 0
