from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

from ootp_opt.automation.run_metrics import (
    analyze_session,
    extract_markers,
    format_metrics_summary,
    load_session_rows,
    latest_metric_session,
    metric_marker,
    write_metrics_html,
    write_metrics_json,
)


def row(timestamp: str, type_: str, payload: dict) -> dict:
    return {"timestamp": timestamp, "type": type_, "payload": payload}


def test_metric_marker_is_machine_readable() -> None:
    marker = metric_marker(
        "1140208-20261007T123000Z",
        "bullpen",
        "start",
        now=datetime(2026, 10, 7, 12, 30, tzinfo=timezone.utc),
    )

    assert marker == (
        "OOTP_METRIC run=1140208-20261007T123000Z stage=bullpen event=start "
        "at=2026-10-07T12:30:00+00:00"
    )

    with pytest.raises(ValueError, match="Metric run ID"):
        metric_marker("bad run id", "bullpen", "start")


def test_analyze_session_attributes_usage_and_actions_to_stage(tmp_path: Path) -> None:
    session = tmp_path / "session.jsonl"
    rows = [
        row(
            "2026-10-07T12:00:00Z",
            "response_item",
            {
                "type": "custom_tool_call_output",
                "output": [
                    {
                        "type": "input_text",
                        "text": (
                            "OOTP_METRIC run=test-run stage=sync event=start "
                            "at=2026-10-07T12:00:00+00:00"
                        ),
                    }
                ],
            },
        ),
        row(
            "2026-10-07T12:00:30Z",
            "response_item",
            {"type": "custom_tool_call", "name": "exec", "input": "sync cards"},
        ),
        row(
            "2026-10-07T12:00:31Z",
            "response_item",
            {
                "type": "custom_tool_call_output",
                "output": [{"type": "input_image", "image_url": "data:image/png"}],
            },
        ),
        row(
            "2026-10-07T12:00:32Z",
            "token_usage_record",
            {
                "usage": {
                    "input_tokens": 1000,
                    "cached_input_tokens": 800,
                    "output_tokens": 50,
                    "reasoning_output_tokens": 10,
                    "total_tokens": 1050,
                }
            },
        ),
        row(
            "2026-10-07T12:02:00Z",
            "response_item",
            {
                "type": "custom_tool_call_output",
                "output": [
                    {
                        "type": "input_text",
                        "text": (
                            "OOTP_METRIC run=test-run stage=sync event=complete "
                            "at=2026-10-07T12:02:00+00:00"
                        ),
                    }
                ],
            },
        ),
    ]
    session.write_text(
        "\n".join(json.dumps(item) for item in rows) + "\n", encoding="utf-8"
    )

    metrics = analyze_session(session)

    assert len(metrics) == 1
    metric = metrics[0]
    assert metric.stage == "sync"
    assert metric.wall_seconds == 120
    assert metric.total_tokens == 1050
    assert metric.cached_input_tokens == 800
    assert metric.uncached_input_tokens == 200
    assert metric.output_tokens == 50
    assert metric.model_responses == 1
    assert metric.tool_calls == 1
    assert metric.images == 1
    assert "sync\t2:00\t100.0\t1050" in format_metrics_summary(metrics)

    html_path = tmp_path / "metrics.html"
    json_path = tmp_path / "metrics.json"
    write_metrics_html(html_path, metrics, session_path=session)
    write_metrics_json(json_path, metrics)
    assert "OOTP automation metrics" in html_path.read_text(encoding="utf-8")
    assert json.loads(json_path.read_text(encoding="utf-8"))[0]["stage"] == "sync"


def test_extract_markers_uses_latest_start_after_interruption() -> None:
    rows = [
        row(
            "2026-10-07T12:00:00Z",
            "response_item",
            {
                "type": "custom_tool_call_output",
                "output": [
                    {
                        "type": "input_text",
                        "text": (
                            "OOTP_METRIC run=test-run stage=plan event=start "
                            "at=2026-10-07T12:00:00+00:00"
                        ),
                    }
                ],
            },
        ),
        row(
            "2026-10-07T13:00:00Z",
            "response_item",
            {
                "type": "custom_tool_call_output",
                "output": [
                    {
                        "type": "input_text",
                        "text": (
                            "OOTP_METRIC run=test-run stage=plan event=start "
                            "at=2026-10-07T13:00:00+00:00"
                        ),
                    }
                ],
            },
        ),
    ]

    markers = extract_markers(rows)

    assert [marker.event for marker in markers] == ["start", "start"]


