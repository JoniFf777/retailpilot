"""Server-owned read providers for structured catalog recommendation runs."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Protocol

from app.db.session import SessionLocal
from app.repositories.catalog import list_active_laptop_skus, list_active_skus
from app.repositories.preferences import get_user_preferences
from app.schemas.catalog import CatalogSkuCandidate
from app.schemas.recommendation import CategoryAttributeConstraint


class CatalogCandidateProvider(Protocol):
    """A narrow dependency boundary; callers never own its database session."""

    def list_active_skus(self, category_code: str) -> list[CatalogSkuCandidate]: ...

    def list_active_laptop_skus(self) -> list[CatalogSkuCandidate]: ...


class SqlAlchemyCatalogCandidateProvider:
    """Open one short-lived local session only for catalog candidate retrieval."""

    def list_active_skus(self, category_code: str) -> list[CatalogSkuCandidate]:
        with self._session() as session:
            return list_active_skus(session, category_code=category_code)

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

    def list_active_skus(self, category_code: str) -> list[CatalogSkuCandidate]:
        self.calls += 1
        return list(self.candidates)

    def list_active_laptop_skus(self) -> list[CatalogSkuCandidate]:
        return self.list_active_skus("laptop")


class RecommendationPreferenceProvider(Protocol):
    def summary_for_user(self, user_id: str | None) -> dict[str, object] | None: ...

    def preference_constraints_for_user(
        self, user_id: str | None, category: str
    ) -> dict[str, CategoryAttributeConstraint]: ...


class SqlAlchemyRecommendationPreferenceProvider:
    """Read preferences as bounded, soft ranking signals for one category."""

    def summary_for_user(self, user_id: str | None) -> dict[str, object] | None:
        if not user_id:
            return None
        with SqlAlchemyCatalogCandidateProvider._session() as session:
            preferences = get_user_preferences(session, user_id)
        # The summary is display metadata; ranking inputs are returned through
        # preference_constraints_for_user so the public summary stays PII-free.
        return {
            "source": "preferences",
            "preference_count": len(preferences),
            "informational_only": True,
        }

    def preference_constraints_for_user(
        self, user_id: str | None, category: str
    ) -> dict[str, CategoryAttributeConstraint]:
        if not user_id:
            return {}
        from app.recommendation.request import parse_recommendation_request

        with SqlAlchemyCatalogCandidateProvider._session() as session:
            preferences = get_user_preferences(session, user_id)
        constraints: dict[str, CategoryAttributeConstraint] = {}
        priorities: dict[str, tuple[int, int]] = {}
        for index, preference in enumerate(preferences):
            try:
                request = parse_recommendation_request(
                    str(preference["preference_value"]), category
                )
            except Exception:
                continue
            preference_type = str(preference.get("preference_type") or "other")
            for key, constraint in request.category_attributes.items():
                if constraint.role == "soft":
                    if preference_type == "avoid" and constraint.polarity == "include":
                        constraint = constraint.model_copy(
                            update={"polarity": "exclude"}
                        )
                    # Avoid constraints take precedence over positive defaults;
                    # within one type the repository returns newest first.
                    priority = (2 if constraint.polarity == "exclude" else 1, -index)
                    if priority >= priorities.get(key, (-1, -10_000)):
                        constraints[key] = constraint
                        priorities[key] = priority
        return constraints


class FakeRecommendationPreferenceProvider:
    def __init__(
        self,
        summary: dict[str, object] | None = None,
        constraints: dict[str, CategoryAttributeConstraint] | None = None,
    ) -> None:
        self.summary = summary
        self.constraints = dict(constraints or {})
        self.calls: list[str | None] = []

    def summary_for_user(self, user_id: str | None) -> dict[str, object] | None:
        self.calls.append(user_id)
        return self.summary

    def preference_constraints_for_user(
        self, user_id: str | None, category: str
    ) -> dict[str, CategoryAttributeConstraint]:
        del user_id, category
        return dict(self.constraints)
