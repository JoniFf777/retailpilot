"""ShopMind V2 configuration helpers.

This module is intentionally additive. The legacy workshop `config.py` module
continues to power the existing V1 tools and agents while V2 infrastructure is
introduced incrementally.
"""

from functools import lru_cache
import os
from typing import Literal

from pydantic import BaseModel, Field, SecretStr, model_validator

from app.core.langsmith_policy import (
    DEFAULT_LANGSMITH_ENDPOINT,
    DEFAULT_LANGSMITH_PROJECT,
    DEFAULT_LANGSMITH_TRACING,
    DEFAULT_LANGSMITH_TRACING_SAMPLING_RATE,
    DeploymentProfile,
    initialize_langsmith_runtime,
)

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - python-dotenv is a project dependency.
    load_dotenv = None


DEFAULT_DATABASE_URL = (
    "postgresql+psycopg://retailpilot:retailpilot@127.0.0.1:5432/"
    "retailpilot?connect_timeout=5"
)
DEFAULT_TEST_DATABASE_URL = (
    "postgresql+psycopg://retailpilot:retailpilot@127.0.0.1:5432/"
    "retailpilot_test?connect_timeout=5"
)
DEFAULT_EMBEDDING_PROVIDER = "huggingface"
DEFAULT_VECTOR_DIMENSION = 768
DEFAULT_WORKSHOP_MODEL = "anthropic:claude-haiku-4-5"
DEFAULT_SHOPMIND_AGENT_MODE = "single"
DEFAULT_SHOPMIND_SUPERVISOR_ROUTER = "deterministic"
DEFAULT_SHOPMIND_AGENT_PLANNER = "deterministic"
DEFAULT_SHOPMIND_DEPLOYMENT_PROFILE = "development"
DEFAULT_SHOPMIND_DEPLOYMENT_REPLICAS = 1
MAX_SHOPMIND_DEPLOYMENT_REPLICAS = 1_000
DEFAULT_SHOPMIND_TRUSTED_PROXY_AUTHENTICATION = False
DEFAULT_SHOPMIND_RUNTIME_CLEANUP_SCHEDULED = False
DEFAULT_SHOPMIND_RUNTIME_CLEANUP_EVIDENCE_MAX_AGE_SECONDS = 90_000
MAX_SHOPMIND_RUNTIME_CLEANUP_EVIDENCE_MAX_AGE_SECONDS = 604_800
DEFAULT_SHOPMIND_SERVICE_SLO_MIN_RUNS = 20
MAX_SHOPMIND_SERVICE_SLO_MIN_RUNS = 1_000
DEFAULT_SHOPMIND_SERVICE_SLO_SUCCESS_RATE_TARGET = 0.99
DEFAULT_SHOPMIND_SERVICE_SLO_P95_LATENCY_MS = 5_000
MAX_SHOPMIND_SERVICE_SLO_P95_LATENCY_MS = 300_000
DEFAULT_SHOPMIND_STREAM_MAX_CONCURRENCY = 8
DEFAULT_SHOPMIND_STREAM_EVENT_BUFFER_SIZE = 128
DEFAULT_SHOPMIND_STREAM_ADMISSION_LEASE_TTL_MS = 30_000
DEFAULT_SHOPMIND_STREAM_ADMISSION_RENEW_INTERVAL_MS = 10_000
MAX_SHOPMIND_STREAM_ADMISSION_LEASE_TTL_MS = 300_000
DEFAULT_SHOPMIND_COORDINATION_BACKEND = "local"
DEFAULT_SHOPMIND_IDENTITY_PROVIDER = "development_payload"
DEFAULT_SHOPMIND_CHECKOUT_TOKEN_TTL_SECONDS = 900
MAX_SHOPMIND_CHECKOUT_TOKEN_TTL_SECONDS = 3_600
DEFAULT_SHOPMIND_IDENTITY_SIGNATURE_MAX_AGE_SECONDS = 60
MAX_SHOPMIND_IDENTITY_SIGNATURE_MAX_AGE_SECONDS = 300
DEFAULT_SHOPMIND_IDENTITY_SIGNATURE_CLOCK_SKEW_SECONDS = 5
MAX_SHOPMIND_IDENTITY_SIGNATURE_CLOCK_SKEW_SECONDS = 30
DEFAULT_SHOPMIND_GOVERNANCE_AUDIT_ENABLED = False
DEFAULT_SHOPMIND_GOVERNANCE_AUDIT_ALERT_FAILURE_THRESHOLD = 3
MAX_SHOPMIND_GOVERNANCE_AUDIT_ALERT_FAILURE_THRESHOLD = 100
DEFAULT_SHOPMIND_RUNTIME_MAX_RETRIES = 0
DEFAULT_SHOPMIND_AGENT_TASK_MAX_ATTEMPTS = 1
MAX_SHOPMIND_AGENT_TASK_MAX_ATTEMPTS = 3
DEFAULT_SHOPMIND_RAG_AGENT_TRANSPORT = "in_process"
DEFAULT_SHOPMIND_RAG_AGENT_HTTP_TIMEOUT_SECONDS = 10.0
DEFAULT_SHOPMIND_RAG_AGENT_HTTP_MAX_RESPONSE_BYTES = 1_048_576
DEFAULT_SHOPMIND_PARALLEL_READ_ENABLED = False
DEFAULT_SHOPMIND_PARALLEL_READ_MAX_WORKERS = 2
MAX_SHOPMIND_PARALLEL_READ_WORKERS = 3
DEFAULT_SHOPMIND_OUTBOX_ENABLED = False
DEFAULT_SHOPMIND_OUTBOX_TOPIC = "shopmind-order-events-v1"
DEFAULT_SHOPMIND_OUTBOX_LEASE_SECONDS = 60
DEFAULT_SHOPMIND_OUTBOX_BATCH_SIZE = 10
DEFAULT_SHOPMIND_OUTBOX_POLL_INTERVAL_SECONDS = 1.0
DEFAULT_SHOPMIND_OUTBOX_BASE_BACKOFF_SECONDS = 5
DEFAULT_SHOPMIND_OUTBOX_MAX_BACKOFF_SECONDS = 15 * 60
DEFAULT_SHOPMIND_OUTBOX_MAX_ATTEMPTS = 12


