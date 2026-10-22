"""Run the dbt project in-process against a test warehouse."""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from dbt.cli.main import dbtRunner

from academic_platform.config import DatabaseSettings

DBT_PROJECT_DIR = Path(__file__).resolve().parent.parent / "dbt"


@contextmanager
def environment(**values: str) -> Iterator[None]:
    """Set environment variables for the duration of the block."""
    previous = {name: os.environ.get(name) for name in values}
    os.environ.update(values)
    try:
        yield
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def run_dbt(warehouse: DatabaseSettings, args: list[str], work_dir: Path) -> dict[str, str]:
    """Run a dbt command against `warehouse`; returns the status of every node by name."""
    with environment(
        POSTGRES_HOST=warehouse.host,
        POSTGRES_PORT=str(warehouse.port),
        POSTGRES_USER=warehouse.user,
        POSTGRES_PASSWORD=warehouse.password,
        WAREHOUSE_DB=warehouse.name,
    ):
        result = dbtRunner().invoke(
            [
                *args,
                "--project-dir",
                str(DBT_PROJECT_DIR),
                "--profiles-dir",
                str(DBT_PROJECT_DIR),
                "--target-path",
                str(work_dir / "target"),
                "--log-path",
                str(work_dir / "logs"),
                "--quiet",
            ]
        )
    if result.exception is not None:
        raise result.exception
    return {node.node.name: str(node.status) for node in result.result.results}


def failed_nodes(statuses: dict[str, str]) -> set[str]:
    return {name for name, status in statuses.items() if status in {"fail", "error"}}
