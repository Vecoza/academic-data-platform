"""Create the read-only dashboard role and grant it SELECT on the marts schema, idempotently.

Run as the warehouse owner: python -m dashboard.access. Default privileges make tables that
dbt creates or rebuilds later readable as well, so no grant has to be repeated after a build.
"""

from __future__ import annotations

import logging

import psycopg
from psycopg import sql

from academic_platform.config import DatabaseSettings

logger = logging.getLogger(__name__)

MARTS_SCHEMA = "marts"


def ensure_reader_role(owner: DatabaseSettings, reader: DatabaseSettings) -> None:
    """Create or update the reader role with access to nothing but SELECT on marts."""
    role = sql.Identifier(reader.user)
    schema = sql.Identifier(MARTS_SCHEMA)
    with psycopg.connect(owner.dsn, autocommit=True) as connection:
        exists = connection.execute(
            "SELECT 1 FROM pg_roles WHERE rolname = %s", (reader.user,)
        ).fetchone()
        action = "ALTER" if exists else "CREATE"
        connection.execute(
            sql.SQL(
                "{action} ROLE {role} WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE "
                "NOINHERIT PASSWORD {password}"
            ).format(action=sql.SQL(action), role=role, password=sql.Literal(reader.password))
        )
        connection.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(schema))
        for statement in (
            "GRANT CONNECT ON DATABASE {database} TO {role}",
            "GRANT USAGE ON SCHEMA {schema} TO {role}",
            "GRANT SELECT ON ALL TABLES IN SCHEMA {schema} TO {role}",
            "ALTER DEFAULT PRIVILEGES IN SCHEMA {schema} GRANT SELECT ON TABLES TO {role}",
        ):
            connection.execute(
                sql.SQL(statement).format(
                    database=sql.Identifier(owner.name), schema=schema, role=role
                )
            )
    logger.info("Role %s can read %s.%s", reader.user, owner.name, MARTS_SCHEMA)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    ensure_reader_role(DatabaseSettings.for_warehouse(), DatabaseSettings.for_dashboard())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
