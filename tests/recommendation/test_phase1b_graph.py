from decimal import Decimal
from uuid import uuid4

import pytest

from agents.shopmind_multi_agent.graph import invoke_shopmind_multi_agent
from agents.shopmind_multi_agent.rag_agent import rag_agent_node
from agents.shopmind_multi_agent.preference_agent import preference_agent_node
from app.recommendation.providers import (
    FakeCatalogCandidateProvider,
    FakeRecommendationPreferenceProvider,
)
from app.recommendation.rag import (
    FakeRecommendationEvidenceProvider,
    RecommendationEvidence,
    RetrievalBudget,
    SemanticEvidenceReranker,
    SqlAlchemyRecommendationEvidenceProvider,
    build_retrieval_query_plan,
)
from app.recommendation.providers import SqlAlchemyRecommendationPreferenceProvider
from app.schemas.catalog import CatalogAttributeDefinition, CatalogSkuCandidate
from app.schemas.recommendation import (
    CategoryAttributeConstraint,
    EvidenceView,
    RecommendationResult,
)


def _candidate(code: str, *, price: str, use_cases: list[str]) -> CatalogSkuCandidate:
    return CatalogSkuCandidate(
        product_id=uuid4(),
        product_code=f"P-{code}",
        product_name=f"Laptop {code}",
        brand="Test",
        sku_id=uuid4(),
        sku_code=code,
        sku_name=code,
        money_amount=Decimal(price),
        currency="CNY",
        available_quantity=4,
        product_attributes={
            "cpu_tier": "i7",
            "gpu_tier": "entry",
            "memory_gb": 16,
            "storage_gb": 512,
            "weight_kg": 1.3,
            "screen_inches": 14,
            "use_cases": use_cases,
            "internal": "hidden",
        },
        attribute_definitions=[
            CatalogAttributeDefinition(
                code="memory_gb",
                name="Memory",
                scope="spu",
                data_type="integer",
                unit="GB",
                comparable=True,
                display_order=10,
            ),
            CatalogAttributeDefinition(
                code="storage_gb",
                name="Storage",
                scope="spu",
                data_type="integer",
                unit="GB",
                comparable=True,
                display_order=20,
            ),
            CatalogAttributeDefinition(
                code="use_cases",
                name="Use cases",
                scope="spu",
                data_type="string_list",
                display_order=30,
            ),
        ],
    )


def test_structured_laptop_graph_uses_catalog_top_k_before_exact_rag() -> None:
    first = _candidate("LAP-A", price="4999", use_cases=["java_development"])
    second = _candidate("LAP-B", price="5599", use_cases=["office"])
    candidates = FakeCatalogCandidateProvider([second, first])
    evidence = FakeRecommendationEvidenceProvider(
        RecommendationEvidence(
            product_evidence={
                "LAP-A": [
                    EvidenceView(
                        source="product_rag",
                        type="product_document",
                        field="document_excerpt",
                        value="safe",
                        ref="doc-1",
                    )
                ]
            },
            policy_evidence=[],
            diagnostics={"product_document_count": 1},
        )
    )
    result = invoke_shopmind_multi_agent(
        "预算 6000 元以内，推荐一台用于 Java 开发的笔记本，内存至少 16GB",
        catalog_candidate_provider=candidates,
        recommendation_preference_provider=FakeRecommendationPreferenceProvider(),
        recommendation_evidence_provider=evidence,
    )

    recommendation = RecommendationResult.model_validate(result["recommendation"])
    assert candidates.calls == 1
    assert evidence.calls == [["LAP-A", "LAP-B"]]
    assert [item.sku_id for item in recommendation.recommendations] == [
        first.sku_id,
        second.sku_id,
    ]
    assert recommendation.recommendations[0].evidence[0].source == "product_rag"
    assert result["shopping_session_state"]["field_sources"]["memory_min_gb"] == "user"
    assert [spec.code for spec in recommendation.recommendations[0].specifications] == [
        "memory_gb",
        "storage_gb",
        "use_cases",
    ]
    assert "internal" not in str(recommendation.model_dump())
    assert result["raw_result"]["agent_steps"][-1]["node"] == "recommendation_decision"


