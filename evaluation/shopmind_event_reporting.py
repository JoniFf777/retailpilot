"""Aggregate V3 debug events from ShopMind API/evaluation outputs."""

from __future__ import annotations

from collections import Counter
from typing import Any, Iterable, TypedDict


CANDIDATE_CONTEXT_EVENTS = {
    "candidate_context_stored",
    "candidate_context_skipped",
    "candidate_context_missed",
    "candidate_context_selected",
    "candidate_context_out_of_range",
    "candidate_context_cleared",
}
CONFIRMATION_EVENTS = {
    "pending_action_confirmed",
    "pending_action_cancelled",
    "pending_action_failed",
}
EVENT_GROUP_BY_NAME = {
    **{event: "candidate_context" for event in CANDIDATE_CONTEXT_EVENTS},
    **{event: "confirmation" for event in CONFIRMATION_EVENTS},
}


class EventRecord(TypedDict):
    event: str
    group: str
    source: str
    metadata: dict[str, Any]


class EventSummary(TypedDict):
    total_outputs: int
    outputs_with_events: int
    output_event_rate: float
    total_events: int
    event_counts: dict[str, int]
    group_counts: dict[str, int]
    event_rates: dict[str, float]
    group_rates: dict[str, float]


class EventMetricRow(TypedDict):
    name: str
    labels: dict[str, str]
    value: float


class EventHealthCheck(TypedDict):
    name: str
    passed: bool
    actual: str
    expected: str


class EventHealthReport(TypedDict):
    title: str
    status: str
    checks: list[EventHealthCheck]
    summary: EventSummary


def _as_mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _events_from_container(
    container: dict[str, Any],
    *,
    group: str,
    source: str,
) -> list[EventRecord]:
    group_payload = _as_mapping(container.get(group))
    raw_events = group_payload.get("events")
    if not isinstance(raw_events, list):
        return []

    records: list[EventRecord] = []
    for raw_event in raw_events:
        event_payload = _as_mapping(raw_event)
        event_name = event_payload.get("event")
        if not isinstance(event_name, str):
            continue
        records.append(
            {
                "event": event_name,
                "group": EVENT_GROUP_BY_NAME.get(event_name, group),
                "source": source,
                "metadata": {
                    key: value
                    for key, value in event_payload.items()
                    if key not in {"event", "index"}
                },
            }
        )
    return records


def extract_debug_events(output: dict[str, Any]) -> list[EventRecord]:
    """Extract known V3 debug events from an API or evaluator output."""

    debug = _as_mapping(output.get("debug"))
    records: list[EventRecord] = []
    records.extend(
        _events_from_container(
            debug,
            group="candidate_context",
            source="debug.candidate_context",
        )
    )
    records.extend(
        _events_from_container(
            _as_mapping(debug.get("write_handoff_debug")),
            group="candidate_context",
            source="debug.write_handoff_debug.candidate_context",
        )
    )
    records.extend(
        _events_from_container(
            debug,
            group="confirmation",
            source="debug.confirmation",
        )
    )
    return records


def summarize_debug_events(outputs: Iterable[dict[str, Any]]) -> EventSummary:
    """Return count and per-output rate metrics for known V3 debug events."""

    output_list = list(outputs)
    event_counter: Counter[str] = Counter()
    group_counter: Counter[str] = Counter()
    outputs_with_events = 0

    for output in output_list:
        events = extract_debug_events(output)
        if events:
            outputs_with_events += 1
        for event in events:
            event_counter[event["event"]] += 1
            group_counter[event["group"]] += 1

    total_outputs = len(output_list)
    total_events = sum(event_counter.values())
    return {
        "total_outputs": total_outputs,
        "outputs_with_events": outputs_with_events,
        "output_event_rate": (
            outputs_with_events / total_outputs if total_outputs else 0.0
        ),
        "total_events": total_events,
        "event_counts": dict(sorted(event_counter.items())),
        "group_counts": dict(sorted(group_counter.items())),
        "event_rates": {
            event: count / total_outputs if total_outputs else 0.0
            for event, count in sorted(event_counter.items())
        },
        "group_rates": {
            group: count / total_outputs if total_outputs else 0.0
            for group, count in sorted(group_counter.items())
        },
    }


def format_event_summary(summary: EventSummary) -> str:
    lines = [
        "V3 debug event summary",
        f"outputs: {summary['total_outputs']}",
        (
            "outputs with events: "
            f"{summary['outputs_with_events']}/{summary['total_outputs']} "
            f"({summary['output_event_rate'] * 100:.1f}%)"
        ),
        f"events: {summary['total_events']}",
    ]
    if not summary["event_counts"]:
        lines.append("event counts: none")
        return "\n".join(lines)

    lines.append("group counts:")
    for group, count in summary["group_counts"].items():
        lines.append(f"- {group}: {count}")
    lines.append("event counts:")
    for event, count in summary["event_counts"].items():
        lines.append(f"- {event}: {count}")
    return "\n".join(lines)


