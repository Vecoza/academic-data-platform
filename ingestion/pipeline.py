"""Extract changed rows from the operational database and load them into warehouse.raw.

Each table is loaded in its own warehouse transaction: new row versions, delete flags, the
batch record and the watermark are committed together or not at all. The source is read in a
single REPEATABLE READ snapshot, so the extracted rows and the key list used to detect deletes
describe the same moment.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

import psycopg
from psycopg import Connection, IsolationLevel, sql

from academic_platform.config import DatabaseSettings
from ingestion.catalog import (
    CHANGE_COLUMN,
    SOURCE_SCHEMA,
    SourceTable,
    select_tables,
    source_tables,
)
from ingestion.warehouse import (
    RAW_SCHEMA,
    ensure_meta,
    ensure_raw_table,
    read_watermark,
    save_watermark,
    version_constraint,
)

logger = logging.getLogger(__name__)

DEFAULT_OVERLAP = timedelta(minutes=10)
MAX_ATTEMPTS = 3
BACKOFF_SECONDS = 1.0
TRANSIENT_ERRORS = (psycopg.OperationalError,)


@dataclass
class TableResult:
    table: str
    mode: str
    batch_id: int
    status: str = "running"
    extracted: int = 0
    inserted: int = 0
    duplicates: int = 0
    deleted: int = 0
    watermark_from: datetime | None = None
    watermark_to: datetime | None = None
    attempts: int = 0
    seconds: float = 0.0
    error: str | None = None


def run_ingestion(
    source: DatabaseSettings,
    target: DatabaseSettings,
    mode: str,
    tables: Sequence[str] | None = None,
    overlap: timedelta = DEFAULT_OVERLAP,
) -> list[TableResult]:
    """Ingest the chosen tables (default: every eligible table) and return one result each."""
    with psycopg.connect(target.dsn, autocommit=True) as warehouse:
        ensure_meta(warehouse)
    with psycopg.connect(source.dsn) as connection:
        selected = select_tables(source_tables(connection), tables)
    return [ingest_table(source, target, table, mode, overlap) for table in selected]


def ingest_table(
    source: DatabaseSettings,
    target: DatabaseSettings,
    table: SourceTable,
    mode: str,
    overlap: timedelta,
) -> TableResult:
    """Load one table, retrying transient connection errors with exponential backoff."""
    started = time.perf_counter()
    result = TableResult(table.name, mode, start_batch(target, table.name, mode))
    while True:
        result.attempts += 1
        try:
            load_table(source, target, table, mode, overlap, result)
            result.status = "succeeded"
            break
        except TRANSIENT_ERRORS as error:
            if result.attempts >= MAX_ATTEMPTS:
                fail_batch(target, result, error)
                break
            delay = BACKOFF_SECONDS * 2 ** (result.attempts - 1)
            logger.warning(
                "table=%s attempt=%d transient error, retrying in %.1f s: %s",
                table.name,
                result.attempts,
                delay,
                error,
            )
            time.sleep(delay)
        except Exception as error:
            fail_batch(target, result, error)
            break
    result.seconds = time.perf_counter() - started
    log_result(result)
    return result


def load_table(
    source: DatabaseSettings,
    target: DatabaseSettings,
    table: SourceTable,
    mode: str,
    overlap: timedelta,
    result: TableResult,
) -> None:
    with (
        psycopg.connect(source.dsn) as source_connection,
        psycopg.connect(target.dsn) as warehouse,
    ):
        source_connection.isolation_level = IsolationLevel.REPEATABLE_READ
        source_connection.read_only = True
        with source_connection.transaction(), warehouse.transaction():
            ensure_raw_table(warehouse, table)
            result.watermark_from = read_watermark(warehouse, table.name)
            since = None
            if mode == "incremental" and result.watermark_from is not None:
                since = result.watermark_from - overlap

            result.extracted = extract_to_stage(source_connection, warehouse, table, since)
            result.inserted = insert_new_versions(warehouse, table, result.batch_id)
            result.duplicates = result.extracted - result.inserted
            result.deleted = flag_deletes(source_connection, warehouse, table)

            latest = warehouse.execute(
                sql.SQL("SELECT max({}) FROM _stage").format(sql.Identifier(CHANGE_COLUMN))
            ).fetchone()[0]
            result.watermark_to = max(filter(None, (latest, result.watermark_from)), default=None)
            if result.watermark_to is not None:
                save_watermark(warehouse, table.name, result.watermark_to)
            finish_batch(warehouse, result)


def extract_to_stage(
    source_connection: Connection,
    warehouse: Connection,
    table: SourceTable,
    since: datetime | None,
) -> int:
    """Stream the changed source rows with COPY into a temporary staging table."""
    warehouse.execute(
        sql.SQL("CREATE TEMPORARY TABLE _stage ({}) ON COMMIT DROP").format(
            sql.SQL(", ").join(
                sql.SQL("{} {}").format(sql.Identifier(column.name), sql.SQL(column.data_type))
                for column in table.columns
            )
        )
    )
    columns = sql.SQL(", ").join(map(sql.Identifier, table.column_names))
    query = sql.SQL("SELECT {columns} FROM {table}").format(
        columns=columns, table=sql.Identifier(SOURCE_SCHEMA, table.name)
    )
    if since is not None:
        query = sql.SQL("{query} WHERE {change_column} > {since}").format(
            query=query, change_column=sql.Identifier(CHANGE_COLUMN), since=sql.Literal(since)
        )
    copy_between(
        source_connection,
        sql.SQL("COPY ({}) TO STDOUT").format(query),
        warehouse,
        sql.SQL("COPY _stage ({}) FROM STDIN").format(columns),
    )
    return warehouse.execute("SELECT count(*) FROM _stage").fetchone()[0]


def copy_between(
    source_connection: Connection,
    copy_out: sql.Composable,
    warehouse: Connection,
    copy_in: sql.Composable,
) -> None:
    """Pass COPY data block by block, so a large table never has to fit in memory."""
    with (
        source_connection.cursor() as source_cursor,
        warehouse.cursor() as warehouse_cursor,
        source_cursor.copy(copy_out) as reader,
        warehouse_cursor.copy(copy_in) as writer,
    ):
        for block in reader:
            writer.write(block)


def insert_new_versions(warehouse: Connection, table: SourceTable, batch_id: int) -> int:
    """Append staged rows to raw; a version already present (same key and updated_at) is skipped."""
    columns = sql.SQL(", ").join(map(sql.Identifier, table.column_names))
    return warehouse.execute(
        sql.SQL(
            "INSERT INTO {raw} ({columns}, _batch_id, _loaded_at, _source_updated_at) "
            "SELECT {columns}, %s, now(), {change_column} FROM _stage "
            "ON CONFLICT ON CONSTRAINT {unique_version} DO NOTHING"
        ).format(
            raw=sql.Identifier(RAW_SCHEMA, table.name),
            columns=columns,
            change_column=sql.Identifier(CHANGE_COLUMN),
            unique_version=sql.Identifier(version_constraint(table.name)),
        ),
        (batch_id,),
    ).rowcount


def flag_deletes(source_connection: Connection, warehouse: Connection, table: SourceTable) -> int:
    """Flag raw rows whose key no longer exists in the source. Returns the number of keys."""
    key = sql.Identifier(table.key)
    warehouse.execute(
        sql.SQL("CREATE TEMPORARY TABLE _source_keys ({} {} PRIMARY KEY) ON COMMIT DROP").format(
            key, sql.SQL(table.key_type)
        )
    )
    copy_between(
        source_connection,
        sql.SQL("COPY (SELECT {key} FROM {table}) TO STDOUT").format(
            key=key, table=sql.Identifier(SOURCE_SCHEMA, table.name)
        ),
        warehouse,
        sql.SQL("COPY _source_keys ({}) FROM STDIN").format(key),
    )
    flagged = warehouse.execute(
        sql.SQL(
            "UPDATE {raw} AS raw_row SET _is_deleted = true, _deleted_at = now() "
            "WHERE NOT raw_row._is_deleted "
            "AND NOT EXISTS (SELECT 1 FROM _source_keys WHERE _source_keys.{key} = raw_row.{key}) "
            "RETURNING raw_row.{key}"
        ).format(raw=sql.Identifier(RAW_SCHEMA, table.name), key=key)
    ).fetchall()
    return len({row[0] for row in flagged})


def start_batch(target: DatabaseSettings, table_name: str, mode: str) -> int:
    """Record the batch as running in its own transaction, so a failure can still be recorded."""
    with psycopg.connect(target.dsn, autocommit=True) as warehouse:
        return warehouse.execute(
            """
            INSERT INTO meta.load_batches (table_name, mode, status)
            VALUES (%s, %s, 'running')
            RETURNING batch_id
            """,
            (table_name, mode),
        ).fetchone()[0]


def finish_batch(warehouse: Connection, result: TableResult) -> None:
    warehouse.execute(
        """
        UPDATE meta.load_batches
        SET status = 'succeeded', finished_at = clock_timestamp(),
            watermark_from = %s, watermark_to = %s,
            rows_extracted = %s, rows_inserted = %s, rows_duplicate = %s, rows_deleted = %s,
            updated_at = now()
        WHERE batch_id = %s
        """,
        (
            result.watermark_from,
            result.watermark_to,
            result.extracted,
            result.inserted,
            result.duplicates,
            result.deleted,
            result.batch_id,
        ),
    )


def fail_batch(target: DatabaseSettings, result: TableResult, error: Exception) -> None:
    """Mark the batch failed; the table's watermark and raw rows were rolled back with it."""
    result.status = "failed"
    result.error = f"{type(error).__name__}: {error}"
    try:
        with psycopg.connect(target.dsn, autocommit=True) as warehouse:
            warehouse.execute(
                """
                UPDATE meta.load_batches
                SET status = 'failed', finished_at = clock_timestamp(), error_message = %s,
                    updated_at = now()
                WHERE batch_id = %s
                """,
                (result.error, result.batch_id),
            )
    except psycopg.Error:
        logger.exception("table=%s could not record the failed batch", result.table)


def log_result(result: TableResult) -> None:
    level = logging.INFO if result.status == "succeeded" else logging.ERROR
    logger.log(
        level,
        "table=%s mode=%s status=%s batch=%d extracted=%d inserted=%d duplicates=%d deleted=%d "
        "watermark=%s attempts=%d seconds=%.2f%s",
        result.table,
        result.mode,
        result.status,
        result.batch_id,
        result.extracted,
        result.inserted,
        result.duplicates,
        result.deleted,
        result.watermark_to.isoformat() if result.watermark_to else None,
        result.attempts,
        result.seconds,
        f" error={result.error!r}" if result.error else "",
    )
