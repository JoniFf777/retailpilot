"""ShopMind V2 configuration helpers.

This module is intentionally additive. The legacy workshop `config.py` module
continues to power the existing V1 tools and agents while V2 infrastructure is
introduced incrementally.
"""

from functools import lru_cache
import os
from typing import Optional

from pydantic import BaseModel, Field

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
DEFAULT_LANGSMITH_TRACING = True
DEFAULT_LANGSMITH_PROJECT = "langsmith-agent-lifecycle-workshop"
DEFAULT_WORKSHOP_MODEL = "anthropic:claude-haiku-4-5"
DEFAULT_SHOPMIND_AGENT_MODE = "single"
DEFAULT_SHOPMIND_SUPERVISOR_ROUTER = "deterministic"


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


class Settings(BaseModel):
    """Runtime settings for the V2 infrastructure layer."""

    database_url: str = Field(default=DEFAULT_DATABASE_URL)
    test_database_url: str = Field(default=DEFAULT_TEST_DATABASE_URL)
    embedding_provider: str = Field(default=DEFAULT_EMBEDDING_PROVIDER)
    vector_dimension: int = Field(default=DEFAULT_VECTOR_DIMENSION)
    langsmith_api_key: Optional[str] = Field(default=None)
    langsmith_tracing: bool = Field(default=DEFAULT_LANGSMITH_TRACING)
    langsmith_project: str = Field(default=DEFAULT_LANGSMITH_PROJECT)
    workshop_model: str = Field(default=DEFAULT_WORKSHOP_MODEL)
    shopmind_agent_mode: str = Field(default=DEFAULT_SHOPMIND_AGENT_MODE)
    shopmind_supervisor_router: str = Field(default=DEFAULT_SHOPMIND_SUPERVISOR_ROUTER)

    @classmethod
    def from_env(cls) -> "Settings":
        """Build settings from environment variables and an optional `.env` file."""
        _load_dotenv()
        return cls(
            database_url=os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL),
            test_database_url=os.getenv("TEST_DATABASE_URL", DEFAULT_TEST_DATABASE_URL),
            embedding_provider=os.getenv(
                "EMBEDDING_PROVIDER", DEFAULT_EMBEDDING_PROVIDER
            ),
            vector_dimension=_get_int_env("VECTOR_DIMENSION", DEFAULT_VECTOR_DIMENSION),
            langsmith_api_key=os.getenv("LANGSMITH_API_KEY"),
            langsmith_tracing=_get_bool_env(
                "LANGSMITH_TRACING", DEFAULT_LANGSMITH_TRACING
            ),
            langsmith_project=os.getenv(
                "LANGSMITH_PROJECT", DEFAULT_LANGSMITH_PROJECT
            ),
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
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached V2 settings for application code."""
    return Settings.from_env()
