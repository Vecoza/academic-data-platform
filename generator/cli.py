"""Command line entry point: python -m generator."""

from __future__ import annotations

import argparse
import logging
import time
from collections.abc import Sequence

from academic_platform.db import get_engine
from generator.history import simulate_history
from generator.loader import load_generated_data
from generator.reference import generate_reference_data

logger = logging.getLogger(__name__)


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
    parser.add_argument("--seed", type=int, default=42, help="random seed (default: 42)")
    parser.add_argument(
        "--students", type=positive_int, default=15_000, help="number of students (default: 15000)"
    )
    parser.add_argument(
        "--years", type=positive_int, default=8, help="academic years of history (default: 8)"
    )
    parser.add_argument(
        "--mode",
        choices=("full", "daily"),
        default="full",
        help="full replaces all data with a new history; daily adds one day of activity",
    )
    args = parser.parse_args(argv)
    if args.mode == "daily":
        parser.error("daily mode is not implemented yet")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    args = parse_args(argv)
    logger.info(
        "Generating %s mode data: seed %s, %s students, %s years",
        args.mode,
        args.seed,
        args.students,
        args.years,
    )

    started = time.perf_counter()
    reference = generate_reference_data(seed=args.seed, years=args.years)
    history = simulate_history(seed=args.seed, student_count=args.students, reference=reference)
    logger.info("Simulated history in %.2f s", time.perf_counter() - started)

    started = time.perf_counter()
    with get_engine().begin() as connection:
        counts = load_generated_data(connection, reference, history)
    logger.info("Loaded %d rows in %.2f s", sum(counts.values()), time.perf_counter() - started)
    return 0
