"""Warehouse side: meta tables, raw tables built from source metadata, and schema drift checks."""

from __future__ import annotations

import logging
from datetime import datetime

from psycopg import Connection, sql

from ingestion.catalog import SourceTable, column_type

logger = logging.getLogger(__name__)

RAW_SCHEMA = "raw"
META_SCHEMA = "meta"

META_DDL = """
    CREATE SCHEMA IF NOT EXISTS raw;
    CREATE SCHEMA IF NOT EXISTS meta;

    CREATE TABLE IF NOT EXISTS meta.load_batches (
        batch_id        BIGINT GENERATED ALWAYS AS IDENTITY,
        table_name      TEXT NOT NULL,
        mode            TEXT NOT NULL,
        status          TEXT NOT NULL,
        started_at      TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
        finished_at     TIMESTAMPTZ,
        watermark_from  TIMESTAMPTZ,
        watermark_to    TIMESTAMPTZ,
        rows_extracted  BIGINT,
        rows_inserted   BIGINT,
        rows_duplicate  BIGINT,
        rows_deleted    BIGINT,
        error_message   TEXT,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
        CONSTRAINT pk_load_batches PRIMARY KEY (batch_id),
        CONSTRAINT ck_load_batches_mode CHECK (mode IN ('incremental', 'full')),
        CONSTRAINT ck_load_batches_status CHECK (status IN ('running', 'succeeded', 'failed'))
    );

    CREATE INDEX IF NOT EXISTS ix_load_batches_table_name ON meta.load_batches (table_name);

    CREATE TABLE IF NOT EXISTS meta.watermarks (
        watermark_id     BIGINT GENERATED ALWAYS AS IDENTITY,
        table_name       TEXT NOT NULL,
        last_updated_at  TIMESTAMPTZ NOT NULL,
        created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
        CONSTRAINT pk_watermarks PRIMARY KEY (watermark_id),
        CONSTRAINT uq_watermarks_table_name UNIQUE (table_name)
    );
"""

RAW_METADATA_COLUMNS = (
    ("_batch_id", "bigint NOT NULL"),
    ("_loaded_at", "timestamp with time zone NOT NULL"),
    ("_source_updated_at", "timestamp with time zone NOT NULL"),
    ("_is_deleted", "boolean NOT NULL DEFAULT false"),
    ("_deleted_at", "timestamp with time zone"),
)


class SchemaDriftError(Exception):
    """A source column changed in a way the raw layer cannot absorb automatically."""


def ensure_meta(connection: Connection) -> None:
    """Create the raw and meta schemas and the meta tables if they do not exist yet."""
    connection.execute(META_DDL)


def ensure_raw_table(connection: Connection, table: SourceTable) -> list[str]:
    """Create raw.<table> or align it with the source. Returns the names of added columns."""
    existing = raw_columns(connection, table.name)
    if not existing:
        create_raw_table(connection, table)
        return []

    added = []
    for column in table.columns:
        raw_type = existing.get(column.name)
        if raw_type is None:
            connection.execute(
                sql.SQL("ALTER TABLE {} ADD COLUMN {} {}").format(
                    sql.Identifier(RAW_SCHEMA, table.name),
                    sql.Identifier(column.name),
                    sql.SQL(column.data_type),
                )
            )
            added.append(column.name)
            logger.info(
                "table=%s added raw column %s %s", table.name, column.name, column.data_type
            )
        elif raw_type != column.data_type:
            raise SchemaDriftError(
                f"Column {table.name}.{column.name} is {column.data_type} in the source "
                f"but {raw_type} in {RAW_SCHEMA}.{table.name}; change the raw column before loading"
            )
    return added


def create_raw_table(connection: Connection, table: SourceTable) -> None:
    """Every source column (nullable, so dropped source columns cannot break loads) plus
    load metadata, unique on the source key and the source updated_at."""
    columns = [
        sql.SQL("{} {}").format(sql.Identifier(column.name), sql.SQL(column.data_type))
        for column in table.columns
    ] + [
        sql.SQL("{} {}").format(sql.Identifier(name), sql.SQL(definition))
        for name, definition in RAW_METADATA_COLUMNS
    ]
    connection.execute(
        sql.SQL(
            "CREATE TABLE {table} ("
            "_raw_id bigint GENERATED ALWAYS AS IDENTITY, {columns}, "
            "CONSTRAINT {primary_key} PRIMARY KEY (_raw_id), "
            "CONSTRAINT {unique_version} UNIQUE ({key}, _source_updated_at))"
        ).format(
            table=sql.Identifier(RAW_SCHEMA, table.name),
            columns=sql.SQL(", ").join(columns),
            primary_key=sql.Identifier(f"pk_raw_{table.name}"),
            unique_version=sql.Identifier(version_constraint(table.name)),
            key=sql.Identifier(table.key),
        )
    )
    logger.info("table=%s created %s.%s", table.name, RAW_SCHEMA, table.name)


def version_constraint(table_name: str) -> str:
    return f"uq_raw_{table_name}_version"


def raw_columns(connection: Connection, table_name: str) -> dict[str, str]:
    """Source-mirroring columns of raw.<table> and their types, without load metadata."""
    rows = connection.execute(
        """
        SELECT column_name, data_type, udt_name, character_maximum_length,
               numeric_precision, numeric_scale
        FROM information_schema.columns
        WHERE table_schema = %s AND table_name = %s AND column_name NOT LIKE '\\_%%'
        ORDER BY ordinal_position
        """,
        (RAW_SCHEMA, table_name),
    ).fetchall()
    return {name: column_type(*type_parts) for name, *type_parts in rows}


def read_watermark(connection: Connection, table_name: str) -> datetime | None:
    row = connection.execute(
        "SELECT last_updated_at FROM meta.watermarks WHERE table_name = %s", (table_name,)
    ).fetchone()
    return row[0] if row else None


def save_watermark(connection: Connection, table_name: str, last_updated_at: datetime) -> None:
    connection.execute(
        """
        INSERT INTO meta.watermarks (table_name, last_updated_at)
        VALUES (%s, %s)
        ON CONFLICT ON CONSTRAINT uq_watermarks_table_name DO UPDATE
        SET last_updated_at = EXCLUDED.last_updated_at, updated_at = now()
        """,
        (table_name, last_updated_at),
    )
