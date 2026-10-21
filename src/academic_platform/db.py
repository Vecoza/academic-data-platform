"""Database engine factory and a simple connectivity check."""

from __future__ import annotations

import sys

from sqlalchemy import Engine, create_engine, text

from academic_platform.config import DatabaseSettings


def get_engine(settings: DatabaseSettings | None = None) -> Engine:
    settings = settings or DatabaseSettings.from_env()
    return create_engine(settings.url, pool_pre_ping=True)


def check_connection() -> str:
    """Return the PostgreSQL server version, raising if the database is unreachable."""
    with get_engine().connect() as conn:
        return conn.execute(text("SELECT version()")).scalar_one()


if __name__ == "__main__":
    try:
        print(f"Connected: {check_connection()}")
    except Exception as exc:
        print(f"Database connection failed: {exc}", file=sys.stderr)
        sys.exit(1)