def test_load_session_rows_ignores_blank_lines(tmp_path: Path) -> None:
    path = tmp_path / "session.jsonl"
    path.write_text('\n{"timestamp":"2026-10-07T12:00:00Z"}\n', encoding="utf-8")

    assert load_session_rows(path) == [{"timestamp": "2026-10-07T12:00:00Z"}]


def test_latest_metric_session_ignores_subagent_echoes(tmp_path: Path) -> None:
    primary = tmp_path / "primary.jsonl"
    reviewer = tmp_path / "reviewer.jsonl"
    marker = "OOTP_METRIC run=target-run stage=setup event=start at=2026-10-07T12:00:00Z"
    primary.write_text(
        json.dumps(
            {
                "type": "session_meta",
                "payload": {"thread_source": "user", "source": "vscode"},
            }
        )
        + "\n"
        + json.dumps({"type": "response_item", "payload": {"text": marker}})
        + "\n",
        encoding="utf-8",
    )
    reviewer.write_text(
        json.dumps(
            {
                "type": "session_meta",
                "payload": {
                    "thread_source": "guardian_review",
                    "source": {"subagent": {"other": "guardian"}},
                    "parent_thread_id": "parent",
                },
            }
        )
        + "\n"
        + json.dumps({"type": "response_item", "payload": {"text": marker}})
        + "\n",
        encoding="utf-8",
    )
    reviewer.touch()

    assert latest_metric_session(tmp_path, "target-run") == primary


def test_latest_metric_session_prefers_most_complete_primary_run(tmp_path: Path) -> None:
    complete = tmp_path / "complete.jsonl"
    partial = tmp_path / "partial.jsonl"
    metadata = {
        "type": "session_meta",
        "payload": {"thread_source": "user", "source": "vscode"},
    }
    complete_markers = [
        "OOTP_METRIC run=target-run stage=setup event=start at=2026-10-07T12:00:00Z",
        "OOTP_METRIC run=target-run stage=setup event=complete at=2026-10-07T12:01:00Z",
        "OOTP_METRIC run=target-run stage=plan event=start at=2026-10-07T12:01:00Z",
        "OOTP_METRIC run=target-run stage=plan event=complete at=2026-10-07T12:02:00Z",
    ]
    partial_markers = [
        "OOTP_METRIC run=target-run stage=save event=start at=2026-10-07T13:00:00Z",
        "OOTP_METRIC run=target-run stage=save event=complete at=2026-10-07T13:01:00Z",
    ]
    complete.write_text(
        "\n".join(
            json.dumps(item)
            for item in [
                metadata,
                *[
                    {"type": "response_item", "payload": {"text": marker}}
                    for marker in complete_markers
                ],
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    partial.write_text(
        "\n".join(
            json.dumps(item)
            for item in [
                metadata,
                *[
                    {"type": "response_item", "payload": {"text": marker}}
                    for marker in partial_markers
                ],
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    partial.touch()

    assert latest_metric_session(tmp_path, "target-run") == complete


def test_analyzer_uses_latest_setup_for_repeated_run_id(tmp_path: Path) -> None:
    session = tmp_path / "repeated.jsonl"
    rows = []
    for hour, tokens in ((10, 100), (12, 200)):
        for minute, event in ((0, "start"), (2, "complete")):
            timestamp = f"2026-10-07T{hour:02d}:{minute:02d}:00Z"
            rows.append(
                row(
                    timestamp,
                    "response_item",
                    {
                        "type": "custom_tool_call_output",
                        "output": [
                            {
                                "type": "input_text",
                                "text": (
                                    f"OOTP_METRIC run=same-run stage=setup event={event} "
                                    f"at={timestamp}"
                                ),
                            }
                        ],
                    },
                )
            )
        rows.append(
            row(
                f"2026-10-07T{hour:02d}:01:00Z",
                "token_usage_record",
                {
                    "usage": {
                        "input_tokens": tokens,
                        "cached_input_tokens": 0,
                        "output_tokens": 0,
                        "reasoning_output_tokens": 0,
                        "total_tokens": tokens,
                    }
                },
            )
        )
    session.write_text(
        "\n".join(json.dumps(item) for item in rows) + "\n", encoding="utf-8"
    )

    metrics = analyze_session(session, "same-run")

    assert len(metrics) == 1
    assert metrics[0].total_tokens == 200
