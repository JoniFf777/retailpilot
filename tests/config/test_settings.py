from app.core.settings import (
    DEFAULT_DATABASE_URL,
    DEFAULT_SHOPMIND_AGENT_MODE,
    DEFAULT_SHOPMIND_SUPERVISOR_ROUTER,
    DEFAULT_TEST_DATABASE_URL,
    Settings,
)


def test_settings_uses_default_database_urls(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("TEST_DATABASE_URL", raising=False)
    monkeypatch.setattr("app.core.settings.load_dotenv", None)

    settings = Settings.from_env()

    assert settings.database_url == DEFAULT_DATABASE_URL
    assert settings.test_database_url == DEFAULT_TEST_DATABASE_URL
    assert settings.database_url.startswith("postgresql+psycopg://")
    assert "@127.0.0.1:5432/" in settings.database_url
    assert "connect_timeout=5" in settings.database_url


def test_settings_reads_database_urls_from_environment(monkeypatch):
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg://custom:custom@127.0.0.1:5432/custom_db?connect_timeout=5",
    )
    monkeypatch.setenv(
        "TEST_DATABASE_URL",
        "postgresql+psycopg://custom:custom@127.0.0.1:5432/custom_test_db?connect_timeout=5",
    )
    monkeypatch.setenv("VECTOR_DIMENSION", "1536")
    monkeypatch.setenv("LANGSMITH_TRACING", "false")

    settings = Settings.from_env()

    assert (
        settings.database_url
        == "postgresql+psycopg://custom:custom@127.0.0.1:5432/custom_db?connect_timeout=5"
    )
    assert (
        settings.test_database_url
        == "postgresql+psycopg://custom:custom@127.0.0.1:5432/custom_test_db?connect_timeout=5"
    )
    assert settings.vector_dimension == 1536
    assert settings.langsmith_tracing is False


def test_settings_defaults_shopmind_agent_mode_to_single(monkeypatch):
    monkeypatch.delenv("SHOPMIND_AGENT_MODE", raising=False)
    monkeypatch.delenv("SHOPMIND_SUPERVISOR_ROUTER", raising=False)
    monkeypatch.setattr("app.core.settings.load_dotenv", None)

    settings = Settings.from_env()

    assert settings.shopmind_agent_mode == DEFAULT_SHOPMIND_AGENT_MODE
    assert settings.shopmind_supervisor_router == DEFAULT_SHOPMIND_SUPERVISOR_ROUTER


def test_settings_reads_multi_agent_mode(monkeypatch):
    monkeypatch.setenv("SHOPMIND_AGENT_MODE", "multi")
    monkeypatch.setenv("SHOPMIND_SUPERVISOR_ROUTER", "llm")

    settings = Settings.from_env()

    assert settings.shopmind_agent_mode == "multi"
    assert settings.shopmind_supervisor_router == "llm"


def test_settings_defaults_invalid_supervisor_router_to_deterministic(monkeypatch):
    monkeypatch.setenv("SHOPMIND_SUPERVISOR_ROUTER", "unknown")

    settings = Settings.from_env()

    assert settings.shopmind_supervisor_router == DEFAULT_SHOPMIND_SUPERVISOR_ROUTER
