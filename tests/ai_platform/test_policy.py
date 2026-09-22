from datetime import date, timedelta

from app.ai_platform.policy import evaluate_order_policy_eligibility


def test_policy_eligibility_requires_owner_order_facts():
    assert (
        evaluate_order_policy_eligibility(
            policy={"opened_window_days": 14}, order=None, today=date.today()
        )["status"]
        == "needs_order_facts"
    )


def test_policy_eligibility_combines_current_policy_and_order():
    result = evaluate_order_policy_eligibility(
        policy={"opened_window_days": 14},
        order={"delivered_at": date.today() - timedelta(days=3), "status": "paid"},
        today=date.today(),
    )
    assert result == {"status": "eligible", "reason": "current_policy_and_order_facts"}
