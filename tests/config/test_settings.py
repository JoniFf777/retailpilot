import pytest
from pydantic import ValidationError

from app.core.settings import (
    DEFAULT_DATABASE_URL,
    DEFAULT_SHOPMIND_AGENT_MODE,
    DEFAULT_SHOPMIND_AGENT_PLANNER,
    DEFAULT_SHOPMIND_AGENT_TASK_MAX_ATTEMPTS,
    DEFAULT_SHOPMIND_DEPLOYMENT_PROFILE,
    DEFAULT_SHOPMIND_DEPLOYMENT_REPLICAS,
    DEFAULT_SHOPMIND_RAG_AGENT_HTTP_MAX_RESPONSE_BYTES,
    DEFAULT_SHOPMIND_RAG_AGENT_HTTP_TIMEOUT_SECONDS,
    DEFAULT_SHOPMIND_RAG_AGENT_TRANSPORT,
    DEFAULT_SHOPMIND_SUPERVISOR_ROUTER,
    DEFAULT_SHOPMIND_RUNTIME_CLEANUP_SCHEDULED,
    DEFAULT_SHOPMIND_RUNTIME_CLEANUP_EVIDENCE_MAX_AGE_SECONDS,
    DEFAULT_SHOPMIND_SERVICE_SLO_MIN_RUNS,
    DEFAULT_SHOPMIND_SERVICE_SLO_P95_LATENCY_MS,
    DEFAULT_SHOPMIND_SERVICE_SLO_SUCCESS_RATE_TARGET,
    DEFAULT_SHOPMIND_TRUSTED_PROXY_AUTHENTICATION,
    DEFAULT_SHOPMIND_STREAM_EVENT_BUFFER_SIZE,
    DEFAULT_SHOPMIND_STREAM_MAX_CONCURRENCY,
    DEFAULT_SHOPMIND_COORDINATION_BACKEND,
    DEFAULT_SHOPMIND_GOVERNANCE_AUDIT_ALERT_FAILURE_THRESHOLD,
    DEFAULT_SHOPMIND_GOVERNANCE_AUDIT_ENABLED,
    DEFAULT_SHOPMIND_IDENTITY_PROVIDER,
    DEFAULT_SHOPMIND_IDENTITY_SIGNATURE_CLOCK_SKEW_SECONDS,
    DEFAULT_SHOPMIND_IDENTITY_SIGNATURE_MAX_AGE_SECONDS,
    DEFAULT_SHOPMIND_STREAM_ADMISSION_LEASE_TTL_MS,
    DEFAULT_SHOPMIND_STREAM_ADMISSION_RENEW_INTERVAL_MS,
    DEFAULT_SHOPMIND_PARALLEL_READ_ENABLED,
    DEFAULT_SHOPMIND_PARALLEL_READ_MAX_WORKERS,
    MAX_SHOPMIND_PARALLEL_READ_WORKERS,
    MAX_SHOPMIND_DEPLOYMENT_REPLICAS,
    MAX_SHOPMIND_AGENT_TASK_MAX_ATTEMPTS,
    MAX_SHOPMIND_GOVERNANCE_AUDIT_ALERT_FAILURE_THRESHOLD,
    MAX_SHOPMIND_RUNTIME_CLEANUP_EVIDENCE_MAX_AGE_SECONDS,
    MAX_SHOPMIND_SERVICE_SLO_MIN_RUNS,
    MAX_SHOPMIND_SERVICE_SLO_P95_LATENCY_MS,
    MAX_SHOPMIND_IDENTITY_SIGNATURE_CLOCK_SKEW_SECONDS,
    MAX_SHOPMIND_IDENTITY_SIGNATURE_MAX_AGE_SECONDS,
    DEFAULT_TEST_DATABASE_URL,
    Settings,
)


