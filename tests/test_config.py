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
