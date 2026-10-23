"""Application settings loaded from environment variables (.env supported)."""

from __future__ import annotations

import os
from dataclasses import dataclass, replace

from dotenv import load_dotenv
from psycopg.conninfo import make_conninfo

load_dotenv()


@dataclass(frozen=True)
class DatabaseSettings:
    user: str
    password: str
    host: str
    port: int
    name: str

    @classmethod
    def from_env(cls) -> DatabaseSettings:
        return cls(
            user=os.getenv("POSTGRES_USER", "academic"),
            password=os.getenv("POSTGRES_PASSWORD", "adp_local_pw_2026"),
            host=os.getenv("POSTGRES_HOST", "localhost"),
            port=int(os.getenv("POSTGRES_PORT", "5432")),
            name=os.getenv("POSTGRES_DB", "university"),
        )

    @classmethod
    def for_warehouse(cls) -> DatabaseSettings:
        """Settings for the analytical database on the same server."""
        return replace(cls.from_env(), name=os.getenv("WAREHOUSE_DB", "warehouse"))

    @classmethod
    def for_dashboard(cls) -> DatabaseSettings:
        """Warehouse settings with the read-only dashboard role instead of the owner."""
        return replace(
            cls.for_warehouse(),
            user=os.getenv("DASHBOARD_USER", "dashboard_reader"),
            password=os.getenv("DASHBOARD_PASSWORD", "adp_dashboard_pw_2026"),
        )

    @property
    def url(self) -> str:
        """SQLAlchemy connection URL using the psycopg 3 driver."""
        return (
            f"postgresql+psycopg://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"
        )

    @property
    def dsn(self) -> str:
        """libpq connection string for direct psycopg connections."""
        return make_conninfo(
            host=self.host, port=self.port, dbname=self.name, user=self.user, password=self.password
        )
