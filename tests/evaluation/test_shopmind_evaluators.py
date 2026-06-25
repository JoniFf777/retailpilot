from evaluation.shopmind_evaluators import (
    expected_keywords_evaluator,
    expected_tools_evaluator,
    forbidden_tools_evaluator,
    status_evaluator,
)


def test_expected_tools_evaluator_passes_when_all_expected_tools_called() -> None:
    result = expected_tools_evaluator(
        inputs={},
        outputs={"tool_calls": ["search_products", "get_user_preferences"]},
        reference_outputs={"expected_tools": ["search_products"]},
    )

    assert result["score"] is True


def test_expected_tools_evaluator_fails_when_tool_missing() -> None:
    result = expected_tools_evaluator(
        inputs={},
        outputs={"tool_calls": ["search_products"]},
        reference_outputs={"expected_tools": ["search_products", "compare_products"]},
    )

    assert result["score"] is False
    assert "compare_products" in result["comment"]


def test_forbidden_tools_evaluator_passes_when_forbidden_tools_absent() -> None:
    result = forbidden_tools_evaluator(
        inputs={},
        outputs={"tool_calls": ["prepare_add_to_cart"]},
        reference_outputs={"forbidden_tools": ["confirm_add_to_cart"]},
    )

    assert result["score"] is True


def test_forbidden_tools_evaluator_fails_when_forbidden_tool_called() -> None:
    result = forbidden_tools_evaluator(
        inputs={},
        outputs={"tool_calls": ["confirm_add_to_cart"]},
        reference_outputs={"forbidden_tools": ["confirm_add_to_cart"]},
    )

    assert result["score"] is False
    assert "confirm_add_to_cart" in result["comment"]


def test_status_evaluator_passes_when_status_matches() -> None:
    result = status_evaluator(
        inputs={},
        outputs={"status": "confirmation_required"},
        reference_outputs={"expected_status": "confirmation_required"},
    )

    assert result["score"] is True


def test_status_evaluator_fails_when_status_differs() -> None:
    result = status_evaluator(
        inputs={},
        outputs={"status": "completed"},
        reference_outputs={"expected_status": "confirmation_required"},
    )

    assert result["score"] is False
    assert "confirmation_required" in result["comment"]


def test_expected_keywords_evaluator_passes_when_all_keywords_present() -> None:
    result = expected_keywords_evaluator(
        inputs={},
        outputs={"answer": "我已为你生成待确认加购，请确认是否加入购物车。"},
        reference_outputs={"expected_keywords": ["确认", "购物车"]},
    )

    assert result["score"] is True


def test_expected_keywords_evaluator_fails_when_keyword_missing() -> None:
    result = expected_keywords_evaluator(
        inputs={},
        outputs={"answer": "我推荐这款键盘。"},
        reference_outputs={"expected_keywords": ["购物车"]},
    )

    assert result["score"] is False
    assert "购物车" in result["comment"]