def test_incomplete_laptop_request_returns_structured_clarification_without_rag() -> (
    None
):
    evidence = FakeRecommendationEvidenceProvider()
    result = invoke_shopmind_multi_agent(
        "推荐一台笔记本",
        catalog_candidate_provider=FakeCatalogCandidateProvider(
            [_candidate("LAP-A", price="4999", use_cases=[])]
        ),
        recommendation_preference_provider=FakeRecommendationPreferenceProvider(),
        recommendation_evidence_provider=evidence,
    )
    recommendation = RecommendationResult.model_validate(result["recommendation"])
    assert recommendation.outcome == "clarification_required"
    assert evidence.calls == []


def test_recommendation_evidence_failure_keeps_catalog_result() -> None:
    class BrokenEvidenceProvider:
        def retrieve(self, *, message, top_k):
            raise RuntimeError("embedding model unavailable")

    result = invoke_shopmind_multi_agent(
        "预算 6000 元以内，推荐一台用于 Java 开发的笔记本，内存至少 16GB",
        catalog_candidate_provider=FakeCatalogCandidateProvider(
            [_candidate("LAP-A", price="4999", use_cases=["java_development"])]
        ),
        recommendation_preference_provider=FakeRecommendationPreferenceProvider(),
        recommendation_evidence_provider=BrokenEvidenceProvider(),
    )

    recommendation = RecommendationResult.model_validate(result["recommendation"])
    assert recommendation.outcome == "recommended"
    assert recommendation.recommendations[0].evidence == []
    assert (
        result["raw_result"]["recommendation_diagnostics"]["evidence_unavailable"]
        is True
    )


def test_rag_agent_without_local_tools_returns_safe_summary() -> None:
    result = rag_agent_node(
        {"messages": [{"role": "user", "content": "查询退货政策"}]},
        tools={},
    )

    assert result["rag_summary"]["confidence"] == "medium"
    assert result["rag_summary"]["citations"] == []
    assert result["rag_summary"]["status"] == "degraded"
    assert result["rag_summary"]["reason_code"] == "rag_tool_not_configured"
    assert result["tool_calls"] == []
    assert "跳过 embedding" in result["rag_summary"]["summary"]


def test_preference_agent_accepts_guarded_tool_iterable() -> None:
    class FakePreferenceTool:
        name = "get_user_preferences"

        def invoke(self, _arguments):
            return "暂无已记录偏好。"

    result = preference_agent_node(
        {
            "messages": [{"role": "user", "content": "预算 6000"}],
            "user_id": "test-user",
        },
        tools=[FakePreferenceTool()],
    )

    assert result["preference_summary"]["preference_count"] == 0


def test_confirmed_soft_preference_changes_recommendation_ranking() -> None:
    office = _candidate("LAP-OFFICE", price="4999", use_cases=["office"])
    java = _candidate("LAP-JAVA", price="5199", use_cases=["java_development"])
    provider = FakeRecommendationPreferenceProvider(
        summary={"source": "preferences", "preference_count": 1},
        constraints={
            "primary_use_cases": CategoryAttributeConstraint(
                value=["java_development"], operator="enum_match", role="soft"
            )
        },
    )
    result = invoke_shopmind_multi_agent(
        "预算6000元以内，推荐一台笔记本",
        catalog_candidate_provider=FakeCatalogCandidateProvider([office, java]),
        recommendation_preference_provider=provider,
        recommendation_evidence_provider=FakeRecommendationEvidenceProvider(),
    )

    recommendation = RecommendationResult.model_validate(result["recommendation"])
    assert recommendation.recommendations[0].sku_name == "LAP-JAVA"
    assert (
        result["raw_result"]["recommendation_diagnostics"][
            "preference_used_for_ranking"
        ]
        is True
    )


def test_recommendation_follow_up_inherits_thread_context_and_overrides_budget() -> (
    None
):
    candidate = _candidate("LAP-CONTEXT", price="6500", use_cases=["java_development"])
    result = invoke_shopmind_multi_agent(
        "预算改成7000元，其他要求不变",
        user_id="context-user",
        thread_id="context-thread",
        context_items=[
            {
                "content": "预算6000元以内，推荐一台用于Java开发的笔记本，内存至少16GB",
                "provenance": {
                    "source": "conversation_message",
                    "role": "user",
                    "sequence": 1,
                },
            }
        ],
        catalog_candidate_provider=FakeCatalogCandidateProvider([candidate]),
        recommendation_preference_provider=FakeRecommendationPreferenceProvider(),
        recommendation_evidence_provider=FakeRecommendationEvidenceProvider(),
    )
    recommendation = RecommendationResult.model_validate(result["recommendation"])
    assert recommendation.outcome == "recommended"
    assert recommendation.recommendation_request is not None
    assert recommendation.recommendation_request.budget_max == Decimal("7000")
    assert (
        str(
            recommendation.recommendation_request.category_attributes["memory_min_gb"][
                "value"
            ]
        )
        == "16"
    )
    assert (
        result["raw_result"]["recommendation_gate"]["reason"]
        == "category_inherited_from_thread_context"
    )
    assert result["shopping_session_state"]["version"] == 1


