"""Command line entry point: python -m quality."""

from __future__ import annotations

import argparse
import logging
from collections.abc import Sequence

from academic_platform.config import DatabaseSettings
from quality.reconciliation import reconcile, record_results

logger = logging.getLogger(__name__)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m quality",
        description="Reconcile row counts between the source, warehouse.raw and staging.",
    )
    parser.add_argument(
        "--tables",
        type=lambda value: [name.strip() for name in value.split(",") if name.strip()],
        help="comma-separated tables (default: all ingested tables)",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    args = parse_args(argv)
    warehouse = DatabaseSettings.for_warehouse()
    try:
        results = reconcile(DatabaseSettings.from_env(), warehouse, args.tables)
    except ValueError as error:
        logger.error("%s", error)
        return 2
    run_id = record_results(warehouse, results)

    for result in results:
        level = logging.INFO if result.status == "passed" else logging.ERROR
        logger.log(
            level,
            "check=%s table=%s expected=%s actual=%s status=%s",
            result.check_name,
            result.table_name,
            result.expected,
            result.actual,
            result.status,
        )
    failed = [result for result in results if result.status == "failed"]
    logger.info("run=%s checks=%d failed=%d", run_id, len(results), len(failed))
    return 1 if failed else 0
