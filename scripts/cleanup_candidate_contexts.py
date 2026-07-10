"""Clean expired and overflow V3 candidate-selection contexts."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Callable

from sqlalchemy.orm import Session

from app.core.settings import get_settings
from app.repositories.candidate_contexts import prune_candidate_contexts
from scripts.smoke_postgres import _mask_database_url


DEFAULT_MAX_CONTEXTS = 100


@dataclass(frozen=True)
class CandidateContextCleanupReport:
    database_url: str
    deleted_count: int
    max_contexts: int


def run_cleanup(
    *,
    session_factory: Callable[[], Session] | None = None,
    max_contexts: int = DEFAULT_MAX_CONTEXTS,
) -> CandidateContextCleanupReport:
    settings = get_settings()
    if session_factory is None:
        from app.db.session import SessionLocal

        session_factory = SessionLocal

    session = session_factory()
    try:
        deleted_count = prune_candidate_contexts(session, max_contexts=max_contexts)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    report = CandidateContextCleanupReport(
        database_url=_mask_database_url(settings.database_url),
        deleted_count=deleted_count,
        max_contexts=max_contexts,
    )
    print_report(report)
    return report


def print_report(report: CandidateContextCleanupReport) -> None:
    print(f"Candidate context cleanup database: {report.database_url}")
    print(f"Candidate context deleted rows: {report.deleted_count}")
    print(f"Candidate context max rows: {report.max_contexts}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Delete expired candidate_contexts rows and oldest overflow rows."
    )
    parser.add_argument(
        "--max-contexts",
        type=int,
        default=DEFAULT_MAX_CONTEXTS,
        help="Maximum active candidate contexts to keep after cleanup.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    run_cleanup(max_contexts=args.max_contexts)


if __name__ == "__main__":
    main()
