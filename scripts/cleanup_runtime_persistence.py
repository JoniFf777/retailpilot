"""Clean expired ShopMind runtime persistence rows."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Callable

from sqlalchemy.orm import Session

from app.core.settings import get_settings
from app.operations import write_runtime_cleanup_evidence
from app.repositories.runtime_maintenance import prune_runtime_persistence
from scripts.smoke_postgres import _mask_database_url


@dataclass(frozen=True)
class RuntimePersistenceCleanupReport:
    database_url: str
    deleted_threads: int
    deleted_runs: int
    deleted_messages: int
    deleted_summaries: int
    deleted_idempotency_records: int
    deleted_memory_records: int
    deleted_governance_audit_records: int

    @property
    def deleted_total(self) -> int:
        return (
            self.deleted_threads
            + self.deleted_runs
            + self.deleted_messages
            + self.deleted_summaries
            + self.deleted_idempotency_records
            + self.deleted_memory_records
            + self.deleted_governance_audit_records
        )


def run_cleanup(
    *,
    session_factory: Callable[[], Session] | None = None,
) -> RuntimePersistenceCleanupReport:
    settings = get_settings()
    if session_factory is None:
        from app.db.session import SessionLocal

        session_factory = SessionLocal

    session = session_factory()
    try:
        cleanup = prune_runtime_persistence(session)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    report = RuntimePersistenceCleanupReport(
        database_url=_mask_database_url(settings.database_url),
        deleted_threads=cleanup.deleted_threads,
        deleted_runs=cleanup.deleted_runs,
        deleted_messages=cleanup.deleted_messages,
        deleted_summaries=cleanup.deleted_summaries,
        deleted_idempotency_records=cleanup.deleted_idempotency_records,
        deleted_memory_records=cleanup.deleted_memory_records,
        deleted_governance_audit_records=(
            cleanup.deleted_governance_audit_records
        ),
    )
    evidence_path = getattr(
        settings,
        "shopmind_runtime_cleanup_evidence_path",
        None,
    )
    if evidence_path:
        write_runtime_cleanup_evidence(evidence_path)
    print_report(report)
    return report


def print_report(report: RuntimePersistenceCleanupReport) -> None:
    print(f"Runtime cleanup database: {report.database_url}")
    print(f"Runtime cleanup deleted threads: {report.deleted_threads}")
    print(f"Runtime cleanup deleted runs: {report.deleted_runs}")
    print(f"Runtime cleanup deleted messages: {report.deleted_messages}")
    print(f"Runtime cleanup deleted summaries: {report.deleted_summaries}")
    print(
        "Runtime cleanup deleted idempotency records: "
        f"{report.deleted_idempotency_records}"
    )
    print(f"Runtime cleanup deleted memory records: {report.deleted_memory_records}")
    print(
        "Runtime cleanup deleted governance audit records: "
        f"{report.deleted_governance_audit_records}"
    )
    print(f"Runtime cleanup deleted total: {report.deleted_total}")


def build_parser() -> argparse.ArgumentParser:
    return argparse.ArgumentParser(
        description=(
            "Delete expired runtime persistence and governance audit rows."
        )
    )


def main() -> None:
    build_parser().parse_args()
    run_cleanup()


if __name__ == "__main__":
    main()