def test_recommendation_follow_up_can_clear_an_inherited_budget() -> None:
    candidate = _candidate(
        "LAP-CLEAR-BUDGET", price="6500", use_cases=["java_development"]
    )
    result = invoke_shopmind_multi_agent(
        "预算不限，其他要求不变",
        user_id="context-user",
        thread_id="context-thread",
        context_items=[
            {
                "content": "预算6000元以内，推荐一台用于Java开发的笔记本，内存至少16GB",
                "provenance": {
                    "source": "conversation_message",
                    "role": "user",
                    "sequence": 1,
                },
            }
        ],
        catalog_candidate_provider=FakeCatalogCandidateProvider([candidate]),
        recommendation_preference_provider=FakeRecommendationPreferenceProvider(),
        recommendation_evidence_provider=FakeRecommendationEvidenceProvider(),
    )
    recommendation = RecommendationResult.model_validate(result["recommendation"])
    assert recommendation.outcome == "recommended"
    assert recommendation.recommendation_request is not None
    assert recommendation.recommendation_request.budget_max is None
    assert (
        str(
            recommendation.recommendation_request.category_attributes["memory_min_gb"][
                "value"
            ]
        )
        == "16"
    )


def test_recommendation_can_resume_from_persisted_structured_state() -> None:
    candidate = _candidate("LAP-STATE", price="6500", use_cases=["java_development"])
    result = invoke_shopmind_multi_agent(
        "预算改成7000元，其他要求不变",
        user_id="context-user",
        thread_id="context-thread",
        context_items=[
            {
                "content": "上一轮推荐结果",
                "provenance": {
                    "source": "conversation_message",
                    "role": "assistant",
                    "recommendation_state": {
                        "category": "laptop",
                        "budget_max": "6000",
                        "budget_currency": "CNY",
                        "category_attributes": {
                            "memory_min_gb": {
                                "value": "16",
                                "operator": "gte",
                                "role": "hard",
                            }
                        },
                    },
                },
            }
        ],
        catalog_candidate_provider=FakeCatalogCandidateProvider([candidate]),
        recommendation_preference_provider=FakeRecommendationPreferenceProvider(),
        recommendation_evidence_provider=FakeRecommendationEvidenceProvider(),
    )
    recommendation = RecommendationResult.model_validate(result["recommendation"])
    assert recommendation.outcome == "recommended"
    assert recommendation.recommendation_request is not None
    assert recommendation.recommendation_request.budget_max == Decimal("7000")


def test_recommendation_follow_up_excludes_an_item_from_previous_ordered_candidates() -> (
    None
):
    first = _candidate("LAP-ONE", price="5000", use_cases=["java_development"])
    second = _candidate("LAP-TWO", price="5100", use_cases=["java_development"])
    result = invoke_shopmind_multi_agent(
        "排除第2个",
        user_id="context-user",
        thread_id="context-thread",
        context_items=[
            {
                "content": "上一轮推荐结果",
                "provenance": {
                    "source": "conversation_message",
                    "role": "assistant",
                    "recommendation_state": {
                        "schema_version": "shopmind.shopping-session-state.v1",
                        "owner_id": "context-user",
                        "thread_id": "context-thread",
                        "version": 1,
                        "category": "laptop",
                        "budget_max": "6000",
                        "budget_currency": "CNY",
                        "category_attributes": {
                            "memory_min_gb": {
                                "value": "16",
                                "operator": "gte",
                                "role": "hard",
                            }
                        },
                        "candidate_sku_codes": ["LAP-ONE", "LAP-TWO"],
                    },
                },
            }
        ],
        catalog_candidate_provider=FakeCatalogCandidateProvider([first, second]),
        recommendation_preference_provider=FakeRecommendationPreferenceProvider(),
        recommendation_evidence_provider=FakeRecommendationEvidenceProvider(),
    )
    recommendation = RecommendationResult.model_validate(result["recommendation"])
    assert recommendation.outcome == "recommended"
    assert [item.sku_name for item in recommendation.recommendations] == ["LAP-ONE"]


