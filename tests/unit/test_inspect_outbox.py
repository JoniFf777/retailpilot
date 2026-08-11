"""CLI contract tests for the read-only Outbox inspection command."""

import json

import scripts.inspect_outbox as inspect_outbox


class _Session:
    def close(self) -> None:
        pass

    def rollback(self) -> None:
        pass


def test_inspect_outbox_json_is_bounded_and_payload_free(monkeypatch, capsys) -> None:
    monkeypatch.setattr(inspect_outbox, "SessionLocal", _Session)
    monkeypatch.setattr(
        inspect_outbox,
        "get_outbox_operational_snapshot",
        lambda _session, recent_limit: {
            "pending": 1,
            "publishing": 2,
            "published": 3,
            "dead_letter": 1,
            "oldest_pending_seconds": 8.0,
            "oldest_publishing_lease_expiry": None,
            "recent_dead_letters": [{"event_id": "event-1", "last_error": "safe"}],
            "recent_publish_failures": [],
        },
    )
    monkeypatch.setattr("sys.argv", ["inspect_outbox.py", "--json", "--limit", "99"])

    assert inspect_outbox.main() == 0
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "ok"
    assert report["pending"] == 1
    assert len(report["recent_dead_letters"]) == 1
    assert "payload" not in report


def test_inspect_outbox_failure_is_safe(monkeypatch, capsys) -> None:
    monkeypatch.setattr(inspect_outbox, "SessionLocal", _Session)
    monkeypatch.setattr(
        inspect_outbox,
        "get_outbox_operational_snapshot",
        lambda _session, recent_limit: (_ for _ in ()).throw(
            RuntimeError("request_hash=private-value")
        ),
    )
    monkeypatch.setattr("sys.argv", ["inspect_outbox.py", "--json"])

    assert inspect_outbox.main() == 1
    report = json.loads(capsys.readouterr().out)
    assert report["error_code"] == "outbox_inspection_failed"
    assert "private-value" not in report["error_message"]
