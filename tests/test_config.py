from academic_platform.config import DatabaseSettings


def test_url_is_built_from_env(monkeypatch):
    monkeypatch.setenv("POSTGRES_USER", "u")
    monkeypatch.setenv("POSTGRES_PASSWORD", "p")
    monkeypatch.setenv("POSTGRES_HOST", "db")
    monkeypatch.setenv("POSTGRES_PORT", "6543")
    monkeypatch.setenv("POSTGRES_DB", "uni")

    settings = DatabaseSettings.from_env()

    assert settings.url == "postgresql+psycopg://u:p@db:6543/uni"


def test_port_is_integer(monkeypatch):
    monkeypatch.setenv("POSTGRES_PORT", "5433")
    assert DatabaseSettings.from_env().port == 5433


def test_warehouse_uses_warehouse_db_and_shares_server(monkeypatch):
    monkeypatch.setenv("POSTGRES_USER", "u")
    monkeypatch.setenv("POSTGRES_PASSWORD", "p")
    monkeypatch.setenv("POSTGRES_HOST", "db")
    monkeypatch.setenv("POSTGRES_PORT", "6543")
    monkeypatch.setenv("POSTGRES_DB", "uni")
    monkeypatch.setenv("WAREHOUSE_DB", "dwh")

    settings = DatabaseSettings.for_warehouse()

    assert settings.url == "postgresql+psycopg://u:p@db:6543/dwh"


def test_warehouse_db_defaults_to_warehouse(monkeypatch):
    monkeypatch.delenv("WAREHOUSE_DB", raising=False)
    assert DatabaseSettings.for_warehouse().name == "warehouse"


def test_dsn_quotes_special_characters(monkeypatch):
    monkeypatch.setenv("POSTGRES_PASSWORD", "p@ss word")
    monkeypatch.setenv("POSTGRES_DB", "uni")

    dsn = DatabaseSettings.from_env().dsn

    assert "password='p@ss word'" in dsn
    assert "dbname=uni" in dsn
