"""Server-owned read providers for structured catalog recommendation runs."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Protocol

from app.db.session import SessionLocal
from app.repositories.catalog import list_active_laptop_skus
from app.repositories.preferences import get_user_preferences
from app.schemas.catalog import CatalogSkuCandidate


class CatalogCandidateProvider(Protocol):
    """A narrow dependency boundary; callers never own its database session."""

    def list_active_laptop_skus(self) -> list[CatalogSkuCandidate]: ...


class SqlAlchemyCatalogCandidateProvider:
    """Open one short-lived local session only for catalog candidate retrieval."""

    def list_active_laptop_skus(self) -> list[CatalogSkuCandidate]:
        with self._session() as session:
            return list_active_laptop_skus(session)

    @staticmethod
    @contextmanager
    def _session():
        session = SessionLocal()
        try:
            yield session
        finally:
            session.close()


class FakeCatalogCandidateProvider:
    """Deterministic test provider with no database or global state."""

    def __init__(self, candidates: list[CatalogSkuCandidate]) -> None:
        self.candidates = list(candidates)
        self.calls = 0

    def list_active_laptop_skus(self) -> list[CatalogSkuCandidate]:
        self.calls += 1
        return list(self.candidates)


class RecommendationPreferenceProvider(Protocol):
    def summary_for_user(self, user_id: str | None) -> dict[str, object] | None: ...


class SqlAlchemyRecommendationPreferenceProvider:
    """Read preferences as optional explanatory context, never as ranking input."""

    def summary_for_user(self, user_id: str | None) -> dict[str, object] | None:
        if not user_id:
            return None
        with SqlAlchemyCatalogCandidateProvider._session() as session:
            preferences = get_user_preferences(session, user_id)
        return {"source": "preferences", "preference_count": len(preferences), "informational_only": True}


class FakeRecommendationPreferenceProvider:
    def __init__(self, summary: dict[str, object] | None = None) -> None:
        self.summary = summary
        self.calls: list[str | None] = []

    def summary_for_user(self, user_id: str | None) -> dict[str, object] | None:
        self.calls.append(user_id)
        return self.summary
