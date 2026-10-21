"""Application settings loaded from environment variables (.env supported)."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

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
            password=os.getenv("POSTGRES_PASSWORD", "academic"),
            host=os.getenv("POSTGRES_HOST", "localhost"),
            port=int(os.getenv("POSTGRES_PORT", "5432")),
            name=os.getenv("POSTGRES_DB", "university"),
        )

    @property
    def url(self) -> str:
        """SQLAlchemy connection URL using the psycopg 3 driver."""
        return (
            f"postgresql+psycopg://{self.user}:{self.password}"
            f"@{self.host}:{self.port}/{self.name}"
        )