def _load_dotenv() -> None:
    if load_dotenv is not None:
        load_dotenv(override=False)


def _get_bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default

    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _get_int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default

    try:
        return int(value)
    except ValueError:
        return default


def _get_positive_int_env(name: str, default: int) -> int:
    value = _get_int_env(name, default)
    return value if value > 0 else default


def _get_optional_positive_int_env(name: str) -> int | None:
    value = _get_int_env(name, 0)
    return value if value > 0 else None


def _get_optional_positive_float_env(name: str) -> float | None:
    raw_value = os.getenv(name)
    if raw_value is None:
        return None
    try:
        value = float(raw_value)
    except ValueError:
        return None
    return value if value > 0 else None


def _get_bounded_positive_int_env(name: str, default: int, maximum: int) -> int:
    return min(_get_positive_int_env(name, default), maximum)


def _get_bounded_positive_float_env(
    name: str,
    default: float,
    maximum: float,
) -> float:
    value = _get_optional_positive_float_env(name)
    return min(value, maximum) if value is not None else default


def _get_stream_admission_timing() -> tuple[int, int]:
    lease_ttl_ms = _get_bounded_positive_int_env(
        "SHOPMIND_STREAM_ADMISSION_LEASE_TTL_MS",
        DEFAULT_SHOPMIND_STREAM_ADMISSION_LEASE_TTL_MS,
        MAX_SHOPMIND_STREAM_ADMISSION_LEASE_TTL_MS,
    )
    renew_interval_ms = _get_positive_int_env(
        "SHOPMIND_STREAM_ADMISSION_RENEW_INTERVAL_MS",
        DEFAULT_SHOPMIND_STREAM_ADMISSION_RENEW_INTERVAL_MS,
    )
    if renew_interval_ms >= lease_ttl_ms:
        renew_interval_ms = max(1, lease_ttl_ms // 3)
    return lease_ttl_ms, renew_interval_ms


def _get_identity_signature_timing() -> tuple[int, int]:
    max_age_seconds = _get_bounded_positive_int_env(
        "SHOPMIND_IDENTITY_SIGNATURE_MAX_AGE_SECONDS",
        DEFAULT_SHOPMIND_IDENTITY_SIGNATURE_MAX_AGE_SECONDS,
        MAX_SHOPMIND_IDENTITY_SIGNATURE_MAX_AGE_SECONDS,
    )
    clock_skew_seconds = min(
        max(
            0,
            _get_int_env(
                "SHOPMIND_IDENTITY_SIGNATURE_CLOCK_SKEW_SECONDS",
                DEFAULT_SHOPMIND_IDENTITY_SIGNATURE_CLOCK_SKEW_SECONDS,
            ),
        ),
        MAX_SHOPMIND_IDENTITY_SIGNATURE_CLOCK_SKEW_SECONDS,
    )
    if clock_skew_seconds >= max_age_seconds:
        clock_skew_seconds = max(0, max_age_seconds - 1)
    return max_age_seconds, clock_skew_seconds


def _get_host_set_env(name: str) -> frozenset[str]:
    raw_value = os.getenv(name, "")
    return frozenset(
        host.strip().lower()
        for host in raw_value.split(",")
        if host.strip()
    )


class Settings(BaseModel):
    """Runtime settings for the V2 infrastructure layer."""

    database_url: str = Field(default=DEFAULT_DATABASE_URL)
    test_database_url: str = Field(default=DEFAULT_TEST_DATABASE_URL)
    embedding_provider: str = Field(default=DEFAULT_EMBEDDING_PROVIDER)
    vector_dimension: int = Field(default=DEFAULT_VECTOR_DIMENSION)
    langsmith_api_key: SecretStr | None = Field(default=None, repr=False)
    langsmith_tracing: bool = Field(default=DEFAULT_LANGSMITH_TRACING)
    langsmith_project: str = Field(default=DEFAULT_LANGSMITH_PROJECT)
    langsmith_endpoint: str = Field(default=DEFAULT_LANGSMITH_ENDPOINT)
    langsmith_tracing_sampling_rate: float = Field(
        default=DEFAULT_LANGSMITH_TRACING_SAMPLING_RATE,
        gt=0,
        le=1,
    )
    workshop_model: str = Field(default=DEFAULT_WORKSHOP_MODEL)
    shopmind_agent_mode: str = Field(default=DEFAULT_SHOPMIND_AGENT_MODE)
    shopmind_supervisor_router: str = Field(default=DEFAULT_SHOPMIND_SUPERVISOR_ROUTER)
    shopmind_agent_planner: str = Field(default=DEFAULT_SHOPMIND_AGENT_PLANNER)
    shopmind_deployment_profile: DeploymentProfile = Field(
        default=DEFAULT_SHOPMIND_DEPLOYMENT_PROFILE
    )
    shopmind_deployment_replicas: int = Field(
        default=DEFAULT_SHOPMIND_DEPLOYMENT_REPLICAS,
        ge=1,
        le=MAX_SHOPMIND_DEPLOYMENT_REPLICAS,
    )
    shopmind_trusted_proxy_authentication: bool = Field(
        default=DEFAULT_SHOPMIND_TRUSTED_PROXY_AUTHENTICATION
    )
    shopmind_runtime_cleanup_scheduled: bool = Field(
        default=DEFAULT_SHOPMIND_RUNTIME_CLEANUP_SCHEDULED
    )
    shopmind_runtime_cleanup_evidence_path: str | None = Field(default=None)
    shopmind_runtime_cleanup_evidence_max_age_seconds: int = Field(
        default=DEFAULT_SHOPMIND_RUNTIME_CLEANUP_EVIDENCE_MAX_AGE_SECONDS,
        ge=1,
        le=MAX_SHOPMIND_RUNTIME_CLEANUP_EVIDENCE_MAX_AGE_SECONDS,
    )
    shopmind_service_slo_min_runs: int = Field(
        default=DEFAULT_SHOPMIND_SERVICE_SLO_MIN_RUNS,
        ge=1,
        le=MAX_SHOPMIND_SERVICE_SLO_MIN_RUNS,
    )
    shopmind_service_slo_success_rate_target: float = Field(
        default=DEFAULT_SHOPMIND_SERVICE_SLO_SUCCESS_RATE_TARGET,
        gt=0,
        le=1,
    )
    shopmind_service_slo_p95_latency_ms: int = Field(
        default=DEFAULT_SHOPMIND_SERVICE_SLO_P95_LATENCY_MS,
        ge=1,
        le=MAX_SHOPMIND_SERVICE_SLO_P95_LATENCY_MS,
    )
    shopmind_stream_max_concurrency: int = Field(
        default=DEFAULT_SHOPMIND_STREAM_MAX_CONCURRENCY
    )
    shopmind_stream_event_buffer_size: int = Field(
        default=DEFAULT_SHOPMIND_STREAM_EVENT_BUFFER_SIZE
    )
    shopmind_stream_admission_lease_ttl_ms: int = Field(
        default=DEFAULT_SHOPMIND_STREAM_ADMISSION_LEASE_TTL_MS,
        ge=1,
        le=MAX_SHOPMIND_STREAM_ADMISSION_LEASE_TTL_MS,
    )
    shopmind_stream_admission_renew_interval_ms: int = Field(
        default=DEFAULT_SHOPMIND_STREAM_ADMISSION_RENEW_INTERVAL_MS,
        ge=1,
    )
    shopmind_coordination_backend: Literal["local", "redis"] = Field(
        default=DEFAULT_SHOPMIND_COORDINATION_BACKEND
    )
    shopmind_coordination_redis_url: SecretStr | None = Field(default=None)
    shopmind_identity_provider: Literal[
        "development_payload",
        "trusted_header",
        "signed_header",
    ] = Field(default=DEFAULT_SHOPMIND_IDENTITY_PROVIDER)
    shopmind_identity_signing_secret: SecretStr | None = Field(default=None)
    shopmind_checkout_signing_secret: SecretStr | None = Field(default=None)
    shopmind_checkout_token_ttl_seconds: int = Field(
        default=DEFAULT_SHOPMIND_CHECKOUT_TOKEN_TTL_SECONDS,
        ge=1,
        le=MAX_SHOPMIND_CHECKOUT_TOKEN_TTL_SECONDS,
    )
    shopmind_identity_signature_max_age_seconds: int = Field(
        default=DEFAULT_SHOPMIND_IDENTITY_SIGNATURE_MAX_AGE_SECONDS,
        ge=1,
        le=MAX_SHOPMIND_IDENTITY_SIGNATURE_MAX_AGE_SECONDS,
    )
    shopmind_identity_signature_clock_skew_seconds: int = Field(
        default=DEFAULT_SHOPMIND_IDENTITY_SIGNATURE_CLOCK_SKEW_SECONDS,
        ge=0,
        le=MAX_SHOPMIND_IDENTITY_SIGNATURE_CLOCK_SKEW_SECONDS,
    )
    shopmind_governance_audit_enabled: bool = Field(
        default=DEFAULT_SHOPMIND_GOVERNANCE_AUDIT_ENABLED
    )
    shopmind_governance_audit_alert_failure_threshold: int = Field(
        default=DEFAULT_SHOPMIND_GOVERNANCE_AUDIT_ALERT_FAILURE_THRESHOLD,
        ge=1,
        le=MAX_SHOPMIND_GOVERNANCE_AUDIT_ALERT_FAILURE_THRESHOLD,
    )
    shopmind_runtime_max_retries: int = Field(default=DEFAULT_SHOPMIND_RUNTIME_MAX_RETRIES)
    shopmind_agent_task_max_attempts: int = Field(
        default=DEFAULT_SHOPMIND_AGENT_TASK_MAX_ATTEMPTS,
        ge=1,
        le=MAX_SHOPMIND_AGENT_TASK_MAX_ATTEMPTS,
    )
    shopmind_rag_agent_transport: Literal["in_process", "http"] = Field(
        default=DEFAULT_SHOPMIND_RAG_AGENT_TRANSPORT
    )
    shopmind_rag_agent_http_endpoint: str | None = Field(default=None)
    shopmind_rag_agent_http_allowed_hosts: frozenset[str] = Field(
        default_factory=frozenset
    )
    shopmind_rag_agent_http_timeout_seconds: float = Field(
        default=DEFAULT_SHOPMIND_RAG_AGENT_HTTP_TIMEOUT_SECONDS,
        gt=0,
        le=30,
    )
    shopmind_rag_agent_http_max_response_bytes: int = Field(
        default=DEFAULT_SHOPMIND_RAG_AGENT_HTTP_MAX_RESPONSE_BYTES,
        ge=1,
        le=DEFAULT_SHOPMIND_RAG_AGENT_HTTP_MAX_RESPONSE_BYTES,
    )
    shopmind_rag_agent_http_bearer_token: SecretStr | None = Field(default=None)
    shopmind_runtime_max_duration_ms: int | None = Field(default=None)
    shopmind_runtime_max_steps: int | None = Field(default=None)
    shopmind_runtime_max_tool_calls: int | None = Field(default=None)
    shopmind_runtime_max_prompt_tokens: int | None = Field(default=None)
    shopmind_runtime_max_completion_tokens: int | None = Field(default=None)
    shopmind_runtime_max_total_tokens: int | None = Field(default=None)
    shopmind_runtime_max_cost_usd: float | None = Field(default=None)
    shopmind_parallel_read_enabled: bool = Field(
        default=DEFAULT_SHOPMIND_PARALLEL_READ_ENABLED
    )
    shopmind_parallel_read_max_workers: int = Field(
        default=DEFAULT_SHOPMIND_PARALLEL_READ_MAX_WORKERS,
        ge=1,
        le=MAX_SHOPMIND_PARALLEL_READ_WORKERS,
    )
    shopmind_outbox_enabled: bool = Field(default=DEFAULT_SHOPMIND_OUTBOX_ENABLED)
    shopmind_outbox_rocketmq_endpoint: str | None = Field(default=None)
    shopmind_outbox_rocketmq_topic: str = Field(default=DEFAULT_SHOPMIND_OUTBOX_TOPIC)
    shopmind_outbox_rocketmq_access_key: SecretStr | None = Field(default=None, repr=False)
    shopmind_outbox_rocketmq_secret_key: SecretStr | None = Field(default=None, repr=False)
    shopmind_outbox_lease_seconds: int = Field(
        default=DEFAULT_SHOPMIND_OUTBOX_LEASE_SECONDS, ge=1, le=3_600
    )
    shopmind_outbox_batch_size: int = Field(default=DEFAULT_SHOPMIND_OUTBOX_BATCH_SIZE, ge=1, le=100)
    shopmind_outbox_poll_interval_seconds: float = Field(
        default=DEFAULT_SHOPMIND_OUTBOX_POLL_INTERVAL_SECONDS, gt=0, le=60
    )
    shopmind_outbox_base_backoff_seconds: int = Field(
        default=DEFAULT_SHOPMIND_OUTBOX_BASE_BACKOFF_SECONDS, ge=1, le=900
    )
    shopmind_outbox_max_backoff_seconds: int = Field(
        default=DEFAULT_SHOPMIND_OUTBOX_MAX_BACKOFF_SECONDS, ge=1, le=86_400
    )
    shopmind_outbox_max_attempts: int = Field(
        default=DEFAULT_SHOPMIND_OUTBOX_MAX_ATTEMPTS, ge=1, le=100
    )

    @model_validator(mode="after")
    def validate_coordination_settings(self) -> "Settings":
        if (
            self.shopmind_stream_admission_renew_interval_ms
            >= self.shopmind_stream_admission_lease_ttl_ms
        ):
            raise ValueError(
                "Stream admission renewal interval must be shorter than its lease TTL."
            )
        if self.shopmind_identity_provider == "signed_header":
            if self.shopmind_identity_signing_secret is None:
                raise ValueError(
                    "Signed-header identity requires a server-owned signing secret."
                )
            if (
                len(
                    self.shopmind_identity_signing_secret.get_secret_value()
                )
                < 32
            ):
                raise ValueError(
                    "Signed-header identity signing secret is too short."
                )
            if (
                self.shopmind_identity_signature_clock_skew_seconds
                >= self.shopmind_identity_signature_max_age_seconds
            ):
                raise ValueError(
                    "Signed-header clock skew must be shorter than max age."
                )
        if (
            self.shopmind_checkout_signing_secret is not None
            and len(self.shopmind_checkout_signing_secret.get_secret_value()) < 32
        ):
            raise ValueError("Checkout signing secret is too short.")
        if self.shopmind_outbox_max_backoff_seconds < self.shopmind_outbox_base_backoff_seconds:
            raise ValueError("Outbox maximum backoff must be at least its base backoff.")
        return self

    @classmethod
    def from_env(cls) -> "Settings":
        """Build settings from environment variables and an optional `.env` file."""
        langsmith_runtime = initialize_langsmith_runtime(
            load_environment=True,
            dotenv_loader=load_dotenv,
        )
        lease_ttl_ms, renew_interval_ms = _get_stream_admission_timing()
        identity_max_age_seconds, identity_clock_skew_seconds = (
            _get_identity_signature_timing()
        )
        coordination_backend = (
            os.getenv(
                "SHOPMIND_COORDINATION_BACKEND",
                DEFAULT_SHOPMIND_COORDINATION_BACKEND,
            )
            .strip()
            .lower()
        )
        identity_provider = (
            os.getenv(
                "SHOPMIND_IDENTITY_PROVIDER",
                DEFAULT_SHOPMIND_IDENTITY_PROVIDER,
            )
            .strip()
            .lower()
        )
        return cls(
            database_url=os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL),
            test_database_url=os.getenv("TEST_DATABASE_URL", DEFAULT_TEST_DATABASE_URL),
            embedding_provider=os.getenv(
                "EMBEDDING_PROVIDER", DEFAULT_EMBEDDING_PROVIDER
            ),
            vector_dimension=_get_int_env("VECTOR_DIMENSION", DEFAULT_VECTOR_DIMENSION),
            langsmith_api_key=(
                SecretStr(os.getenv("LANGSMITH_API_KEY", "").strip())
                if os.getenv("LANGSMITH_API_KEY", "").strip()
                else None
            ),
            langsmith_tracing=langsmith_runtime.tracing_enabled,
            langsmith_project=langsmith_runtime.project,
            langsmith_endpoint=langsmith_runtime.endpoint,
            langsmith_tracing_sampling_rate=langsmith_runtime.sampling_rate,
            workshop_model=os.getenv("WORKSHOP_MODEL", DEFAULT_WORKSHOP_MODEL),
            shopmind_agent_mode=(
                "multi"
                if os.getenv("SHOPMIND_AGENT_MODE", DEFAULT_SHOPMIND_AGENT_MODE)
                .strip()
                .lower()
                == "multi"
                else DEFAULT_SHOPMIND_AGENT_MODE
            ),
            shopmind_supervisor_router=(
                "llm"
                if os.getenv(
                    "SHOPMIND_SUPERVISOR_ROUTER",
                    DEFAULT_SHOPMIND_SUPERVISOR_ROUTER,
                )
                .strip()
                .lower()
                == "llm"
                else DEFAULT_SHOPMIND_SUPERVISOR_ROUTER
            ),
            shopmind_agent_planner=(
                "llm"
                if os.getenv(
                    "SHOPMIND_AGENT_PLANNER",
                    DEFAULT_SHOPMIND_AGENT_PLANNER,
                )
                .strip()
                .lower()
                == "llm"
                else DEFAULT_SHOPMIND_AGENT_PLANNER
            ),
            shopmind_deployment_profile=langsmith_runtime.profile,
            shopmind_deployment_replicas=_get_bounded_positive_int_env(
                "SHOPMIND_DEPLOYMENT_REPLICAS",
                DEFAULT_SHOPMIND_DEPLOYMENT_REPLICAS,
                MAX_SHOPMIND_DEPLOYMENT_REPLICAS,
            ),
            shopmind_trusted_proxy_authentication=_get_bool_env(
                "SHOPMIND_TRUSTED_PROXY_AUTHENTICATION",
                DEFAULT_SHOPMIND_TRUSTED_PROXY_AUTHENTICATION,
            ),
            shopmind_runtime_cleanup_scheduled=_get_bool_env(
                "SHOPMIND_RUNTIME_CLEANUP_SCHEDULED",
                DEFAULT_SHOPMIND_RUNTIME_CLEANUP_SCHEDULED,
            ),
            shopmind_runtime_cleanup_evidence_path=(
                (
                    os.getenv("SHOPMIND_RUNTIME_CLEANUP_EVIDENCE_PATH") or ""
                ).strip()
                or None
            ),
            shopmind_runtime_cleanup_evidence_max_age_seconds=(
                _get_bounded_positive_int_env(
                    "SHOPMIND_RUNTIME_CLEANUP_EVIDENCE_MAX_AGE_SECONDS",
                    DEFAULT_SHOPMIND_RUNTIME_CLEANUP_EVIDENCE_MAX_AGE_SECONDS,
                    MAX_SHOPMIND_RUNTIME_CLEANUP_EVIDENCE_MAX_AGE_SECONDS,
                )
            ),
            shopmind_service_slo_min_runs=_get_bounded_positive_int_env(
                "SHOPMIND_SERVICE_SLO_MIN_RUNS",
                DEFAULT_SHOPMIND_SERVICE_SLO_MIN_RUNS,
                MAX_SHOPMIND_SERVICE_SLO_MIN_RUNS,
            ),
            shopmind_service_slo_success_rate_target=(
                _get_bounded_positive_float_env(
                    "SHOPMIND_SERVICE_SLO_SUCCESS_RATE_TARGET",
                    DEFAULT_SHOPMIND_SERVICE_SLO_SUCCESS_RATE_TARGET,
                    1.0,
                )
            ),
            shopmind_service_slo_p95_latency_ms=(
                _get_bounded_positive_int_env(
                    "SHOPMIND_SERVICE_SLO_P95_LATENCY_MS",
                    DEFAULT_SHOPMIND_SERVICE_SLO_P95_LATENCY_MS,
                    MAX_SHOPMIND_SERVICE_SLO_P95_LATENCY_MS,
                )
            ),
            shopmind_stream_max_concurrency=_get_positive_int_env(
                "SHOPMIND_STREAM_MAX_CONCURRENCY",
                DEFAULT_SHOPMIND_STREAM_MAX_CONCURRENCY,
            ),
            shopmind_stream_event_buffer_size=_get_positive_int_env(
                "SHOPMIND_STREAM_EVENT_BUFFER_SIZE",
                DEFAULT_SHOPMIND_STREAM_EVENT_BUFFER_SIZE,
            ),
            shopmind_stream_admission_lease_ttl_ms=lease_ttl_ms,
            shopmind_stream_admission_renew_interval_ms=renew_interval_ms,
            shopmind_coordination_backend=(
                "redis"
                if coordination_backend == "redis"
                else DEFAULT_SHOPMIND_COORDINATION_BACKEND
            ),
            shopmind_coordination_redis_url=(
                os.getenv("SHOPMIND_COORDINATION_REDIS_URL") or None
            ),
            shopmind_identity_provider=(
                identity_provider
                if identity_provider in {"trusted_header", "signed_header"}
                else DEFAULT_SHOPMIND_IDENTITY_PROVIDER
            ),
            shopmind_identity_signing_secret=(
                os.getenv("SHOPMIND_IDENTITY_SIGNING_SECRET") or None
            ),
            shopmind_checkout_signing_secret=(
                os.getenv("SHOPMIND_CHECKOUT_SIGNING_SECRET") or None
            ),
            shopmind_checkout_token_ttl_seconds=_get_bounded_positive_int_env(
                "SHOPMIND_CHECKOUT_TOKEN_TTL_SECONDS",
                DEFAULT_SHOPMIND_CHECKOUT_TOKEN_TTL_SECONDS,
                MAX_SHOPMIND_CHECKOUT_TOKEN_TTL_SECONDS,
            ),
            shopmind_identity_signature_max_age_seconds=identity_max_age_seconds,
            shopmind_identity_signature_clock_skew_seconds=(
                identity_clock_skew_seconds
            ),
            shopmind_governance_audit_enabled=_get_bool_env(
                "SHOPMIND_GOVERNANCE_AUDIT_ENABLED",
                DEFAULT_SHOPMIND_GOVERNANCE_AUDIT_ENABLED,
            ),
            shopmind_governance_audit_alert_failure_threshold=(
                _get_bounded_positive_int_env(
                    "SHOPMIND_GOVERNANCE_AUDIT_ALERT_FAILURE_THRESHOLD",
                    DEFAULT_SHOPMIND_GOVERNANCE_AUDIT_ALERT_FAILURE_THRESHOLD,
                    MAX_SHOPMIND_GOVERNANCE_AUDIT_ALERT_FAILURE_THRESHOLD,
                )
            ),
            shopmind_runtime_max_retries=max(
                0,
                _get_int_env(
                    "SHOPMIND_RUNTIME_MAX_RETRIES",
                    DEFAULT_SHOPMIND_RUNTIME_MAX_RETRIES,
                ),
            ),
            shopmind_agent_task_max_attempts=_get_bounded_positive_int_env(
                "SHOPMIND_AGENT_TASK_MAX_ATTEMPTS",
                DEFAULT_SHOPMIND_AGENT_TASK_MAX_ATTEMPTS,
                MAX_SHOPMIND_AGENT_TASK_MAX_ATTEMPTS,
            ),
            shopmind_rag_agent_transport=(
                "http"
                if os.getenv(
                    "SHOPMIND_RAG_AGENT_TRANSPORT",
                    DEFAULT_SHOPMIND_RAG_AGENT_TRANSPORT,
                ).strip().lower()
                == "http"
                else DEFAULT_SHOPMIND_RAG_AGENT_TRANSPORT
            ),
            shopmind_rag_agent_http_endpoint=(
                os.getenv("SHOPMIND_RAG_AGENT_HTTP_ENDPOINT") or None
            ),
            shopmind_rag_agent_http_allowed_hosts=_get_host_set_env(
                "SHOPMIND_RAG_AGENT_HTTP_ALLOWED_HOSTS"
            ),
            shopmind_rag_agent_http_timeout_seconds=(
                _get_bounded_positive_float_env(
                    "SHOPMIND_RAG_AGENT_HTTP_TIMEOUT_SECONDS",
                    DEFAULT_SHOPMIND_RAG_AGENT_HTTP_TIMEOUT_SECONDS,
                    30.0,
                )
            ),
            shopmind_rag_agent_http_max_response_bytes=(
                _get_bounded_positive_int_env(
                    "SHOPMIND_RAG_AGENT_HTTP_MAX_RESPONSE_BYTES",
                    DEFAULT_SHOPMIND_RAG_AGENT_HTTP_MAX_RESPONSE_BYTES,
                    DEFAULT_SHOPMIND_RAG_AGENT_HTTP_MAX_RESPONSE_BYTES,
                )
            ),
            shopmind_rag_agent_http_bearer_token=(
                os.getenv("SHOPMIND_RAG_AGENT_HTTP_BEARER_TOKEN") or None
            ),
            shopmind_runtime_max_duration_ms=_get_optional_positive_int_env(
                "SHOPMIND_RUNTIME_MAX_DURATION_MS"
            ),
            shopmind_runtime_max_steps=_get_optional_positive_int_env(
                "SHOPMIND_RUNTIME_MAX_STEPS"
            ),
            shopmind_runtime_max_tool_calls=_get_optional_positive_int_env(
                "SHOPMIND_RUNTIME_MAX_TOOL_CALLS"
            ),
            shopmind_runtime_max_prompt_tokens=_get_optional_positive_int_env(
                "SHOPMIND_RUNTIME_MAX_PROMPT_TOKENS"
            ),
            shopmind_runtime_max_completion_tokens=_get_optional_positive_int_env(
                "SHOPMIND_RUNTIME_MAX_COMPLETION_TOKENS"
            ),
            shopmind_runtime_max_total_tokens=_get_optional_positive_int_env(
                "SHOPMIND_RUNTIME_MAX_TOTAL_TOKENS"
            ),
            shopmind_runtime_max_cost_usd=_get_optional_positive_float_env(
                "SHOPMIND_RUNTIME_MAX_COST_USD"
            ),
            shopmind_parallel_read_enabled=_get_bool_env(
                "SHOPMIND_PARALLEL_READ_ENABLED",
                DEFAULT_SHOPMIND_PARALLEL_READ_ENABLED,
            ),
            shopmind_parallel_read_max_workers=_get_bounded_positive_int_env(
                "SHOPMIND_PARALLEL_READ_MAX_WORKERS",
                DEFAULT_SHOPMIND_PARALLEL_READ_MAX_WORKERS,
                MAX_SHOPMIND_PARALLEL_READ_WORKERS,
            ),
            shopmind_outbox_enabled=_get_bool_env(
                "SHOPMIND_OUTBOX_ENABLED", DEFAULT_SHOPMIND_OUTBOX_ENABLED
            ),
            shopmind_outbox_rocketmq_endpoint=(
                os.getenv("SHOPMIND_OUTBOX_ROCKETMQ_ENDPOINT") or None
            ),
            shopmind_outbox_rocketmq_topic=os.getenv(
                "SHOPMIND_OUTBOX_ROCKETMQ_TOPIC", DEFAULT_SHOPMIND_OUTBOX_TOPIC
            ),
            shopmind_outbox_rocketmq_access_key=(
                SecretStr(os.getenv("SHOPMIND_OUTBOX_ROCKETMQ_ACCESS_KEY"))
                if os.getenv("SHOPMIND_OUTBOX_ROCKETMQ_ACCESS_KEY")
                else None
            ),
            shopmind_outbox_rocketmq_secret_key=(
                SecretStr(os.getenv("SHOPMIND_OUTBOX_ROCKETMQ_SECRET_KEY"))
                if os.getenv("SHOPMIND_OUTBOX_ROCKETMQ_SECRET_KEY")
                else None
            ),
            shopmind_outbox_lease_seconds=_get_bounded_positive_int_env(
                "SHOPMIND_OUTBOX_LEASE_SECONDS",
                DEFAULT_SHOPMIND_OUTBOX_LEASE_SECONDS,
                3_600,
            ),
            shopmind_outbox_batch_size=_get_bounded_positive_int_env(
                "SHOPMIND_OUTBOX_BATCH_SIZE", DEFAULT_SHOPMIND_OUTBOX_BATCH_SIZE, 100
            ),
            shopmind_outbox_poll_interval_seconds=_get_bounded_positive_float_env(
                "SHOPMIND_OUTBOX_POLL_INTERVAL_SECONDS",
                DEFAULT_SHOPMIND_OUTBOX_POLL_INTERVAL_SECONDS,
                60.0,
            ),
            shopmind_outbox_base_backoff_seconds=_get_bounded_positive_int_env(
                "SHOPMIND_OUTBOX_BASE_BACKOFF_SECONDS",
                DEFAULT_SHOPMIND_OUTBOX_BASE_BACKOFF_SECONDS,
                900,
            ),
            shopmind_outbox_max_backoff_seconds=_get_bounded_positive_int_env(
                "SHOPMIND_OUTBOX_MAX_BACKOFF_SECONDS",
                DEFAULT_SHOPMIND_OUTBOX_MAX_BACKOFF_SECONDS,
                86_400,
            ),
            shopmind_outbox_max_attempts=_get_bounded_positive_int_env(
                "SHOPMIND_OUTBOX_MAX_ATTEMPTS", DEFAULT_SHOPMIND_OUTBOX_MAX_ATTEMPTS, 100
            ),
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached V2 settings for application code."""
    return Settings.from_env()
