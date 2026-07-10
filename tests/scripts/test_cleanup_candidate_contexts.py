from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models import CandidateContext
from scripts import cleanup_candidate_contexts


def make_session_factory():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def test_run_cleanup_deletes_expired_and_overflow_rows(monkeypatch, capsys):
    Session = make_session_factory()
    session = Session()
    now = datetime.now(timezone.utc)
    session.add_all(
        [
            CandidateContext(
                user_id="user-1",
                thread_id="expired",
                product_ids=["TECH-KEY-000"],
                quantity=1,
                expires_at=now - timedelta(seconds=1),
                created_at=now - timedelta(seconds=3),
                updated_at=now - timedelta(seconds=3),
            ),
            CandidateContext(
                user_id="user-1",
                thread_id="oldest",
                product_ids=["TECH-KEY-001"],
                quantity=1,
                expires_at=now + timedelta(minutes=10),
                created_at=now - timedelta(seconds=2),
                updated_at=now - timedelta(seconds=2),
            ),
            CandidateContext(
                user_id="user-1",
                thread_id="newest",
                product_ids=["TECH-KEY-002"],
                quantity=1,
                expires_at=now + timedelta(minutes=10),
                created_at=now - timedelta(seconds=1),
                updated_at=now - timedelta(seconds=1),
            ),
        ]
    )
    session.commit()
    session.close()
    monkeypatch.setattr(
        cleanup_candidate_contexts,
        "get_settings",
        lambda: SimpleNamespace(
            database_url="postgresql+psycopg://user:secret@127.0.0.1:5432/app"
        ),
    )

    report = cleanup_candidate_contexts.run_cleanup(
        session_factory=Session,
        max_contexts=1,
    )

    verify_session = Session()
    remaining = list(verify_session.scalars(select(CandidateContext)))
    output = capsys.readouterr().out

    assert report.deleted_count == 2
    assert report.max_contexts == 1
    assert "user:***" in output
    assert [context.thread_id for context in remaining] == ["newest"]
    verify_session.close()
