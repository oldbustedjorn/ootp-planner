from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from uuid import UUID, uuid5

from ootp_opt.config import load_config
from ootp_opt.storage.models import BuildMethod, BuildRecord, PresetRecord

IMPORT_NAMESPACE = UUID("ec4b0574-a3f4-4e9a-aa6c-031db4ecda84")
VALID_BUILD_METHODS = {"greedy", "optimizer"}


@dataclass(frozen=True, slots=True)
class ImportIssue:
    severity: Literal["warning", "error"]
    source: str
    identity: str
    message: str


@dataclass(frozen=True, slots=True)
class BuildImportCandidate:
    record: BuildRecord
    html_output: str | None
    snapshot_path: str | None
    html_exists: bool
    snapshot_exists: bool


@dataclass(frozen=True, slots=True)
class ImportPreview:
    config_path: Path
    history_path: Path
    presets: tuple[PresetRecord, ...]
    builds: tuple[BuildImportCandidate, ...]
    issues: tuple[ImportIssue, ...]

    @property
    def error_count(self) -> int:
        return sum(issue.severity == "error" for issue in self.issues)

    @property
    def warning_count(self) -> int:
        return sum(issue.severity == "warning" for issue in self.issues)

    @property
    def snapshots_found(self) -> int:
        return sum(candidate.snapshot_exists for candidate in self.builds)

    @property
    def reports_found(self) -> int:
        return sum(candidate.html_exists for candidate in self.builds)


def preview_existing_state(
    config_path: str | Path = "config.toml",
    history_path: str | Path = "outputs/roster_build_registry.json",
) -> ImportPreview:
    config_path = Path(config_path)
    history_path = Path(history_path)
    issues: list[ImportIssue] = []

    try:
        config = load_config(config_path)
    except (OSError, ValueError) as exc:
        issues.append(
            ImportIssue("error", "config", str(config_path), f"Cannot read config: {exc}")
        )
        config = {}

    presets = _preview_presets(config, issues)
    preset_by_name = {preset.command_name: preset for preset in presets}
    raw_history = _load_history(history_path, issues)
    builds = _preview_builds(raw_history, preset_by_name, issues)

    return ImportPreview(
        config_path=config_path,
        history_path=history_path,
        presets=tuple(presets),
        builds=tuple(builds),
        issues=tuple(issues),
    )


def render_import_preview(preview: ImportPreview, *, details: bool = False) -> str:
    lines = [
        "SQLite import preview (read-only)",
        f"Config: {preview.config_path}",
        f"History: {preview.history_path}",
        "",
        f"Presets ready: {len(preview.presets)}",
        f"Build records ready: {len(preview.builds)}",
        f"Roster reports found: {preview.reports_found}/{len(preview.builds)}",
        f"Roster snapshots found: {preview.snapshots_found}/{len(preview.builds)}",
        f"Warnings: {preview.warning_count}",
        f"Errors: {preview.error_count}",
    ]

    if preview.issues:
        lines.extend(["", "Issues:"])
        lines.extend(
            f"- {issue.severity.upper()} [{issue.source}:{issue.identity}] "
            f"{issue.message}"
            for issue in preview.issues
        )

    if details:
        lines.extend(["", "Presets:"])
        lines.extend(
            f"- {preset.command_name} ({preset.build_method}, {preset.base_profile})"
            for preset in preview.presets
        )
        lines.extend(["", "Builds:"])
        lines.extend(
            f"- {candidate.record.created_at or 'unknown date'} | "
            f"{candidate.record.roster_name} | "
            f"source={candidate.record.source_record_id or 'none'} | "
            f"snapshot={'yes' if candidate.snapshot_exists else 'no'}"
            for candidate in preview.builds
        )

    lines.extend(["", "No database was created or modified."])
    return "\n".join(lines)


def _preview_presets(
    config: dict[str, Any], issues: list[ImportIssue]
) -> list[PresetRecord]:
    raw_presets = config.get("tournament_presets", {})
    if not isinstance(raw_presets, dict):
        issues.append(
            ImportIssue(
                "error",
                "config",
                "tournament_presets",
                "Tournament presets must be a table.",
            )
        )
        return []

    presets: list[PresetRecord] = []
    for command_name, raw_preset in sorted(raw_presets.items()):
        identity = str(command_name)
        if not isinstance(raw_preset, dict):
            issues.append(
                ImportIssue("error", "preset", identity, "Preset must be a table.")
            )
            continue

        base_profile = str(raw_preset.get("base_profile") or "").strip()
        build_method = str(raw_preset.get("build_method") or "greedy")
        if not base_profile:
            issues.append(
                ImportIssue(
                    "error", "preset", identity, "Preset has no base_profile."
                )
            )
            continue
        if build_method not in VALID_BUILD_METHODS:
            issues.append(
                ImportIssue(
                    "error",
                    "preset",
                    identity,
                    f"Unknown build method '{build_method}'.",
                )
            )
            continue

        presets.append(
            PresetRecord(
                id=str(uuid5(IMPORT_NAMESPACE, f"preset:{identity}")),
                command_name=identity,
                display_title=_optional_text(raw_preset.get("_gui_title")),
                note=_optional_text(raw_preset.get("_gui_note")),
                base_profile=base_profile,
                build_method=_build_method(build_method),
                rules=dict(raw_preset),
                source="config.toml",
            )
        )
    return presets


