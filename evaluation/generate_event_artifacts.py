"""Generate deterministic V3 event artifacts for CI and local review."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Sequence

from evaluation.shopmind_event_reporting import (
    build_event_health_report,
    format_event_metrics,
    summarize_debug_events,
    write_event_artifacts,
)


DEFAULT_OUTPUT_DIR = Path("artifacts/v3-events")


def sample_event_outputs() -> list[dict[str, Any]]:
    """Return stable V3 debug event samples that do not require DB or LLM access."""

    return [
        {
            "debug": {
                "write_handoff_debug": {
                    "candidate_context": {
                        "events": [{"event": "candidate_context_stored"}]
                    }
                }
            }
        },
        {
            "debug": {
                "confirmation": {
                    "events": [{"event": "pending_action_confirmed"}]
                }
            }
        },
    ]


def generate_sample_event_artifacts(
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
) -> dict[str, str]:
    """Generate event artifacts from deterministic sample outputs."""

    summary = summarize_debug_events(sample_event_outputs())
    report = build_event_health_report(
        summary,
        title="ShopMind V3 sample event health",
        required_groups=("candidate_context", "confirmation"),
        required_events=("candidate_context_stored", "pending_action_confirmed"),
        min_output_event_rate=1.0,
    )
    return write_event_artifacts(
        summary,
        output_dir,
        report=report,
        metrics_text=format_event_metrics(summary),
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate deterministic V3 event artifacts."
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Directory where event artifacts should be written.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    paths = generate_sample_event_artifacts(args.output_dir)
    print("event artifacts:")
    for name, path in paths.items():
        print(f"- {name}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
