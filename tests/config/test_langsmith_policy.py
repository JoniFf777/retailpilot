import logging

import pytest

from app.core import langsmith_policy
from app.core.langsmith_policy import initialize_langsmith_runtime
from app.core.settings import Settings


LANGSMITH_ENV_NAMES = (
    "SHOPMIND_DEPLOYMENT_PROFILE",
    "LANGSMITH_TRACING",
    "LANGCHAIN_TRACING_V2",
    "LANGSMITH_API_KEY",
    "LANGSMITH_PROJECT",
    "LANGSMITH_ENDPOINT",
    "LANGSMITH_TRACING_SAMPLING_RATE",
)


@pytest.fixture(autouse=True)
def isolate_langsmith_environment(monkeypatch):
    for name in LANGSMITH_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(langsmith_policy, "load_dotenv", None)
    monkeypatch.setattr("app.core.settings.load_dotenv", None)


def test_default_is_fail_closed_and_sdk_environment_is_false():
    runtime = initialize_langsmith_runtime(load_environment=False)

    assert runtime.profile == "development"
    assert runtime.tracing_enabled is False
    assert runtime.project == "shopmind-development"
    assert runtime.sampling_rate == 1.0
    assert runtime.tracing_enabled is (False)
    assert langsmith_policy.os.environ["LANGSMITH_TRACING"] == "false"
    assert langsmith_policy.os.environ["LANGCHAIN_TRACING_V2"] == "false"


def test_demo_profile_uses_demo_defaults_when_key_is_present(monkeypatch):
    monkeypatch.setenv("SHOPMIND_DEPLOYMENT_PROFILE", "demo")
    monkeypatch.setenv("LANGSMITH_API_KEY", "test-only-key")

    runtime = initialize_langsmith_runtime(load_environment=False)

    assert runtime.profile == "demo"
    assert runtime.tracing_enabled is True
    assert runtime.project == "shopmind-demo"
    assert runtime.sampling_rate == 1.0
    assert langsmith_policy.os.environ["LANGSMITH_TRACING"] == "true"


def test_development_profile_honors_explicit_process_tracing(monkeypatch):
    monkeypatch.setenv("SHOPMIND_DEPLOYMENT_PROFILE", "development")
    monkeypatch.setenv("LANGSMITH_API_KEY", "test-only-key")
    monkeypatch.setenv("LANGSMITH_TRACING", "true")

    runtime = initialize_langsmith_runtime(load_environment=False)

    assert runtime.tracing_enabled is True
    assert langsmith_policy.os.environ["LANGSMITH_TRACING"] == "true"


def test_development_profile_overrides_stale_dotenv_tracing_default(monkeypatch):
    monkeypatch.setenv("SHOPMIND_DEPLOYMENT_PROFILE", "development")
    monkeypatch.setenv("LANGSMITH_API_KEY", "test-only-key")

    def fake_dotenv_loader(**_kwargs):
        langsmith_policy.os.environ["LANGSMITH_TRACING"] = "true"

    runtime = initialize_langsmith_runtime(dotenv_loader=fake_dotenv_loader)

    assert runtime.tracing_enabled is False
    assert langsmith_policy.os.environ["LANGSMITH_TRACING"] == "false"


def test_explicit_process_environment_overrides_profile_defaults(monkeypatch):
    monkeypatch.setenv("SHOPMIND_DEPLOYMENT_PROFILE", "production")
    monkeypatch.setenv("LANGSMITH_API_KEY", "test-only-key")
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    monkeypatch.setenv("LANGSMITH_PROJECT", "explicit-project")
    monkeypatch.setenv("LANGSMITH_TRACING_SAMPLING_RATE", "0.25")

    runtime = initialize_langsmith_runtime(load_environment=False)

    assert runtime.tracing_enabled is False
    assert runtime.project == "explicit-project"
    assert runtime.sampling_rate == 0.25
    assert langsmith_policy.os.environ["LANGSMITH_TRACING"] == "false"


