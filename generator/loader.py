"""Bulk-load generated rows into the operational database with COPY."""

from __future__ import annotations

import logging
import time
from collections.abc import Sequence
from dataclasses import dataclass, fields
from operator import attrgetter

from psycopg import sql
from sqlalchemy import Connection, text

from generator.models import History, ReferenceData

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
HISTORY_STATIC_TABLES = ("students", "student_programs", "course_offerings", "exam_terms")


@dataclass
class TableLoad:
    key: str
    rows: int = 0
    seconds: float = 0.0


def load_generated_data(
    connection: Connection, reference: ReferenceData, history: History | None = None
) -> dict[str, int]:
    """Replace all operational data with generated data. Returns rows loaded per table.

    Enrollments and exam attempts are loaded period by period, in chronological order, so the
    prerequisite trigger sees every passing attempt that an enrollment depends on.
    """
    truncate_all(connection)
    loads: dict[str, TableLoad] = {}
    for field in fields(reference):
        copy_table(connection, field.name, getattr(reference, field.name), loads)
    if history is not None:
        for table in HISTORY_STATIC_TABLES:
            copy_table(connection, table, getattr(history, table), loads)
        for batch in history.batches:
            copy_table(connection, "enrollments", batch.enrollments, loads)
            copy_table(connection, "exam_attempts", batch.exam_attempts, loads)

    for table, load in loads.items():
        reset_sequence(connection, table, load.key)
        logger.info("Loaded %d rows into %s in %.2f s", load.rows, table, load.seconds)
    return {table: load.rows for table, load in loads.items()}


def truncate_all(connection: Connection) -> None:
    connection.execute(text(f"TRUNCATE {', '.join(OLTP_TABLES)} RESTART IDENTITY"))


def copy_table(
    connection: Connection, table: str, rows: Sequence[object], loads: dict[str, TableLoad]
) -> None:
    if not rows:
        return
    columns = [field.name for field in fields(rows[0])]
    load = loads.setdefault(table, TableLoad(key=columns[0]))
    started = time.perf_counter()
    copy_rows(connection, table, columns, rows)
    load.rows += len(rows)
    load.seconds += time.perf_counter() - started


def copy_rows(
    connection: Connection, table: str, columns: list[str], rows: Sequence[object]
) -> None:
    """COPY dataclass rows into a table whose columns are named like the dataclass fields."""
    statement = sql.SQL("COPY {} ({}) FROM STDIN").format(
        sql.Identifier(table), sql.SQL(", ").join(map(sql.Identifier, columns))
    )
    values = attrgetter(*columns)
    with connection.connection.driver_connection.cursor() as cursor:
        with cursor.copy(statement) as copy:
            for row in rows:
                copy.write_row(values(row))


def reset_sequence(connection: Connection, table: str, key: str) -> None:
    """Move the identity sequence past the highest loaded id so later inserts do not collide."""
    connection.execute(
        text(f"SELECT setval(pg_get_serial_sequence(:table, :key), MAX({key})) FROM {table}"),
        {"table": table, "key": key},
    )