def test_settings_reads_bounded_production_deployment_declarations(
    monkeypatch,
):
    for name in (
        "SHOPMIND_DEPLOYMENT_PROFILE",
        "SHOPMIND_DEPLOYMENT_REPLICAS",
        "SHOPMIND_TRUSTED_PROXY_AUTHENTICATION",
        "SHOPMIND_RUNTIME_CLEANUP_SCHEDULED",
        "SHOPMIND_RUNTIME_CLEANUP_EVIDENCE_PATH",
        "SHOPMIND_RUNTIME_CLEANUP_EVIDENCE_MAX_AGE_SECONDS",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr("app.core.settings.load_dotenv", None)

    default = Settings.from_env()

    assert default.shopmind_deployment_profile == (
        DEFAULT_SHOPMIND_DEPLOYMENT_PROFILE
    )
    assert default.shopmind_deployment_replicas == (
        DEFAULT_SHOPMIND_DEPLOYMENT_REPLICAS
    )
    assert default.shopmind_trusted_proxy_authentication is (
        DEFAULT_SHOPMIND_TRUSTED_PROXY_AUTHENTICATION
    )
    assert default.shopmind_runtime_cleanup_scheduled is (
        DEFAULT_SHOPMIND_RUNTIME_CLEANUP_SCHEDULED
    )
    assert default.shopmind_runtime_cleanup_evidence_path is None
    assert default.shopmind_runtime_cleanup_evidence_max_age_seconds == (
        DEFAULT_SHOPMIND_RUNTIME_CLEANUP_EVIDENCE_MAX_AGE_SECONDS
    )

    monkeypatch.setenv("SHOPMIND_DEPLOYMENT_PROFILE", "production")
    monkeypatch.setenv("SHOPMIND_DEPLOYMENT_REPLICAS", "99999")
    monkeypatch.setenv("SHOPMIND_TRUSTED_PROXY_AUTHENTICATION", "true")
    monkeypatch.setenv("SHOPMIND_RUNTIME_CLEANUP_SCHEDULED", "true")
    monkeypatch.setenv(
        "SHOPMIND_RUNTIME_CLEANUP_EVIDENCE_PATH",
        "artifacts/cleanup-success.json",
    )
    monkeypatch.setenv(
        "SHOPMIND_RUNTIME_CLEANUP_EVIDENCE_MAX_AGE_SECONDS",
        "999999",
    )
    production = Settings.from_env()

    assert production.shopmind_deployment_profile == "production"
    assert production.shopmind_deployment_replicas == (
        MAX_SHOPMIND_DEPLOYMENT_REPLICAS
    )
    assert production.shopmind_trusted_proxy_authentication is True
    assert production.shopmind_runtime_cleanup_scheduled is True
    assert production.shopmind_runtime_cleanup_evidence_path == (
        "artifacts/cleanup-success.json"
    )
    assert production.shopmind_runtime_cleanup_evidence_max_age_seconds == (
        MAX_SHOPMIND_RUNTIME_CLEANUP_EVIDENCE_MAX_AGE_SECONDS
    )

    monkeypatch.setenv("SHOPMIND_DEPLOYMENT_PROFILE", "staging")
    monkeypatch.setenv("SHOPMIND_DEPLOYMENT_REPLICAS", "0")
    fallback = Settings.from_env()

    assert fallback.shopmind_deployment_profile == (
        DEFAULT_SHOPMIND_DEPLOYMENT_PROFILE
    )
    assert fallback.shopmind_deployment_replicas == (
        DEFAULT_SHOPMIND_DEPLOYMENT_REPLICAS
    )


def test_settings_reads_bounded_service_slo_policy(monkeypatch) -> None:
    for name in (
        "SHOPMIND_SERVICE_SLO_MIN_RUNS",
        "SHOPMIND_SERVICE_SLO_SUCCESS_RATE_TARGET",
        "SHOPMIND_SERVICE_SLO_P95_LATENCY_MS",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr("app.core.settings.load_dotenv", None)

    default = Settings.from_env()

    assert default.shopmind_service_slo_min_runs == (
        DEFAULT_SHOPMIND_SERVICE_SLO_MIN_RUNS
    )
    assert default.shopmind_service_slo_success_rate_target == (
        DEFAULT_SHOPMIND_SERVICE_SLO_SUCCESS_RATE_TARGET
    )
    assert default.shopmind_service_slo_p95_latency_ms == (
        DEFAULT_SHOPMIND_SERVICE_SLO_P95_LATENCY_MS
    )

    monkeypatch.setenv("SHOPMIND_SERVICE_SLO_MIN_RUNS", "999999")
    monkeypatch.setenv("SHOPMIND_SERVICE_SLO_SUCCESS_RATE_TARGET", "2.0")
    monkeypatch.setenv("SHOPMIND_SERVICE_SLO_P95_LATENCY_MS", "999999")
    bounded = Settings.from_env()

    assert bounded.shopmind_service_slo_min_runs == (
        MAX_SHOPMIND_SERVICE_SLO_MIN_RUNS
    )
    assert bounded.shopmind_service_slo_success_rate_target == 1.0
    assert bounded.shopmind_service_slo_p95_latency_ms == (
        MAX_SHOPMIND_SERVICE_SLO_P95_LATENCY_MS
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
    monkeypatch.delenv("SHOPMIND_AGENT_PLANNER", raising=False)
    monkeypatch.setattr("app.core.settings.load_dotenv", None)

    settings = Settings.from_env()

    assert settings.shopmind_agent_mode == DEFAULT_SHOPMIND_AGENT_MODE
    assert settings.shopmind_supervisor_router == DEFAULT_SHOPMIND_SUPERVISOR_ROUTER
    assert settings.shopmind_agent_planner == DEFAULT_SHOPMIND_AGENT_PLANNER


def test_settings_reads_multi_agent_mode(monkeypatch):
    monkeypatch.setenv("SHOPMIND_AGENT_MODE", "multi")
    monkeypatch.setenv("SHOPMIND_SUPERVISOR_ROUTER", "llm")
    monkeypatch.setenv("SHOPMIND_AGENT_PLANNER", "llm")

    settings = Settings.from_env()

    assert settings.shopmind_agent_mode == "multi"
    assert settings.shopmind_supervisor_router == "llm"
    assert settings.shopmind_agent_planner == "llm"


def test_settings_defaults_invalid_supervisor_router_to_deterministic(monkeypatch):
    monkeypatch.setenv("SHOPMIND_SUPERVISOR_ROUTER", "unknown")
    monkeypatch.setenv("SHOPMIND_AGENT_PLANNER", "unknown")

    settings = Settings.from_env()

    assert settings.shopmind_supervisor_router == DEFAULT_SHOPMIND_SUPERVISOR_ROUTER
    assert settings.shopmind_agent_planner == DEFAULT_SHOPMIND_AGENT_PLANNER


def test_settings_reads_positive_stream_controls_and_falls_back_for_invalid_values(monkeypatch):
    monkeypatch.setenv("SHOPMIND_STREAM_MAX_CONCURRENCY", "3")
    monkeypatch.setenv("SHOPMIND_STREAM_EVENT_BUFFER_SIZE", "16")

    settings = Settings.from_env()

    assert settings.shopmind_stream_max_concurrency == 3
    assert settings.shopmind_stream_event_buffer_size == 16

    monkeypatch.setenv("SHOPMIND_STREAM_MAX_CONCURRENCY", "0")
    monkeypatch.setenv("SHOPMIND_STREAM_EVENT_BUFFER_SIZE", "invalid")

    fallback_settings = Settings.from_env()

    assert fallback_settings.shopmind_stream_max_concurrency == (
        DEFAULT_SHOPMIND_STREAM_MAX_CONCURRENCY
    )
    assert fallback_settings.shopmind_stream_event_buffer_size == (
        DEFAULT_SHOPMIND_STREAM_EVENT_BUFFER_SIZE
    )


def test_settings_reads_coordination_backend_and_normalizes_stream_lease_timing(
    monkeypatch,
):
    monkeypatch.setenv("SHOPMIND_COORDINATION_BACKEND", "redis")
    monkeypatch.setenv(
        "SHOPMIND_COORDINATION_REDIS_URL",
        "redis://:private-value@127.0.0.1:6379/0",
    )
    monkeypatch.setenv("SHOPMIND_STREAM_ADMISSION_LEASE_TTL_MS", "9000")
    monkeypatch.setenv("SHOPMIND_STREAM_ADMISSION_RENEW_INTERVAL_MS", "9000")

    settings = Settings.from_env()

    assert settings.shopmind_coordination_backend == "redis"
    assert settings.shopmind_coordination_redis_url is not None
    assert "private-value" not in repr(settings)
    assert settings.shopmind_stream_admission_lease_ttl_ms == 9000
    assert settings.shopmind_stream_admission_renew_interval_ms == 3000

    monkeypatch.setenv("SHOPMIND_COORDINATION_BACKEND", "unknown")
    monkeypatch.delenv("SHOPMIND_COORDINATION_REDIS_URL")
    monkeypatch.setenv("SHOPMIND_STREAM_ADMISSION_LEASE_TTL_MS", "invalid")
    monkeypatch.setenv("SHOPMIND_STREAM_ADMISSION_RENEW_INTERVAL_MS", "invalid")

    fallback = Settings.from_env()

    assert fallback.shopmind_coordination_backend == DEFAULT_SHOPMIND_COORDINATION_BACKEND
    assert fallback.shopmind_stream_admission_lease_ttl_ms == (
        DEFAULT_SHOPMIND_STREAM_ADMISSION_LEASE_TTL_MS
    )
    assert fallback.shopmind_stream_admission_renew_interval_ms == (
        DEFAULT_SHOPMIND_STREAM_ADMISSION_RENEW_INTERVAL_MS
    )


def test_settings_selects_identity_provider_only_from_server_environment(monkeypatch):
    for name in (
        "SHOPMIND_IDENTITY_PROVIDER",
        "SHOPMIND_IDENTITY_SIGNING_SECRET",
        "SHOPMIND_IDENTITY_SIGNATURE_MAX_AGE_SECONDS",
        "SHOPMIND_IDENTITY_SIGNATURE_CLOCK_SKEW_SECONDS",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr("app.core.settings.load_dotenv", None)

    default = Settings.from_env()
    assert default.shopmind_identity_provider == DEFAULT_SHOPMIND_IDENTITY_PROVIDER

    monkeypatch.setenv("SHOPMIND_IDENTITY_PROVIDER", "trusted_header")
    trusted = Settings.from_env()
    assert trusted.shopmind_identity_provider == "trusted_header"

    monkeypatch.setenv("SHOPMIND_IDENTITY_PROVIDER", "payload_roles")
    fallback = Settings.from_env()
    assert fallback.shopmind_identity_provider == DEFAULT_SHOPMIND_IDENTITY_PROVIDER


def test_settings_requires_a_strong_secret_for_signed_identity(monkeypatch):
    monkeypatch.setattr("app.core.settings.load_dotenv", None)
    monkeypatch.setenv("SHOPMIND_IDENTITY_PROVIDER", "signed_header")
    monkeypatch.delenv("SHOPMIND_IDENTITY_SIGNING_SECRET", raising=False)

    with pytest.raises(ValidationError, match="signing secret"):
        Settings.from_env()

    monkeypatch.setenv("SHOPMIND_IDENTITY_SIGNING_SECRET", "too-short")
    with pytest.raises(ValidationError, match="too short"):
        Settings.from_env()


def test_settings_reads_and_masks_signed_identity_configuration(monkeypatch):
    signing_secret = "signed-identity-settings-secret-32-bytes-minimum"
    monkeypatch.setattr("app.core.settings.load_dotenv", None)
    monkeypatch.setenv("SHOPMIND_IDENTITY_PROVIDER", "signed_header")
    monkeypatch.setenv("SHOPMIND_IDENTITY_SIGNING_SECRET", signing_secret)
    monkeypatch.setenv("SHOPMIND_IDENTITY_SIGNATURE_MAX_AGE_SECONDS", "90")
    monkeypatch.setenv("SHOPMIND_IDENTITY_SIGNATURE_CLOCK_SKEW_SECONDS", "8")

    settings = Settings.from_env()

    assert settings.shopmind_identity_provider == "signed_header"
    assert settings.shopmind_identity_signing_secret is not None
    assert (
        settings.shopmind_identity_signing_secret.get_secret_value()
        == signing_secret
    )
    assert settings.shopmind_identity_signature_max_age_seconds == 90
    assert settings.shopmind_identity_signature_clock_skew_seconds == 8
    assert signing_secret not in repr(settings)


def test_settings_bounds_signed_identity_timing_from_environment(monkeypatch):
    monkeypatch.setattr("app.core.settings.load_dotenv", None)
    monkeypatch.setenv("SHOPMIND_IDENTITY_PROVIDER", "signed_header")
    monkeypatch.setenv(
        "SHOPMIND_IDENTITY_SIGNING_SECRET",
        "signed-identity-settings-secret-32-bytes-minimum",
    )
    monkeypatch.setenv("SHOPMIND_IDENTITY_SIGNATURE_MAX_AGE_SECONDS", "999")
    monkeypatch.setenv("SHOPMIND_IDENTITY_SIGNATURE_CLOCK_SKEW_SECONDS", "999")

    bounded = Settings.from_env()

    assert bounded.shopmind_identity_signature_max_age_seconds == (
        MAX_SHOPMIND_IDENTITY_SIGNATURE_MAX_AGE_SECONDS
    )
    assert bounded.shopmind_identity_signature_clock_skew_seconds == (
        MAX_SHOPMIND_IDENTITY_SIGNATURE_CLOCK_SKEW_SECONDS
    )

    monkeypatch.setenv("SHOPMIND_IDENTITY_SIGNATURE_MAX_AGE_SECONDS", "invalid")
    monkeypatch.setenv(
        "SHOPMIND_IDENTITY_SIGNATURE_CLOCK_SKEW_SECONDS",
        "invalid",
    )
    fallback = Settings.from_env()

    assert fallback.shopmind_identity_signature_max_age_seconds == (
        DEFAULT_SHOPMIND_IDENTITY_SIGNATURE_MAX_AGE_SECONDS
    )
    assert fallback.shopmind_identity_signature_clock_skew_seconds == (
        DEFAULT_SHOPMIND_IDENTITY_SIGNATURE_CLOCK_SKEW_SECONDS
    )


def test_settings_rejects_invalid_direct_signed_identity_timing():
    with pytest.raises(ValidationError, match="clock skew"):
        Settings(
            shopmind_identity_provider="signed_header",
            shopmind_identity_signing_secret=(
                "signed-identity-settings-secret-32-bytes-minimum"
            ),
            shopmind_identity_signature_max_age_seconds=10,
            shopmind_identity_signature_clock_skew_seconds=10,
        )


def test_settings_keeps_governance_audit_default_off_and_server_owned(monkeypatch):
    monkeypatch.delenv("SHOPMIND_GOVERNANCE_AUDIT_ENABLED", raising=False)
    monkeypatch.delenv(
        "SHOPMIND_GOVERNANCE_AUDIT_ALERT_FAILURE_THRESHOLD",
        raising=False,
    )
    monkeypatch.setattr("app.core.settings.load_dotenv", None)

    default = Settings.from_env()
    assert default.shopmind_governance_audit_enabled is (
        DEFAULT_SHOPMIND_GOVERNANCE_AUDIT_ENABLED
    )
    assert default.shopmind_governance_audit_enabled is False
    assert default.shopmind_governance_audit_alert_failure_threshold == (
        DEFAULT_SHOPMIND_GOVERNANCE_AUDIT_ALERT_FAILURE_THRESHOLD
    )

    monkeypatch.setenv("SHOPMIND_GOVERNANCE_AUDIT_ENABLED", "true")
    enabled = Settings.from_env()
    assert enabled.shopmind_governance_audit_enabled is True

    monkeypatch.setenv("SHOPMIND_GOVERNANCE_AUDIT_ENABLED", "invalid")
    fallback = Settings.from_env()
    assert fallback.shopmind_governance_audit_enabled is False

    monkeypatch.setenv(
        "SHOPMIND_GOVERNANCE_AUDIT_ALERT_FAILURE_THRESHOLD",
        "999",
    )
    bounded = Settings.from_env()
    assert bounded.shopmind_governance_audit_alert_failure_threshold == (
        MAX_SHOPMIND_GOVERNANCE_AUDIT_ALERT_FAILURE_THRESHOLD
    )

    monkeypatch.setenv(
        "SHOPMIND_GOVERNANCE_AUDIT_ALERT_FAILURE_THRESHOLD",
        "0",
    )
    threshold_fallback = Settings.from_env()
    assert threshold_fallback.shopmind_governance_audit_alert_failure_threshold == (
        DEFAULT_SHOPMIND_GOVERNANCE_AUDIT_ALERT_FAILURE_THRESHOLD
    )


def test_settings_reads_optional_runtime_budget_controls(monkeypatch):
    monkeypatch.setenv("SHOPMIND_RUNTIME_MAX_RETRIES", "2")
    monkeypatch.setenv("SHOPMIND_RUNTIME_MAX_DURATION_MS", "1500")
    monkeypatch.setenv("SHOPMIND_RUNTIME_MAX_STEPS", "6")
    monkeypatch.setenv("SHOPMIND_RUNTIME_MAX_TOOL_CALLS", "4")
    monkeypatch.setenv("SHOPMIND_RUNTIME_MAX_PROMPT_TOKENS", "512")
    monkeypatch.setenv("SHOPMIND_RUNTIME_MAX_COMPLETION_TOKENS", "256")
    monkeypatch.setenv("SHOPMIND_RUNTIME_MAX_TOTAL_TOKENS", "768")
    monkeypatch.setenv("SHOPMIND_RUNTIME_MAX_COST_USD", "0.25")

    settings = Settings.from_env()

    assert settings.shopmind_runtime_max_retries == 2
    assert settings.shopmind_runtime_max_duration_ms == 1500
    assert settings.shopmind_runtime_max_steps == 6
    assert settings.shopmind_runtime_max_tool_calls == 4
    assert settings.shopmind_runtime_max_prompt_tokens == 512
    assert settings.shopmind_runtime_max_completion_tokens == 256
    assert settings.shopmind_runtime_max_total_tokens == 768
    assert settings.shopmind_runtime_max_cost_usd == 0.25


def test_settings_bounds_agent_task_attempts_and_defaults_disabled(monkeypatch):
    monkeypatch.delenv("SHOPMIND_AGENT_TASK_MAX_ATTEMPTS", raising=False)
    monkeypatch.setattr("app.core.settings.load_dotenv", None)

    default_settings = Settings.from_env()
    assert default_settings.shopmind_agent_task_max_attempts == (
        DEFAULT_SHOPMIND_AGENT_TASK_MAX_ATTEMPTS
    )

    monkeypatch.setenv("SHOPMIND_AGENT_TASK_MAX_ATTEMPTS", "99")
    bounded_settings = Settings.from_env()
    assert bounded_settings.shopmind_agent_task_max_attempts == (
        MAX_SHOPMIND_AGENT_TASK_MAX_ATTEMPTS
    )

    monkeypatch.setenv("SHOPMIND_AGENT_TASK_MAX_ATTEMPTS", "0")
    fallback_settings = Settings.from_env()
    assert fallback_settings.shopmind_agent_task_max_attempts == (
        DEFAULT_SHOPMIND_AGENT_TASK_MAX_ATTEMPTS
    )


def test_settings_reads_bounded_parallel_read_controls(monkeypatch):
    monkeypatch.setenv("SHOPMIND_PARALLEL_READ_ENABLED", "true")
    monkeypatch.setenv("SHOPMIND_PARALLEL_READ_MAX_WORKERS", "99")

    settings = Settings.from_env()

    assert settings.shopmind_parallel_read_enabled is True
    assert settings.shopmind_parallel_read_max_workers == (
        MAX_SHOPMIND_PARALLEL_READ_WORKERS
    )

    monkeypatch.setenv("SHOPMIND_PARALLEL_READ_ENABLED", "invalid")
    monkeypatch.setenv("SHOPMIND_PARALLEL_READ_MAX_WORKERS", "0")

    fallback = Settings.from_env()

    assert fallback.shopmind_parallel_read_enabled is (
        DEFAULT_SHOPMIND_PARALLEL_READ_ENABLED
    )
    assert fallback.shopmind_parallel_read_max_workers == (
        DEFAULT_SHOPMIND_PARALLEL_READ_MAX_WORKERS
    )


def test_settings_defaults_rag_transport_to_in_process(monkeypatch):
    for name in (
        "SHOPMIND_RAG_AGENT_TRANSPORT",
        "SHOPMIND_RAG_AGENT_HTTP_ENDPOINT",
        "SHOPMIND_RAG_AGENT_HTTP_ALLOWED_HOSTS",
        "SHOPMIND_RAG_AGENT_HTTP_BEARER_TOKEN",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr("app.core.settings.load_dotenv", None)

    settings = Settings.from_env()

    assert settings.shopmind_rag_agent_transport == (
        DEFAULT_SHOPMIND_RAG_AGENT_TRANSPORT
    )
    assert settings.shopmind_rag_agent_http_endpoint is None
    assert settings.shopmind_rag_agent_http_allowed_hosts == frozenset()
    assert settings.shopmind_rag_agent_http_timeout_seconds == (
        DEFAULT_SHOPMIND_RAG_AGENT_HTTP_TIMEOUT_SECONDS
    )
    assert settings.shopmind_rag_agent_http_max_response_bytes == (
        DEFAULT_SHOPMIND_RAG_AGENT_HTTP_MAX_RESPONSE_BYTES
    )
    assert settings.shopmind_rag_agent_http_bearer_token is None


def test_settings_reads_bounded_remote_rag_configuration(monkeypatch):
    monkeypatch.setenv("SHOPMIND_RAG_AGENT_TRANSPORT", "http")
    monkeypatch.setenv(
        "SHOPMIND_RAG_AGENT_HTTP_ENDPOINT",
        "https://rag.internal.example/v1/tasks",
    )
    monkeypatch.setenv(
        "SHOPMIND_RAG_AGENT_HTTP_ALLOWED_HOSTS",
        "RAG.INTERNAL.EXAMPLE, backup.internal.example ",
    )
    monkeypatch.setenv("SHOPMIND_RAG_AGENT_HTTP_TIMEOUT_SECONDS", "99")
    monkeypatch.setenv("SHOPMIND_RAG_AGENT_HTTP_MAX_RESPONSE_BYTES", "9999999")
    monkeypatch.setenv("SHOPMIND_RAG_AGENT_HTTP_BEARER_TOKEN", "secret-value")

    settings = Settings.from_env()

    assert settings.shopmind_rag_agent_transport == "http"
    assert settings.shopmind_rag_agent_http_allowed_hosts == frozenset(
        {"rag.internal.example", "backup.internal.example"}
    )
    assert settings.shopmind_rag_agent_http_timeout_seconds == 30.0
    assert settings.shopmind_rag_agent_http_max_response_bytes == 1_048_576
    assert settings.shopmind_rag_agent_http_bearer_token.get_secret_value() == (
        "secret-value"
    )
    assert "secret-value" not in repr(settings)


def test_settings_invalid_rag_transport_does_not_enable_http(monkeypatch):
    monkeypatch.setenv("SHOPMIND_RAG_AGENT_TRANSPORT", "remote")

    settings = Settings.from_env()

    assert settings.shopmind_rag_agent_transport == "in_process"
