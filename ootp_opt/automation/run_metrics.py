from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from html import escape
import json
from pathlib import Path
import re
from typing import Any


METRIC_STAGES = (
    "setup",
    "plan",
    "sync",
    "rotation",
    "bullpen",
    "vs_rhp",
    "vs_lhp",
    "save",
)
METRIC_EVENTS = ("start", "complete")
MARKER_PATTERN = re.compile(
    r"OOTP_METRIC run=(?P<run_id>[A-Za-z0-9_.-]+) "
    r"stage=(?P<stage>[a-z_]+) event=(?P<event>[a-z]+) "
    r"at=(?P<timestamp>[0-9TZ:.+\-]+)"
)


@dataclass(frozen=True)
class MetricMarker:
    run_id: str
    stage: str
    event: str
    timestamp: datetime


@dataclass(frozen=True)
class StageMetric:
    stage: str
    wall_seconds: float
    input_tokens: int
    cached_input_tokens: int
    uncached_input_tokens: int
    output_tokens: int
    reasoning_output_tokens: int
    total_tokens: int
    model_responses: int
    tool_calls: int
    images: int


def metric_marker(
    run_id: str,
    stage: str,
    event: str,
    *,
    now: datetime | None = None,
) -> str:
    normalized_run_id = run_id.strip()
    if not normalized_run_id or not re.fullmatch(r"[A-Za-z0-9_.-]+", normalized_run_id):
        raise ValueError("Metric run ID must contain only letters, numbers, dot, dash, or underscore")
    if stage not in METRIC_STAGES:
        raise ValueError(f"Unknown metric stage: {stage}")
    if event not in METRIC_EVENTS:
        raise ValueError(f"Unknown metric event: {event}")
    timestamp = now or datetime.now(timezone.utc)
    return (
        f"OOTP_METRIC run={normalized_run_id} stage={stage} event={event} "
        f"at={timestamp.isoformat()}"
    )


def load_session_rows(path: str | Path) -> list[dict[str, Any]]:
    rows = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def extract_markers(rows: list[dict[str, Any]]) -> list[MetricMarker]:
    markers: list[MetricMarker] = []
    seen: set[tuple[str, str, str, str]] = set()
    for row in rows:
        if row.get("type") != "response_item":
            continue
        serialized = json.dumps(row.get("payload", {}), ensure_ascii=True)
        for match in MARKER_PATTERN.finditer(serialized):
            key = (
                match["run_id"],
                match["stage"],
                match["event"],
                match["timestamp"],
            )
            if key in seen:
                continue
            seen.add(key)
            markers.append(
                MetricMarker(
                    run_id=match["run_id"],
                    stage=match["stage"],
                    event=match["event"],
                    timestamp=parse_timestamp(match["timestamp"]),
                )
            )
    return sorted(markers, key=lambda marker: marker.timestamp)


def completed_intervals(
    markers: list[MetricMarker],
) -> list[tuple[str, datetime, datetime]]:
    active: dict[str, datetime] = {}
    intervals: list[tuple[str, datetime, datetime]] = []
    for marker in markers:
        if marker.event == "start":
            active[marker.stage] = marker.timestamp
        elif marker.stage in active:
            started = active.pop(marker.stage)
            if marker.timestamp >= started:
                intervals.append((marker.stage, started, marker.timestamp))
    return intervals


def analyze_session(path: str | Path, run_id: str | None = None) -> list[StageMetric]:
    rows = load_session_rows(path)
    markers = extract_markers(rows)
    selected_run_id = run_id or (markers[-1].run_id if markers else None)
    if selected_run_id is None:
        return []
    markers = [marker for marker in markers if marker.run_id == selected_run_id]
    latest_setup = next(
        (
            marker.timestamp
            for marker in reversed(markers)
            if marker.stage == "setup" and marker.event == "start"
        ),
        None,
    )
    if latest_setup is not None:
        markers = [marker for marker in markers if marker.timestamp >= latest_setup]
    intervals = completed_intervals(markers)
    grouped: dict[str, list[tuple[datetime, datetime]]] = {}
    for stage, started, completed in intervals:
        grouped.setdefault(stage, []).append((started, completed))

    metrics = []
    for stage in METRIC_STAGES:
        stage_intervals = grouped.get(stage, [])
        if not stage_intervals:
            continue
        selected = [
            row
            for row in rows
            if any(
                started <= row_timestamp(row) <= completed
                for started, completed in stage_intervals
            )
        ]
        usage_rows = [
            row for row in selected if row.get("type") == "token_usage_record"
        ]
        usage = {
            "input_tokens": 0,
            "cached_input_tokens": 0,
            "output_tokens": 0,
            "reasoning_output_tokens": 0,
            "total_tokens": 0,
        }
        for row in usage_rows:
            record = row.get("payload", {}).get("usage", {})
            for key in usage:
                usage[key] += int(record.get(key, 0) or 0)

        response_items = [
            row for row in selected if row.get("type") == "response_item"
        ]
        tool_calls = sum(
            row.get("payload", {}).get("type")
            in {"custom_tool_call", "function_call"}
            for row in response_items
        )
        images = 0
        for row in response_items:
            output = row.get("payload", {}).get("output", [])
            if isinstance(output, list):
                images += sum(
                    isinstance(item, dict) and item.get("type") == "input_image"
                    for item in output
                )
        metrics.append(
            StageMetric(
                stage=stage,
                wall_seconds=sum(
                    (completed - started).total_seconds()
                    for started, completed in stage_intervals
                ),
                input_tokens=usage["input_tokens"],
                cached_input_tokens=usage["cached_input_tokens"],
                uncached_input_tokens=(
                    usage["input_tokens"] - usage["cached_input_tokens"]
                ),
                output_tokens=usage["output_tokens"],
                reasoning_output_tokens=usage["reasoning_output_tokens"],
                total_tokens=usage["total_tokens"],
                model_responses=len(usage_rows),
                tool_calls=tool_calls,
                images=images,
            )
        )
    return metrics


