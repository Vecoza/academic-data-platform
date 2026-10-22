"""Command line entry point: python -m generator."""

from __future__ import annotations

import argparse
import logging
import time
from collections.abc import Sequence
from datetime import date

from academic_platform.db import get_engine
from generator.daily import (
    first_daily_date,
    format_changes,
    read_clock,
    reset_clock,
    run_days,
    run_until,
)
from generator.history import simulate_history
from generator.loader import load_generated_data
from generator.reference import LAST_ACADEMIC_YEAR, generate_reference_data

logger = logging.getLogger(__name__)

DEFAULT_SEED = 42


def positive_int(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError(f"must be a positive integer, got {value}")
    return number


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m generator",
        description="Generate synthetic university data and load it into the operational database.",
    )
    parser.add_argument(
        "--mode",
        choices=("full", "daily"),
        default="full",
        help="full replaces all data with a new history; daily simulates the next days",
    )
    parser.add_argument(
        "--seed",
        type=int,
        help=f"random seed for full mode (default: {DEFAULT_SEED}); daily mode reuses it",
    )
    parser.add_argument(
        "--students", type=positive_int, default=15_000, help="number of students (default: 15000)"
    )
    parser.add_argument(
        "--years", type=positive_int, default=8, help="academic years of history (default: 8)"
    )
    period = parser.add_mutually_exclusive_group()
    period.add_argument("--days", type=positive_int, help="daily mode: number of days to simulate")
    period.add_argument(
        "--date",
        type=date.fromisoformat,
        help="daily mode: simulate up to and including this date (YYYY-MM-DD)",
    )
    args = parser.parse_args(argv)
    if args.mode == "full" and (args.days is not None or args.date is not None):
        parser.error("--days and --date apply to daily mode only")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    args = parse_args(argv)
    try:
        if args.mode == "full":
            run_full(args)
        else:
            run_daily(args)
    except RuntimeError as error:
        logger.error("%s", error)
        return 1
    return 0


def run_full(args: argparse.Namespace) -> None:
    seed = DEFAULT_SEED if args.seed is None else args.seed
    logger.info(
        "Generating full history: seed %s, %s students, %s years", seed, args.students, args.years
    )
    started = time.perf_counter()
    reference = generate_reference_data(seed=seed, years=args.years)
    history = simulate_history(seed=seed, student_count=args.students, reference=reference)
    logger.info("Simulated history in %.2f s", time.perf_counter() - started)

    started = time.perf_counter()
    with get_engine().begin() as connection:
        counts = load_generated_data(connection, reference, history)
        reset_clock(connection, first_daily_date(LAST_ACADEMIC_YEAR), seed)
    logger.info("Loaded %d rows in %.2f s", sum(counts.values()), time.perf_counter() - started)


def run_daily(args: argparse.Namespace) -> None:
    engine = get_engine()
    with engine.connect() as connection:
        clock = read_clock(connection)
    if args.seed is not None and args.seed != clock.seed:
        raise RuntimeError(
            f"Daily mode continues the history built from seed {clock.seed}, not {args.seed}"
        )
    if args.date is not None:
        changes = run_until(engine, args.date)
    else:
        changes = run_days(engine, args.days or 1)
    logger.info("Daily run total: %s", format_changes(changes))
