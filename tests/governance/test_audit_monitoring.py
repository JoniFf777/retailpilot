import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.governance import (
    GovernanceAuditEmissionMonitor,
    GovernanceAuditEmissionReason,
    GovernanceAuditEmissionResult,
    GovernanceAuditEmissionStatus,
    GovernanceAuditEmitter,
)
from app.security import (
    AuditDecision,
    AuditOperation,
    AuditReason,
    GovernanceAuditFactory,
)


NOW = datetime(2026, 7, 26, 13, 0, tzinfo=timezone.utc)


def make_session_factory():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def make_record():
    return GovernanceAuditFactory(
        clock=lambda: NOW,
        audit_id_factory=lambda: UUID(
            "00000000-0000-0000-0000-000000000301"
        ),
    ).action_decision(
        operation=AuditOperation.ACTION_CONFIRM,
        decision=AuditDecision.SUCCEEDED,
        reason=AuditReason.COMPLETED,
        action_type="add_to_cart",
        action_id="private-action-monitor",
        principal=None,
        owner_id="private-owner-monitor",
    )


def _result(
    *,
    status: GovernanceAuditEmissionStatus,
    reason: GovernanceAuditEmissionReason,
    requested: int,
    persisted: int = 0,
    duplicates: int = 0,
) -> GovernanceAuditEmissionResult:
    return GovernanceAuditEmissionResult(
        status=status,
        reason=reason,
        requested_records=requested,
        persisted_records=persisted,
        duplicate_records=duplicates,
    )


def test_monitor_counts_closed_results_and_recovers_alert_state() -> None:
    monitor = GovernanceAuditEmissionMonitor(
        alert_failure_threshold=2,
        clock=lambda: NOW,
    )

    monitor.observe(
        _result(
            status=GovernanceAuditEmissionStatus.SKIPPED,
            reason=GovernanceAuditEmissionReason.NO_RECORDS,
            requested=0,
        )
    )
    first_failure = monitor.observe(
        _result(
            status=GovernanceAuditEmissionStatus.FAILED,
            reason=GovernanceAuditEmissionReason.STORAGE_UNAVAILABLE,
            requested=2,
        )
    )
    second_failure = monitor.observe(
        _result(
            status=GovernanceAuditEmissionStatus.FAILED,
            reason=GovernanceAuditEmissionReason.STORAGE_UNAVAILABLE,
            requested=1,
        )
    )
    recovered = monitor.observe(
        _result(
            status=GovernanceAuditEmissionStatus.PERSISTED,
            reason=GovernanceAuditEmissionReason.COMPLETED,
            requested=3,
            persisted=2,
            duplicates=1,
        )
    )
    snapshot = monitor.snapshot()

    assert first_failure.alert_activated is False
    assert second_failure.alert_activated is True
    assert recovered.alert_recovered is True
    assert snapshot.status == "healthy"
    assert snapshot.alert_active is False
    assert snapshot.emission_calls_total == 4
    assert snapshot.storage_attempts_total == 3
    assert snapshot.requested_records_total == 6
    assert snapshot.persisted_records_total == 2
    assert snapshot.duplicate_records_total == 1
    assert snapshot.skipped_calls_total == 1
    assert snapshot.failed_calls_total == 2
    assert snapshot.consecutive_failures == 0
    assert snapshot.alert_transitions_total == 1
    assert snapshot.recovery_transitions_total == 1
    assert snapshot.last_failure_at == NOW
    assert snapshot.last_success_at == NOW


def test_monitor_is_thread_safe_and_activates_alert_once() -> None:
    monitor = GovernanceAuditEmissionMonitor(
        alert_failure_threshold=3,
        clock=lambda: NOW,
    )
    failure = _result(
        status=GovernanceAuditEmissionStatus.FAILED,
        reason=GovernanceAuditEmissionReason.STORAGE_UNAVAILABLE,
        requested=1,
    )

    with ThreadPoolExecutor(max_workers=8) as executor:
        observations = list(executor.map(monitor.observe, [failure] * 100))
    snapshot = monitor.snapshot()

    assert sum(item.alert_activated for item in observations) == 1
    assert snapshot.status == "alerting"
    assert snapshot.alert_active is True
    assert snapshot.emission_calls_total == 100
    assert snapshot.storage_attempts_total == 100
    assert snapshot.requested_records_total == 100
    assert snapshot.failed_calls_total == 100
    assert snapshot.consecutive_failures == 100
    assert snapshot.alert_transitions_total == 1


def test_emitter_logs_sanitized_alert_and_recovery(caplog) -> None:
    private_error = "private host password and subject"

    def unavailable_session():
        raise RuntimeError(private_error)

    monitor = GovernanceAuditEmissionMonitor(
        alert_failure_threshold=2,
        clock=lambda: NOW,
    )
    failed_emitter = GovernanceAuditEmitter(
        unavailable_session,
        monitor=monitor,
    )
    successful_emitter = GovernanceAuditEmitter(
        make_session_factory(),
        monitor=monitor,
    )
    caplog.set_level(logging.INFO, logger="app.governance.emitter")

    failed_emitter.emit(make_record())
    failed_emitter.emit(make_record())
    successful = successful_emitter.emit(make_record())

    assert successful.status == "persisted"
    assert "event=governance_audit_emission_alert" in caplog.text
    assert "state=active" in caplog.text
    assert "state=recovered" in caplog.text
    assert "threshold=2" in caplog.text
    assert private_error not in caplog.text


def test_monitoring_failure_never_changes_persisted_result(caplog) -> None:
    class UnavailableMonitor:
        def observe(self, result):
            raise RuntimeError("private monitoring endpoint")

    emitter = GovernanceAuditEmitter(
        make_session_factory(),
        monitor=UnavailableMonitor(),
    )

    result = emitter.emit(make_record())

    assert result.status == "persisted"
    assert "governance_audit_monitoring_unavailable" in caplog.text
    assert "private monitoring endpoint" not in caplog.text