def latest_metric_session(
    root: str | Path | None = None,
    run_id: str | None = None,
) -> Path:
    session_root = Path(root or Path.home() / ".codex" / "sessions")
    candidates = sorted(
        session_root.rglob("*.jsonl"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    matches: list[tuple[int, int, float, Path]] = []
    for path in candidates[:200]:
        if not is_primary_session(path):
            continue
        contents = path.read_text(encoding="utf-8", errors="ignore")
        marker = f"OOTP_METRIC run={run_id} " if run_id else "OOTP_METRIC run="
        if marker in contents:
            markers = extract_markers(load_session_rows(path))
            if run_id:
                markers = [item for item in markers if item.run_id == run_id]
            matches.append(
                (
                    len(completed_intervals(markers)),
                    len(markers),
                    path.stat().st_mtime,
                    path,
                )
            )
    if matches:
        return max(matches, key=lambda item: item[:3])[3]
    raise FileNotFoundError("No Codex session containing OOTP metric markers was found")


def is_primary_session(path: str | Path) -> bool:
    with Path(path).open(encoding="utf-8", errors="ignore") as stream:
        for line in stream:
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("type") != "session_meta":
                continue
            payload = row.get("payload", {})
            source = payload.get("source")
            return (
                payload.get("thread_source") != "guardian_review"
                and not (isinstance(source, dict) and source.get("subagent"))
            )
    return False


def write_metrics_json(path: str | Path, metrics: list[StageMetric]) -> str:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps([asdict(metric) for metric in metrics], indent=2) + "\n",
        encoding="utf-8",
    )
    return str(destination)


def write_metrics_html(
    path: str | Path,
    metrics: list[StageMetric],
    *,
    session_path: str | Path,
) -> str:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    total_seconds = sum(metric.wall_seconds for metric in metrics)
    total_tokens = sum(metric.total_tokens for metric in metrics)
    rows = []
    for metric in metrics:
        time_share = metric.wall_seconds / total_seconds * 100 if total_seconds else 0
        token_share = metric.total_tokens / total_tokens * 100 if total_tokens else 0
        rows.append(
            "<tr>"
            f"<td>{escape(metric.stage)}</td>"
            f"<td data-sort='{metric.wall_seconds}'>{format_seconds(metric.wall_seconds)}</td>"
            f"<td>{time_share:.1f}%</td>"
            f"<td>{metric.total_tokens:,}</td>"
            f"<td>{token_share:.1f}%</td>"
            f"<td>{metric.cached_input_tokens:,}</td>"
            f"<td>{metric.uncached_input_tokens:,}</td>"
            f"<td>{metric.output_tokens:,}</td>"
            f"<td>{metric.model_responses}</td>"
            f"<td>{metric.tool_calls}</td>"
            f"<td>{metric.images}</td>"
            "</tr>"
        )
    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>OOTP Automation Metrics</title>
<style>
body {{ font: 14px system-ui, sans-serif; margin: 24px; color: #172033; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ border-bottom: 1px solid #d5dae3; padding: 8px; text-align: right; }}
th:first-child, td:first-child {{ text-align: left; }}
th {{ background: #eef2f7; position: sticky; top: 0; }}
.meta {{ color: #596579; margin-bottom: 18px; }}
</style></head><body>
<h1>OOTP automation metrics</h1>
<p class="meta">Session: {escape(str(session_path))}</p>
<table><thead><tr><th>Stage</th><th>Time</th><th>Time share</th>
<th>Total tokens</th><th>Token share</th><th>Cached input</th>
<th>Uncached input</th><th>Output</th><th>Model responses</th>
<th>Tool calls</th><th>Images</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table>
</body></html>"""
    destination.write_text(html, encoding="utf-8")
    return str(destination)


def format_metrics_summary(metrics: list[StageMetric]) -> str:
    if not metrics:
        return "No completed metric stages found."
    total_seconds = sum(metric.wall_seconds for metric in metrics)
    total_tokens = sum(metric.total_tokens for metric in metrics)
    lines = [
        "stage\ttime\ttime%\ttokens\ttoken%\tuncached\tcalls\timages"
    ]
    for metric in metrics:
        lines.append(
            "\t".join(
                [
                    metric.stage,
                    format_seconds(metric.wall_seconds),
                    f"{metric.wall_seconds / total_seconds * 100 if total_seconds else 0:.1f}",
                    str(metric.total_tokens),
                    f"{metric.total_tokens / total_tokens * 100 if total_tokens else 0:.1f}",
                    str(metric.uncached_input_tokens),
                    str(metric.tool_calls),
                    str(metric.images),
                ]
            )
        )
    return "\n".join(lines)


def parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def row_timestamp(row: dict[str, Any]) -> datetime:
    return parse_timestamp(row["timestamp"])


def format_seconds(seconds: float) -> str:
    minutes, remaining = divmod(round(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours:d}:{minutes:02d}:{remaining:02d}"
    return f"{minutes:d}:{remaining:02d}"