def test_process_environment_beats_dotenv_values(monkeypatch):
    monkeypatch.setenv("SHOPMIND_DEPLOYMENT_PROFILE", "demo")
    monkeypatch.setenv("LANGSMITH_API_KEY", "test-only-key")
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    monkeypatch.setenv("LANGSMITH_PROJECT", "process-project")
    monkeypatch.setenv("LANGSMITH_TRACING_SAMPLING_RATE", "0.2")

    def fake_dotenv_loader(**_kwargs):
        langsmith_policy.os.environ.setdefault("LANGSMITH_TRACING", "true")
        langsmith_policy.os.environ.setdefault(
            "LANGSMITH_PROJECT", "dotenv-project"
        )
        langsmith_policy.os.environ.setdefault(
            "LANGSMITH_TRACING_SAMPLING_RATE", "0.9"
        )

    runtime = initialize_langsmith_runtime(dotenv_loader=fake_dotenv_loader)

    assert runtime.tracing_enabled is False
    assert runtime.project == "process-project"
    assert runtime.sampling_rate == 0.2


@pytest.mark.parametrize("profile", ["production", "public-demo"])
def test_production_profiles_share_production_defaults(monkeypatch, profile):
    monkeypatch.setenv("SHOPMIND_DEPLOYMENT_PROFILE", profile)
    monkeypatch.setenv("LANGSMITH_API_KEY", "test-only-key")

    runtime = initialize_langsmith_runtime(load_environment=False)

    assert runtime.profile == "production"
    assert runtime.project == "shopmind-production"
    assert runtime.sampling_rate == 0.1
    assert runtime.tracing_enabled is True
    assert langsmith_policy.os.environ["SHOPMIND_DEPLOYMENT_PROFILE"] == "production"


def test_missing_key_for_enabled_profile_forces_sdk_tracing_off(caplog, monkeypatch):
    monkeypatch.setenv("SHOPMIND_DEPLOYMENT_PROFILE", "demo")
    monkeypatch.setenv("LANGSMITH_TRACING", "true")

    with caplog.at_level(logging.WARNING):
        runtime = initialize_langsmith_runtime(load_environment=False)

    assert runtime.tracing_enabled is False
    assert langsmith_policy.os.environ["LANGSMITH_TRACING"] == "false"
    assert "test-only-key" not in caplog.text
    assert "LANGSMITH_API_KEY is not configured" in caplog.text


def test_invalid_sampling_rate_forces_sdk_tracing_off(monkeypatch):
    monkeypatch.setenv("SHOPMIND_DEPLOYMENT_PROFILE", "demo")
    monkeypatch.setenv("LANGSMITH_API_KEY", "test-only-key")
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGSMITH_TRACING_SAMPLING_RATE", "not-a-rate")

    runtime = initialize_langsmith_runtime(load_environment=False)

    assert runtime.tracing_enabled is False
    assert langsmith_policy.os.environ["LANGSMITH_TRACING"] == "false"


@pytest.mark.parametrize(
    "failure",
    [RuntimeError("401"), RuntimeError("429"), RuntimeError("5xx"), TimeoutError()],
)
def test_configuration_failure_is_fail_closed_and_non_fatal(monkeypatch, failure):
    def fail_loader(**_kwargs):
        raise failure

    runtime = initialize_langsmith_runtime(dotenv_loader=fail_loader)

    assert runtime.tracing_enabled is False
    assert langsmith_policy.os.environ["LANGSMITH_TRACING"] == "false"
    assert langsmith_policy.os.environ["LANGCHAIN_TRACING_V2"] == "false"


def test_settings_does_not_expose_key_in_repr(monkeypatch):
    monkeypatch.setenv("SHOPMIND_DEPLOYMENT_PROFILE", "demo")
    monkeypatch.setenv("LANGSMITH_API_KEY", "test-only-key")
    monkeypatch.setenv("LANGSMITH_TRACING", "false")

    settings = Settings.from_env()

    assert settings.langsmith_api_key is not None
    assert settings.langsmith_api_key.get_secret_value() == "test-only-key"
    assert "test-only-key" not in repr(settings)
