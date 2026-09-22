import pytest

from app.shopping_tasks.contracts import ShoppingTaskRequest
from app.shopping_tasks.repository import CommandConflict, create_task, find_command
from tests.shopping_tasks.test_repository import session_factory


def test_command_replay_returns_original_result_and_conflicting_body_is_rejected() -> (
    None
):
    Session = session_factory()
    session = Session()
    request = ShoppingTaskRequest(
        kind="compatibility_diagnosis", goal_text="连接无画面"
    )
    task = create_task(
        session, owner_id="owner-a", request=request, idempotency_key="create-1"
    )
    session.commit()
    replay = create_task(
        session, owner_id="owner-a", request=request, idempotency_key="create-1"
    )
    assert replay.id == task.id
    with pytest.raises(CommandConflict):
        find_command(
            session,
            owner_id="owner-a",
            operation="create_task",
            idempotency_key="create-1",
            body={"goal_text": "different"},
        )