def test_lexical_retrieval_survives_embedding_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = _candidate(
        "LAP-LEXICAL", price="5000", use_cases=["office"]
    ).model_copy(update={"legacy_product_id": "LEGACY-LAP-LEXICAL"})

    class Session:
        def rollback(self) -> None:
            return None

        def close(self) -> None:
            return None

    import app.recommendation.rag as rag_module
    from app.repositories import documents as document_repository

    monkeypatch.setattr(rag_module, "SessionLocal", lambda: Session())
    monkeypatch.setattr(
        document_repository,
        "search_product_documents_for_product_ids",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("embedding unavailable")
        ),
    )
    monkeypatch.setattr(
        document_repository,
        "search_keyword_documents",
        lambda *args, **kwargs: [
            {
                "id": "doc-lexical",
                "product_id": "LEGACY-LAP-LEXICAL",
                "content": "Office keyboard details.",
            }
        ],
    )
    provider = SqlAlchemyRecommendationEvidenceProvider(
        embed_query=lambda _query: (_ for _ in ()).throw(
            RuntimeError("embedding unavailable")
        )
    )

    evidence = provider.retrieve(message="office keyboard", top_k=[candidate])
    assert evidence.product_evidence["LAP-LEXICAL"]
    assert evidence.diagnostics["product_vector_status"] == "unavailable"
    assert evidence.diagnostics["product_keyword_status"] == "ok"


def test_document_dependent_recommendation_does_not_claim_unknown_evidence() -> None:
    candidate = _candidate("LAP-EVIDENCE", price="5000", use_cases=["office"])
    result = invoke_shopmind_multi_agent(
        "预算6000元以内，推荐一台笔记本，需要兼容USB4",
        catalog_candidate_provider=FakeCatalogCandidateProvider([candidate]),
        recommendation_preference_provider=FakeRecommendationPreferenceProvider(),
        recommendation_evidence_provider=FakeRecommendationEvidenceProvider(
            RecommendationEvidence(
                product_evidence={"LAP-EVIDENCE": []},
                policy_evidence=[],
                diagnostics={"evidence_status": "unknown"},
            )
        ),
    )

    recommendation = RecommendationResult.model_validate(result["recommendation"])
    assert recommendation.outcome == "clarification_required"
    assert recommendation.error_code == "evidence_unknown"
    assert (
        result["raw_result"]["recommendation_diagnostics"]["evidence_status"]
        == "unknown"
    )


def test_document_evidence_breaks_catalog_ties_for_document_dependent_request() -> None:
    first = _candidate("LAP-NO-EVIDENCE", price="5000", use_cases=["office"])
    second = _candidate("LAP-WITH-EVIDENCE", price="5200", use_cases=["office"])
    evidence = FakeRecommendationEvidenceProvider(
        RecommendationEvidence(
            product_evidence={
                "LAP-WITH-EVIDENCE": [
                    EvidenceView(
                        source="product_rag",
                        type="product_document",
                        field="document_excerpt",
                        value="支持USB4兼容设备。",
                        ref="doc-usb4",
                    )
                ]
            },
            policy_evidence=[],
            diagnostics={"evidence_status": "available"},
        )
    )
    result = invoke_shopmind_multi_agent(
        "预算6000元以内，推荐一台笔记本，需要兼容USB4",
        catalog_candidate_provider=FakeCatalogCandidateProvider([first, second]),
        recommendation_preference_provider=FakeRecommendationPreferenceProvider(),
        recommendation_evidence_provider=evidence,
    )
    recommendation = RecommendationResult.model_validate(result["recommendation"])
    assert recommendation.recommendations[0].sku_name == "LAP-WITH-EVIDENCE"


