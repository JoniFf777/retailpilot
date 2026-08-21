from app.recommendation.gate import classify_recommendation_request


def test_constraint_only_laptop_brief_enters_structured_recommendation_path() -> None:
    decision = classify_recommendation_request(
        "预算 6000 元以内，主要用于 Java 开发，内存至少 16GB，希望尽量轻"
    )

    assert decision.mode == "structured_laptop_recommendation"
