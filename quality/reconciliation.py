"""Row count reconciliation between the operational source, warehouse.raw and staging.

For every ingested table three numbers must agree:
  source keys     rows in university.public.<table>
  raw keys        distinct keys in warehouse.raw.<table> that are not flagged as deleted
  staging rows    rows in warehouse.staging.stg_<table>
The first comparison checks ingestion, the second the latest-version logic of staging.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass

import psycopg
from psycopg import Connection, sql

from academic_platform.config import DatabaseSettings
from ingestion.catalog import SOURCE_SCHEMA, select_tables, source_tables
from ingestion.warehouse import RAW_SCHEMA

STAGING_SCHEMA = "staging"

QUALITY_DDL = """
    CREATE SCHEMA IF NOT EXISTS meta;

    CREATE TABLE IF NOT EXISTS meta.quality_checks (
        quality_check_id  BIGINT GENERATED ALWAYS AS IDENTITY,
        run_id            UUID NOT NULL,
        check_name        TEXT NOT NULL,
        table_name        TEXT NOT NULL,
        expected          BIGINT,
        actual            BIGINT,
        status            TEXT NOT NULL,
        checked_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
        created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
        CONSTRAINT pk_quality_checks PRIMARY KEY (quality_check_id),
        CONSTRAINT ck_quality_checks_status CHECK (status IN ('passed', 'failed'))
    );

    CREATE INDEX IF NOT EXISTS ix_quality_checks_run_id ON meta.quality_checks (run_id);
"""


@dataclass(frozen=True)
class CheckResult:
    check_name: str
    table_name: str
    expected: int | None
    actual: int | None

    @property
    def status(self) -> str:
        return "passed" if self.expected is not None and self.expected == self.actual else "failed"


def reconcile(
    source: DatabaseSettings,
    warehouse: DatabaseSettings,
    tables: Sequence[str] | None = None,
) -> list[CheckResult]:
    """Compare source, raw and staging counts for the chosen tables (default: all ingested)."""
    with psycopg.connect(source.dsn) as connection:
        selected = select_tables(source_tables(connection), tables)
        source_counts = {
            table.name: count_rows(connection, SOURCE_SCHEMA, table.name) for table in selected
        }

    results = []
    with psycopg.connect(warehouse.dsn) as connection:
        for table in selected:
            raw_keys = count_raw_keys(connection, table.name, table.key)
            staging_rows = count_rows(connection, STAGING_SCHEMA, f"stg_{table.name}")
            results.append(
                CheckResult(
                    "source_keys_vs_raw_keys", table.name, source_counts[table.name], raw_keys
                )
            )
            results.append(
                CheckResult("raw_keys_vs_staging_rows", table.name, raw_keys, staging_rows)
            )
    return results


def count_rows(connection: Connection, schema: str, table_name: str) -> int | None:
    """Row count of a table or view, or None if it does not exist."""
    if not relation_exists(connection, schema, table_name):
        return None
    return connection.execute(
        sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(schema, table_name))
    ).fetchone()[0]


def count_raw_keys(connection: Connection, table_name: str, key: str) -> int | None:
    if not relation_exists(connection, RAW_SCHEMA, table_name):
        return None
    return connection.execute(
        sql.SQL("SELECT count(DISTINCT {key}) FROM {table} WHERE NOT _is_deleted").format(
            key=sql.Identifier(key), table=sql.Identifier(RAW_SCHEMA, table_name)
        )
    ).fetchone()[0]


def relation_exists(connection: Connection, schema: str, name: str) -> bool:
    return connection.execute(
        "SELECT to_regclass(%s) IS NOT NULL", (f'"{schema}"."{name}"',)
    ).fetchone()[0]


def record_results(warehouse: DatabaseSettings, results: Sequence[CheckResult]) -> uuid.UUID:
    """Store the results of one run in meta.quality_checks and return the run id."""
    run_id = uuid.uuid4()
    with psycopg.connect(warehouse.dsn) as connection:
        connection.execute(QUALITY_DDL)
        with connection.cursor() as cursor:
            cursor.executemany(
                """
                INSERT INTO meta.quality_checks
                    (run_id, check_name, table_name, expected, actual, status)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                [
                    (run_id, r.check_name, r.table_name, r.expected, r.actual, r.status)
                    for r in results
                ],
            )
    return run_id