def event_summary_metric_rows(
    summary: EventSummary,
    *,
    prefix: str = "shopmind_v3_debug",
) -> list[EventMetricRow]:
    """Flatten an event summary into operational metric rows."""

    rows: list[EventMetricRow] = []

    def add(
        name: str,
        value: int | float,
        labels: dict[str, str] | None = None,
    ) -> None:
        rows.append(
            {
                "name": name,
                "labels": labels or {},
                "value": float(value),
            }
        )

    add(f"{prefix}_outputs_total", summary["total_outputs"])
    add(f"{prefix}_outputs_with_events_total", summary["outputs_with_events"])
    add(f"{prefix}_output_event_rate", summary["output_event_rate"])
    add(f"{prefix}_events_total", summary["total_events"])

    for group, count in summary["group_counts"].items():
        add(f"{prefix}_group_events_total", count, {"group": group})
    for event, count in summary["event_counts"].items():
        add(
            f"{prefix}_events_by_name_total",
            count,
            {
                "event": event,
                "group": EVENT_GROUP_BY_NAME.get(event, "unknown"),
            },
        )
    for group, rate in summary["group_rates"].items():
        add(f"{prefix}_group_events_per_output", rate, {"group": group})
    for event, rate in summary["event_rates"].items():
        add(
            f"{prefix}_events_per_output",
            rate,
            {
                "event": event,
                "group": EVENT_GROUP_BY_NAME.get(event, "unknown"),
            },
        )
    return rows


def _format_metric_labels(labels: dict[str, str]) -> str:
    if not labels:
        return ""
    formatted = []
    for key, value in sorted(labels.items()):
        escaped = (
            value.replace("\\", "\\\\")
            .replace("\n", "\\n")
            .replace('"', '\\"')
        )
        formatted.append(f'{key}="{escaped}"')
    return "{" + ",".join(formatted) + "}"


def _format_metric_value(value: float) -> str:
    return str(int(value)) if value.is_integer() else str(value)


def format_event_metrics(
    summary: EventSummary,
    *,
    prefix: str = "shopmind_v3_debug",
) -> str:
    """Format event summary rows as Prometheus-style text samples."""

    rows = event_summary_metric_rows(summary, prefix=prefix)
    return "\n".join(
        (
            f"{row['name']}{_format_metric_labels(row['labels'])} "
            f"{_format_metric_value(row['value'])}"
        )
        for row in rows
    )


def build_event_health_report(
    summary: EventSummary,
    *,
    title: str = "ShopMind V3 event health",
    required_events: tuple[str, ...] = (),
    required_groups: tuple[str, ...] = (),
    min_output_event_rate: float = 0.0,
) -> EventHealthReport:
    """Build a compact health report from event counters and rates."""

    checks: list[EventHealthCheck] = [
        {
            "name": "outputs_present",
            "passed": summary["total_outputs"] > 0,
            "actual": str(summary["total_outputs"]),
            "expected": "> 0",
        },
        {
            "name": "output_event_rate",
            "passed": summary["output_event_rate"] >= min_output_event_rate,
            "actual": f"{summary['output_event_rate']:.3f}",
            "expected": f">= {min_output_event_rate:.3f}",
        },
    ]

    for group in required_groups:
        count = summary["group_counts"].get(group, 0)
        checks.append(
            {
                "name": f"group:{group}",
                "passed": count > 0,
                "actual": str(count),
                "expected": "> 0",
            }
        )
    for event in required_events:
        count = summary["event_counts"].get(event, 0)
        checks.append(
            {
                "name": f"event:{event}",
                "passed": count > 0,
                "actual": str(count),
                "expected": "> 0",
            }
        )

    return {
        "title": title,
        "status": "pass" if all(check["passed"] for check in checks) else "warn",
        "checks": checks,
        "summary": summary,
    }


def format_event_health_report(report: EventHealthReport) -> str:
    """Format a health report for local review or CI artifacts."""

    lines = [
        report["title"],
        f"status: {report['status']}",
        "checks:",
    ]
    for check in report["checks"]:
        result = "pass" if check["passed"] else "warn"
        lines.append(
            "- "
            f"{check['name']}: {result} "
            f"(actual={check['actual']} expected={check['expected']})"
        )

    summary = report["summary"]
    lines.extend(
        [
            "summary:",
            f"- outputs: {summary['total_outputs']}",
            f"- outputs_with_events: {summary['outputs_with_events']}",
            f"- output_event_rate: {summary['output_event_rate']:.3f}",
            f"- events: {summary['total_events']}",
        ]
    )
    if summary["group_counts"]:
        lines.append("- groups:")
        for group, count in summary["group_counts"].items():
            lines.append(f"  {group}: {count}")
    if summary["event_counts"]:
        lines.append("- events_by_name:")
        for event, count in summary["event_counts"].items():
            lines.append(f"  {event}: {count}")
    return "\n".join(lines)


__all__ = [
    "CANDIDATE_CONTEXT_EVENTS",
    "CONFIRMATION_EVENTS",
    "EventHealthCheck",
    "EventHealthReport",
    "EventMetricRow",
    "EventRecord",
    "EventSummary",
    "build_event_health_report",
    "event_summary_metric_rows",
    "extract_debug_events",
    "format_event_health_report",
    "format_event_metrics",
    "format_event_summary",
    "summarize_debug_events",
]
