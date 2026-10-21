import pytest
from sqlalchemy import Connection, text

pytestmark = pytest.mark.db

UNINDEXED_FOREIGN_KEYS = """
    SELECT constraint_.conname
    FROM pg_constraint AS constraint_
    WHERE constraint_.contype = 'f'
      AND NOT EXISTS (
          SELECT 1
          FROM pg_index AS index_
          WHERE index_.indrelid = constraint_.conrelid
            AND index_.indkey[0] = constraint_.conkey[1]
      )
"""

TABLES_WITHOUT_UPDATED_AT_INDEX = """
    SELECT tablename
    FROM pg_tables
    WHERE schemaname = 'public'
      AND tablename <> 'alembic_version'
      AND NOT EXISTS (
          SELECT 1
          FROM pg_indexes
          WHERE pg_indexes.tablename = pg_tables.tablename
            AND pg_indexes.indexdef LIKE '%(updated_at)'
      )
"""

TABLES_WITHOUT_UPDATED_AT_TRIGGER = """
    SELECT tablename
    FROM pg_tables
    WHERE schemaname = 'public'
      AND tablename <> 'alembic_version'
      AND NOT EXISTS (
          SELECT 1
          FROM pg_trigger
          WHERE pg_trigger.tgname = 'trg_' || pg_tables.tablename || '_set_updated_at'
      )
"""

NON_RESTRICT_FOREIGN_KEYS = """
    SELECT conname
    FROM pg_constraint
    WHERE contype = 'f' AND confdeltype <> 'r'
    ORDER BY conname
"""


def names(db: Connection, query: str) -> list[str]:
    return list(db.execute(text(query)).scalars())


def test_every_foreign_key_column_is_indexed(db: Connection) -> None:
    assert names(db, UNINDEXED_FOREIGN_KEYS) == []


def test_every_table_has_an_updated_at_index(db: Connection) -> None:
    assert names(db, TABLES_WITHOUT_UPDATED_AT_INDEX) == []


def test_every_table_has_an_updated_at_trigger(db: Connection) -> None:
    assert names(db, TABLES_WITHOUT_UPDATED_AT_TRIGGER) == []


def test_only_prerequisite_pairs_cascade_on_delete(db: Connection) -> None:
    assert names(db, NON_RESTRICT_FOREIGN_KEYS) == [
        "fk_course_prerequisites_course",
        "fk_course_prerequisites_prerequisite",
    ]