def _load_history(
    history_path: Path, issues: list[ImportIssue]
) -> list[Any]:
    if not history_path.exists():
        issues.append(
            ImportIssue(
                "warning",
                "history",
                str(history_path),
                "History registry does not exist; there are no builds to import.",
            )
        )
        return []

    try:
        raw_history = json.loads(history_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        issues.append(
            ImportIssue(
                "error",
                "history",
                str(history_path),
                f"Cannot read history registry: {exc}",
            )
        )
        return []

    if not isinstance(raw_history, list):
        issues.append(
            ImportIssue(
                "error",
                "history",
                str(history_path),
                "History registry must contain a JSON list.",
            )
        )
        return []
    return raw_history


def _preview_builds(
    raw_history: list[Any],
    preset_by_name: dict[str, PresetRecord],
    issues: list[ImportIssue],
) -> list[BuildImportCandidate]:
    source_ids = [
        str(raw.get("id"))
        for raw in raw_history
        if isinstance(raw, dict) and raw.get("id")
    ]
    for source_id, count in sorted(Counter(source_ids).items()):
        if count > 1:
            issues.append(
                ImportIssue(
                    "warning",
                    "history",
                    source_id,
                    f"Legacy ID occurs {count} times; each rebuild will receive "
                    "a unique database ID.",
                )
            )

    fingerprint_occurrences: Counter[str] = Counter()
    builds: list[BuildImportCandidate] = []
    for index, raw_build in enumerate(raw_history):
        identity = f"row-{index + 1}"
        if not isinstance(raw_build, dict):
            issues.append(
                ImportIssue("error", "history", identity, "Build must be an object.")
            )
            continue

        source_record_id = _optional_text(raw_build.get("id"))
        identity = source_record_id or identity
        roster_name = str(raw_build.get("roster_name") or "").strip()
        build_type = str(raw_build.get("build_type") or "").strip()
        build_method = str(raw_build.get("build_method") or "greedy")
        status = str(raw_build.get("status") or "unknown").strip()
        if not roster_name or not build_type:
            issues.append(
                ImportIssue(
                    "error",
                    "history",
                    identity,
                    "Build requires roster_name and build_type.",
                )
            )
            continue
        if build_method not in VALID_BUILD_METHODS:
            issues.append(
                ImportIssue(
                    "error",
                    "history",
                    identity,
                    f"Unknown build method '{build_method}'.",
                )
            )
            continue

        preset_name = _optional_text(raw_build.get("preset_name"))
        preset = preset_by_name.get(preset_name or "")
        if preset_name and preset is None:
            issues.append(
                ImportIssue(
                    "warning",
                    "history",
                    identity,
                    f"Referenced preset '{preset_name}' is no longer configured.",
                )
            )

        fingerprint = _fingerprint(raw_build)
        occurrence = fingerprint_occurrences[fingerprint]
        fingerprint_occurrences[fingerprint] += 1
        database_id = str(
            uuid5(IMPORT_NAMESPACE, f"build:{fingerprint}:{occurrence}")
        )
        overrides = raw_build.get("overrides")
        if not isinstance(overrides, dict):
            overrides = {}
        request = {
            "base_profile": raw_build.get("base_profile"),
            "preset_name": preset_name,
            "overrides": overrides,
        }
        ruleset = dict(preset.rules) if preset else {
            "base_profile": raw_build.get("base_profile"),
            **overrides,
        }
        html_output = _optional_text(raw_build.get("html_output"))
        snapshot_path = _optional_text(raw_build.get("snapshot_path"))

        builds.append(
            BuildImportCandidate(
                record=BuildRecord(
                    id=database_id,
                    source_record_id=source_record_id,
                    build_number=_optional_int(raw_build.get("build_number")),
                    preset_id=preset.id if preset else None,
                    roster_name=roster_name,
                    build_type=build_type,
                    build_method=_build_method(build_method),
                    status=status,
                    model_version="legacy-unversioned",
                    request=request,
                    ruleset=ruleset,
                    source_fingerprint=fingerprint,
                    created_at=_optional_text(raw_build.get("created_at")),
                ),
                html_output=html_output,
                snapshot_path=snapshot_path,
                html_exists=bool(html_output and Path(html_output).is_file()),
                snapshot_exists=bool(snapshot_path and Path(snapshot_path).is_file()),
            )
        )
    return builds


def _fingerprint(value: dict[str, Any]) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), default=str
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _build_method(value: str) -> BuildMethod:
    if value == "optimizer":
        return "optimizer"
    return "greedy"


def _optional_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _optional_int(value: Any) -> int | None:
    return int(value) if str(value or "").isdigit() else None