def test_avoid_preference_is_converted_to_exclusion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from contextlib import contextmanager
    import app.recommendation.providers as providers_module

    @contextmanager
    def fake_session():
        yield object()

    monkeypatch.setattr(
        providers_module.SqlAlchemyCatalogCandidateProvider,
        "_session",
        staticmethod(fake_session),
    )
    monkeypatch.setattr(
        providers_module,
        "get_user_preferences",
        lambda _session, _user_id: [
            {"preference_type": "avoid", "preference_value": "游戏"}
        ],
    )

    constraints = (
        SqlAlchemyRecommendationPreferenceProvider().preference_constraints_for_user(
            "user-1", "laptop"
        )
    )
    assert constraints["primary_use_cases"].value == ["gaming"]
    assert constraints["primary_use_cases"].polarity == "exclude"


def test_excluded_soft_preference_does_not_reward_the_excluded_candidate() -> None:
    from app.recommendation.categories import default_category_registry
    from app.recommendation.constraints import (
        evaluate_constraint_status,
        preference_signal,
    )

    definition = (
        default_category_registry()
        .schema_for("laptop")
        .attribute_for("primary_use_cases")
    )
    assert definition is not None
    excluded = CategoryAttributeConstraint(
        value=["gaming"], operator="enum_match", role="soft", polarity="exclude"
    )
    assert preference_signal(definition, excluded, ["gaming"]) == 0
    assert preference_signal(definition, excluded, ["office"]) == 1
    assert evaluate_constraint_status(definition, excluded, None) == "unknown"
    assert (
        evaluate_constraint_status(definition, excluded, ["gaming", "office"])
        == "mismatch"
    )
    assert (
        evaluate_constraint_status(definition, excluded, ["not-a-known-use-case"])
        == "unknown"
    )


def test_retrieval_budget_keeps_recall_fusion_and_context_limits_distinct() -> None:
    budget = RetrievalBudget(
        recall_per_scope=3, candidate_limit=8, context_per_candidate=2
    )
    assert budget.recall_per_scope == 3
    assert budget.candidate_limit == 8
    assert budget.context_per_candidate == 2
    with pytest.raises(ValueError):
        RetrievalBudget(recall_per_scope=1, candidate_limit=1, context_per_candidate=2)


def test_retrieval_query_plan_keeps_original_request_and_bounds_subquestions() -> None:
    message = "预算6000元以内，16GB内存，不要独显，需要兼容USB4和退货政策"
    plan = build_retrieval_query_plan(message, limit=3)
    assert plan["product"][0] == message
    assert plan["policy"][0] == message
    assert len(plan["product"]) <= 3
    assert len(plan["policy"]) <= 3


def test_semantic_reranker_is_lazy_bounded_and_model_independent_under_test() -> None:
    class FakeCrossEncoder:
        def predict(self, pairs, show_progress_bar=False):
            del show_progress_bar
            return [len(content) for _, content in pairs]

    created: list[str] = []
    reranker = SemanticEvidenceReranker(
        "fake-cross-encoder",
        model_factory=lambda name: (created.append(name) or FakeCrossEncoder()),
        max_documents=2,
    )
    assert created == []
    documents = [
        {"id": "a", "content": "short"},
        {"id": "b", "content": "much longer evidence"},
        {"id": "c", "content": "ignored"},
    ]
    result = reranker.rerank("query", documents, 2)
    assert created == ["fake-cross-encoder"]
    assert [item["id"] for item in result] == ["b", "a"]


def test_structured_recommendation_accepts_a_server_owned_short_dynamic_plan() -> None:
    candidate = _candidate("LAP-DYNAMIC", price="5000", use_cases=["office"])
    result = invoke_shopmind_multi_agent(
        "预算6000元以内，推荐一台办公笔记本",
        recommendation_task_plan=[
            {"step_id": "catalog", "stage": "catalog", "depends_on": []},
            {"step_id": "ranking", "stage": "ranking", "depends_on": ["catalog"]},
            {"step_id": "decision", "stage": "decision", "depends_on": ["ranking"]},
        ],
        catalog_candidate_provider=FakeCatalogCandidateProvider([candidate]),
        recommendation_preference_provider=FakeRecommendationPreferenceProvider(),
        recommendation_evidence_provider=FakeRecommendationEvidenceProvider(),
    )
    recommendation = RecommendationResult.model_validate(result["recommendation"])
    assert recommendation.outcome == "recommended"
    task = result["raw_result"]["recommendation_task"]
    assert task["status"] == "completed"
    assert [
        event["stage"]
        for event in task["stage_events"]
        if event["status"] == "completed"
    ] == [
        "catalog",
        "ranking",
        "decision",
    ]
