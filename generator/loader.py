"""Bulk-load generated rows into the operational database with COPY."""

from __future__ import annotations

import logging
import time
from collections.abc import Sequence
from dataclasses import astuple, fields

from psycopg import sql
from sqlalchemy import Connection, text

from generator.models import ReferenceData

logger = logging.getLogger(__name__)

OLTP_TABLES = (
    "faculties",
    "programs",
    "professors",
    "semesters",
    "courses",
    "course_prerequisites",
    "students",
    "student_programs",
    "course_offerings",
    "enrollments",
    "exam_terms",
    "exam_attempts",
)


def load_reference_data(connection: Connection, data: ReferenceData) -> dict[str, int]:
    """Replace all operational data with the given reference data. Returns rows per table."""
    truncate_all(connection)
    counts: dict[str, int] = {}
    for field in fields(data):
        rows = getattr(data, field.name)
        started = time.perf_counter()
        counts[field.name] = copy_rows(connection, field.name, rows)
        if rows:
            reset_sequence(connection, field.name, fields(rows[0])[0].name)
        logger.info(
            "Loaded %d rows into %s in %.2f s",
            counts[field.name],
            field.name,
            time.perf_counter() - started,
        )
    return counts


def truncate_all(connection: Connection) -> None:
    connection.execute(text(f"TRUNCATE {', '.join(OLTP_TABLES)} RESTART IDENTITY"))


def copy_rows(connection: Connection, table: str, rows: Sequence[object]) -> int:
    """COPY dataclass rows into a table whose columns are named like the dataclass fields."""
    if not rows:
        return 0
    columns = [field.name for field in fields(rows[0])]
    statement = sql.SQL("COPY {} ({}) FROM STDIN").format(
        sql.Identifier(table), sql.SQL(", ").join(map(sql.Identifier, columns))
    )
    with connection.connection.driver_connection.cursor() as cursor:
        with cursor.copy(statement) as copy:
            for row in rows:
                copy.write_row(astuple(row))
    return len(rows)


def reset_sequence(connection: Connection, table: str, key: str) -> None:
    """Move the identity sequence past the highest loaded id so later inserts do not collide."""
    connection.execute(
        text(f"SELECT setval(pg_get_serial_sequence(:table, :key), MAX({key})) FROM {table}"),
        {"table": table, "key": key},
    )
