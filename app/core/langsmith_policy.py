"""Fail-closed, process-wide LangSmith runtime configuration.

This module deliberately does not import the LangSmith SDK.  It resolves the
profile and local environment first, then updates the environment variables
that LangChain/LangGraph read at runtime.  Callers should invoke
``initialize_langsmith_runtime`` before constructing models, agents, graphs or
tracers.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
import os
from typing import Literal

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - python-dotenv is a project dependency.
    load_dotenv = None


LOGGER = logging.getLogger(__name__)
_DEFAULT_DOTENV_LOADER = object()

DeploymentProfile = Literal[
    "development", "offline-demo", "demo", "production", "evaluation"
]

DEFAULT_LANGSMITH_TRACING = False
DEFAULT_LANGSMITH_PROJECT = "shopmind-development"
DEFAULT_LANGSMITH_ENDPOINT = "https://api.smith.langchain.com"
DEFAULT_LANGSMITH_TRACING_SAMPLING_RATE = 1.0

_PROFILE_DEFAULTS: dict[DeploymentProfile, tuple[bool, str, float]] = {
    "development": (False, "shopmind-development", 1.0),
    "offline-demo": (False, "shopmind-offline-demo", 1.0),
    "demo": (True, "shopmind-demo", 1.0),
    "production": (True, "shopmind-production", 0.1),
    "evaluation": (True, "shopmind-evaluation", 1.0),
}


@dataclass(frozen=True)
class LangSmithRuntime:
    """Sanitized effective LangSmith state; never carries the API key."""

    profile: DeploymentProfile
    tracing_enabled: bool
    project: str
    endpoint: str
    sampling_rate: float


def _profile_from_environment(value: str | None) -> DeploymentProfile:
    normalized = (value or "development").strip().lower()
    if normalized == "public-demo":
        return "production"
    if normalized in _PROFILE_DEFAULTS:
        return normalized  # type: ignore[return-value]
    return "development"


def _parse_bool(value: str | None) -> tuple[bool, bool]:
    if value is None:
        return False, True
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True, True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False, True
    return False, False


def _parse_sampling_rate(value: str | None, default: float) -> tuple[float, bool]:
    if value is None:
        return default, True
    try:
        parsed = float(value.strip())
    except (AttributeError, TypeError, ValueError):
        return default, False
    if not 0.0 < parsed <= 1.0:
        return default, False
    return parsed, True


def _set_sdk_tracing(enabled: bool) -> None:
    value = "true" if enabled else "false"
    # LANGCHAIN_TRACING_V2 is retained as a defensive compatibility gate for
    # older LangChain integrations.  No SDK import is needed to set either.
    os.environ["LANGSMITH_TRACING"] = value
    os.environ["LANGCHAIN_TRACING_V2"] = value


def initialize_langsmith_runtime(
    *,
    load_environment: bool = True,
    dotenv_loader: object = _DEFAULT_DOTENV_LOADER,
) -> LangSmithRuntime:
    """Resolve policy and set SDK-visible tracing state before model creation.

    Process variables present before dotenv loading are explicit overrides.
    Profile defaults fill only missing values.  Every error path starts and
    ends with both SDK tracing switches set to ``false``.
    """

    names = (
        "SHOPMIND_DEPLOYMENT_PROFILE",
        "LANGSMITH_TRACING",
        "LANGSMITH_PROJECT",
        "LANGSMITH_ENDPOINT",
        "LANGSMITH_TRACING_SAMPLING_RATE",
    )
    explicit = {name: os.environ.get(name) for name in names if name in os.environ}
    _set_sdk_tracing(False)

    try:
        selected_loader = (
            load_dotenv
            if dotenv_loader is _DEFAULT_DOTENV_LOADER
            else dotenv_loader
        )
        if load_environment and callable(selected_loader):
            selected_loader(override=False)

        profile = _profile_from_environment(
            explicit.get("SHOPMIND_DEPLOYMENT_PROFILE")
            or os.getenv("SHOPMIND_DEPLOYMENT_PROFILE")
        )
        profile_tracing, profile_project, profile_sampling = _PROFILE_DEFAULTS[
            profile
        ]

        requested_tracing, tracing_valid = _parse_bool(
            explicit.get("LANGSMITH_TRACING")
            if "LANGSMITH_TRACING" in explicit
            else None
        )
        if "LANGSMITH_TRACING" not in explicit:
            dotenv_tracing = os.getenv("LANGSMITH_TRACING")
            if dotenv_tracing is None:
                requested_tracing = profile_tracing
            else:
                # A dotenv value is not an explicit process override.  The
                # profile default protects local development from stale .env,
                # but malformed values still fail closed.
                _, tracing_valid = _parse_bool(dotenv_tracing)
                requested_tracing = profile_tracing

        # The offline demo is deliberately self-contained.  A stale local
        # dotenv/process value must not turn LangSmith into a core dependency.
        if profile == "offline-demo":
            requested_tracing = False
            tracing_valid = True

        project = explicit.get("LANGSMITH_PROJECT") or profile_project
        endpoint = explicit.get("LANGSMITH_ENDPOINT") or DEFAULT_LANGSMITH_ENDPOINT
        sampling_raw = explicit.get("LANGSMITH_TRACING_SAMPLING_RATE")
        if sampling_raw is None:
            dotenv_sampling = os.getenv("LANGSMITH_TRACING_SAMPLING_RATE")
            _, sampling_valid = _parse_sampling_rate(
                dotenv_sampling, profile_sampling
            )
            sampling = profile_sampling
        else:
            sampling, sampling_valid = _parse_sampling_rate(
                sampling_raw, profile_sampling
            )
        api_key_present = bool(os.getenv("LANGSMITH_API_KEY", "").strip())

        tracing_enabled = (
            requested_tracing
            and tracing_valid
            and sampling_valid
            and api_key_present
        )

        raw_profile = os.getenv("SHOPMIND_DEPLOYMENT_PROFILE", "").strip().lower()
        os.environ["SHOPMIND_DEPLOYMENT_PROFILE"] = (
            "production" if raw_profile == "public-demo" else profile
        )
        os.environ["LANGSMITH_PROJECT"] = project
        os.environ["LANGSMITH_ENDPOINT"] = endpoint
        os.environ["LANGSMITH_TRACING_SAMPLING_RATE"] = str(sampling)
        _set_sdk_tracing(tracing_enabled)

        if requested_tracing and not api_key_present:
            LOGGER.warning(
                "LangSmith tracing disabled: LANGSMITH_API_KEY is not configured."
            )
        elif requested_tracing and (not tracing_valid or not sampling_valid):
            LOGGER.warning(
                "LangSmith tracing disabled: invalid tracing configuration."
            )

        return LangSmithRuntime(
            profile=profile,
            tracing_enabled=tracing_enabled,
            project=project,
            endpoint=endpoint,
            sampling_rate=sampling,
        )
    except Exception:  # pragma: no cover - defensive fail-closed boundary.
        _set_sdk_tracing(False)
        LOGGER.warning(
            "LangSmith tracing disabled: configuration initialization failed."
        )
        return LangSmithRuntime(
            profile="development",
            tracing_enabled=False,
            project=DEFAULT_LANGSMITH_PROJECT,
            endpoint=DEFAULT_LANGSMITH_ENDPOINT,
            sampling_rate=DEFAULT_LANGSMITH_TRACING_SAMPLING_RATE,
        )


__all__ = [
    "DEFAULT_LANGSMITH_ENDPOINT",
    "DEFAULT_LANGSMITH_PROJECT",
    "DEFAULT_LANGSMITH_TRACING",
    "DEFAULT_LANGSMITH_TRACING_SAMPLING_RATE",
    "DeploymentProfile",
    "LangSmithRuntime",
    "initialize_langsmith_runtime",
]
