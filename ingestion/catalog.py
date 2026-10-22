"""Source metadata: which tables can be ingested, their columns, types and primary keys."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from psycopg import Connection

SOURCE_SCHEMA = "public"
CHANGE_COLUMN = "updated_at"


@dataclass(frozen=True)
class Column:
    name: str
    data_type: str


@dataclass(frozen=True)
class SourceTable:
    name: str
    key: str
    columns: tuple[Column, ...]

    @property
    def column_names(self) -> list[str]:
        return [column.name for column in self.columns]

    @property
    def key_type(self) -> str:
        return next(column.data_type for column in self.columns if column.name == self.key)


def column_type(
    data_type: str,
    udt_name: str,
    character_maximum_length: int | None,
    numeric_precision: int | None,
    numeric_scale: int | None,
) -> str:
    """Rebuild a column type from information_schema.columns, keeping lengths and precision."""
    if data_type == "USER-DEFINED":
        return udt_name
    if data_type == "ARRAY":
        return f"{udt_name.removeprefix('_')}[]"
    if character_maximum_length is not None:
        return f"{data_type}({character_maximum_length})"
    if data_type == "numeric" and numeric_precision is not None:
        return f"numeric({numeric_precision},{numeric_scale or 0})"
    return data_type


def source_tables(connection: Connection) -> list[SourceTable]:
    """Base tables in the source schema that have a single-column primary key and updated_at."""
    keys = dict(
        connection.execute(
            """
            SELECT constraint_.table_name, min(usage.column_name)
            FROM information_schema.table_constraints AS constraint_
            JOIN information_schema.key_column_usage AS usage
                ON usage.constraint_schema = constraint_.constraint_schema
                AND usage.constraint_name = constraint_.constraint_name
            WHERE constraint_.table_schema = %s AND constraint_.constraint_type = 'PRIMARY KEY'
            GROUP BY constraint_.table_name
            HAVING count(*) = 1
            """,
            (SOURCE_SCHEMA,),
        ).fetchall()
    )
    columns: dict[str, list[Column]] = {}
    for row in connection.execute(
        """
        SELECT column_.table_name, column_.column_name, column_.data_type, column_.udt_name,
               column_.character_maximum_length, column_.numeric_precision, column_.numeric_scale
        FROM information_schema.columns AS column_
        JOIN information_schema.tables AS table_
            ON table_.table_schema = column_.table_schema
            AND table_.table_name = column_.table_name
        WHERE column_.table_schema = %s AND table_.table_type = 'BASE TABLE'
        ORDER BY column_.table_name, column_.ordinal_position
        """,
        (SOURCE_SCHEMA,),
    ):
        table_name, column_name, *type_parts = row
        columns.setdefault(table_name, []).append(Column(column_name, column_type(*type_parts)))

    return [
        SourceTable(name, keys[name], tuple(table_columns))
        for name, table_columns in sorted(columns.items())
        if name in keys and CHANGE_COLUMN in {column.name for column in table_columns}
    ]


def select_tables(
    available: Sequence[SourceTable], requested: Sequence[str] | None
) -> list[SourceTable]:
    """The requested tables in the given order, or all available tables."""
    if not requested:
        return list(available)
    by_name = {table.name: table for table in available}
    unknown = [name for name in requested if name not in by_name]
    if unknown:
        raise ValueError(
            f"Not ingestible tables: {', '.join(unknown)}. "
            f"Choose from the {SOURCE_SCHEMA} schema: {', '.join(by_name)}"
        )
    return [by_name[name] for name in requested]
