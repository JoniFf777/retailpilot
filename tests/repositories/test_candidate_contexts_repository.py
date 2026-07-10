from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models import CandidateContext
from app.repositories.candidate_contexts import (
    clear_candidate_context,
    get_candidate_context,
    prune_candidate_contexts,
    save_candidate_context,
)


def make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()


def test_save_and_get_candidate_context():
    session = make_session()
    now = datetime(2026, 7, 10, tzinfo=timezone.utc)

    save_candidate_context(
        session,
        user_id="user-1",
        thread_id="thread-1",
        product_ids=["TECH-KEY-001", "TECH-KEY-002"],
        quantity=2,
        ttl_seconds=600,
        now=now,
    )
    session.commit()

    context = get_candidate_context(
        session,
        user_id="user-1",
        thread_id="thread-1",
        now=now + timedelta(seconds=10),
    )

    assert context is not None
    assert context["product_ids"] == ["TECH-KEY-001", "TECH-KEY-002"]
    assert context["quantity"] == 2


def test_get_candidate_context_deletes_expired_context():
    session = make_session()
    now = datetime(2026, 7, 10, tzinfo=timezone.utc)
    save_candidate_context(
        session,
        user_id="user-1",
        thread_id="thread-1",
        product_ids=["TECH-KEY-001"],
        quantity=1,
        ttl_seconds=60,
        now=now,
    )
    session.commit()

    context = get_candidate_context(
        session,
        user_id="user-1",
        thread_id="thread-1",
        now=now + timedelta(seconds=61),
    )
    rows = session.scalars(select(CandidateContext)).all()

    assert context is None
    assert rows == []


def test_prune_candidate_contexts_deletes_expired_and_oldest_overflow():
    session = make_session()
    now = datetime(2026, 7, 10, tzinfo=timezone.utc)
    for index in range(4):
        save_candidate_context(
            session,
            user_id="user-1",
            thread_id=f"thread-{index}",
            product_ids=[f"TECH-KEY-{index + 1:03d}"],
            quantity=1,
            ttl_seconds=600,
            now=now + timedelta(seconds=index),
            max_contexts=10,
        )
    session.add(
        CandidateContext(
            user_id="user-1",
            thread_id="expired",
            product_ids=["TECH-KEY-000"],
            quantity=1,
            expires_at=now - timedelta(seconds=1),
            created_at=now - timedelta(seconds=5),
            updated_at=now - timedelta(seconds=5),
        )
    )
    session.commit()

    deleted_count = prune_candidate_contexts(
        session,
        now=now + timedelta(seconds=10),
        max_contexts=2,
    )
    remaining_thread_ids = [
        row.thread_id
        for row in session.scalars(
            select(CandidateContext).order_by(CandidateContext.thread_id.asc())
        )
    ]

    assert deleted_count == 3
    assert remaining_thread_ids == ["thread-2", "thread-3"]


def test_clear_candidate_context_returns_whether_row_existed():
    session = make_session()
    now = datetime(2026, 7, 10, tzinfo=timezone.utc)
    save_candidate_context(
        session,
        user_id="user-1",
        thread_id="thread-1",
        product_ids=["TECH-KEY-001"],
        quantity=1,
        now=now,
    )

    assert clear_candidate_context(
        session,
        user_id="user-1",
        thread_id="thread-1",
    ) is True
    assert clear_candidate_context(
        session,
        user_id="user-1",
        thread_id="thread-1",
    ) is False
