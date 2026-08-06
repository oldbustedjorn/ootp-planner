from __future__ import annotations

import hashlib
import json
import re
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from ootp_opt.config import load_config
from ootp_opt.services.preset_service import (
    preset_roster_output_path,
    preset_upgrade_output_path,
)
from ootp_opt.roster.roster_snapshot import snapshot_path_for_html

SUCCESS_STATUSES = {"complete", "success"}


class CleanupError(RuntimeError):
    """Raised when legacy history cannot be cleaned without risking data loss."""


@dataclass(frozen=True, slots=True)
class CleanupIssue:
    severity: Literal["warning", "error"]
    identity: str
    message: str


@dataclass(frozen=True, slots=True)
class PresetRetention:
    preset_name: str
    history_index: int
    source_record_id: str | None
    roster_name: str
    created_at: str | None


@dataclass(frozen=True, slots=True)
class CleanupPlan:
    config_path: Path
    history_path: Path
    project_root: Path
    output_dir: Path
    config_fingerprint: str
    history_fingerprint: str
    original_records: tuple[dict[str, Any], ...]
    retained_records: tuple[dict[str, Any], ...]
    retentions: tuple[PresetRetention, ...]
    delete_paths: tuple[Path, ...]
    shared_paths: tuple[Path, ...]
    missing_paths: tuple[Path, ...]
    backup_paths: tuple[Path, ...]
    issues: tuple[CleanupIssue, ...]

    @property
    def removed_record_count(self) -> int:
        return len(self.original_records) - len(self.retained_records)

    @property
    def error_count(self) -> int:
        return sum(issue.severity == "error" for issue in self.issues)

    @property
    def warning_count(self) -> int:
        return sum(issue.severity == "warning" for issue in self.issues)

    @property
    def can_apply(self) -> bool:
        return self.error_count == 0


@dataclass(frozen=True, slots=True)
class CleanupResult:
    backup_path: Path
    retained_record_count: int
    removed_record_count: int
    deleted_paths: tuple[Path, ...]
    failed_paths: tuple[Path, ...]


def plan_legacy_cleanup(
    config_path: str | Path = "config.toml",
    history_path: str | Path = "outputs/roster_build_registry.json",
) -> CleanupPlan:
    config_path = Path(config_path)
    history_path = Path(history_path)
    config_bytes = _required_file_bytes(config_path, "config")
    history_bytes = _required_file_bytes(history_path, "history registry")
    config = load_config(config_path)
    history = _decode_history(history_bytes)
    presets = config.get("tournament_presets", {})
    if not isinstance(presets, dict) or not presets:
        raise CleanupError("No active tournament presets were found in the config.")

    project_root = config_path.parent.resolve()
    output_dir = history_path.parent.resolve()
    issues: list[CleanupIssue] = []
    retentions: list[PresetRetention] = []
    retained_indices: set[int] = set()

    for preset_name, preset_config in presets.items():
        if not isinstance(preset_config, dict):
            issues.append(
                CleanupIssue("error", str(preset_name), "Preset is not a table.")
            )
            continue
        matches = _matching_history_indices(
            str(preset_name), preset_config, history
        )
        successful = [
            index
            for index in matches
            if str(history[index].get("status") or "").lower()
            in SUCCESS_STATUSES
        ]
        candidates = successful or matches
        if not candidates:
            issues.append(
                CleanupIssue(
                    "error",
                    str(preset_name),
                    "No matching history record exists for this active preset.",
                )
            )
            continue
        if not successful:
            issues.append(
                CleanupIssue(
                    "warning",
                    str(preset_name),
                    "No successful history record exists; retaining the newest match.",
                )
            )

        retained_index = max(candidates, key=lambda index: _record_sort_key(history[index]))
        if retained_index in retained_indices:
            issues.append(
                CleanupIssue(
                    "error",
                    str(preset_name),
                    "Its newest history record is also assigned to another preset.",
                )
            )
            continue
        retained_indices.add(retained_index)
        record = history[retained_index]
        retentions.append(
            PresetRetention(
                preset_name=str(preset_name),
                history_index=retained_index,
                source_record_id=_optional_text(record.get("id")),
                roster_name=str(record.get("roster_name") or ""),
                created_at=_optional_text(record.get("created_at")),
            )
        )

    retained_records = tuple(
        record for index, record in enumerate(history) if index in retained_indices
    )
    removed_records = [
        record for index, record in enumerate(history) if index not in retained_indices
    ]
    retained_paths = _record_artifact_paths(
        retained_records, project_root, output_dir, issues
    )
    active_paths = _active_preset_paths(
        presets, project_root, output_dir, issues
    )
    removed_paths = _record_artifact_paths(
        removed_records, project_root, output_dir, issues
    )
    protected_paths = retained_paths | active_paths
    delete_candidates = removed_paths - protected_paths
    shared_paths = removed_paths & protected_paths
    delete_paths = tuple(sorted(path for path in delete_candidates if path.is_file()))
    missing_paths = tuple(sorted(path for path in delete_candidates if not path.exists()))
    all_history_paths = _record_artifact_paths(
        history, project_root, output_dir, issues
    )
    backup_paths = tuple(sorted(path for path in all_history_paths if path.is_file()))

    return CleanupPlan(
        config_path=config_path,
        history_path=history_path,
        project_root=project_root,
        output_dir=output_dir,
        config_fingerprint=_sha256(config_bytes),
        history_fingerprint=_sha256(history_bytes),
        original_records=tuple(history),
        retained_records=retained_records,
        retentions=tuple(sorted(retentions, key=lambda item: item.preset_name)),
        delete_paths=delete_paths,
        shared_paths=tuple(sorted(shared_paths)),
        missing_paths=missing_paths,
        backup_paths=backup_paths,
        issues=tuple(issues),
    )


def apply_legacy_cleanup(
    plan: CleanupPlan,
    backup_dir: str | Path = "state/backups",
) -> CleanupResult:
    if not plan.can_apply:
        raise CleanupError("Cleanup plan contains errors and cannot be applied.")
    _verify_unchanged(plan)
    backup_path = _write_backup(plan, Path(backup_dir))
    _write_history_atomically(plan.history_path, plan.retained_records)

    deleted_paths: list[Path] = []
    failed_paths: list[Path] = []
    for path in plan.delete_paths:
        try:
            path.unlink()
        except OSError:
            failed_paths.append(path)
        else:
            deleted_paths.append(path)

    return CleanupResult(
        backup_path=backup_path,
        retained_record_count=len(plan.retained_records),
        removed_record_count=plan.removed_record_count,
        deleted_paths=tuple(deleted_paths),
        failed_paths=tuple(failed_paths),
    )


def render_cleanup_plan(plan: CleanupPlan, *, details: bool = False) -> str:
    delete_bytes = sum(path.stat().st_size for path in plan.delete_paths)
    lines = [
        "Legacy history cleanup preview (read-only)",
        f"Active presets: {len(plan.retentions)}",
        f"History records: {len(plan.original_records)}",
        f"Records retained: {len(plan.retained_records)}",
        f"Records removed: {plan.removed_record_count}",
        f"Files to delete: {len(plan.delete_paths)} ({delete_bytes} bytes)",
        f"Shared files protected: {len(plan.shared_paths)}",
        f"Already-missing artifact paths: {len(plan.missing_paths)}",
        f"Files included in backup: {len(plan.backup_paths)}",
        f"Warnings: {plan.warning_count}",
        f"Errors: {plan.error_count}",
    ]

    if plan.issues:
        lines.extend(["", "Issues:"])
        lines.extend(
            f"- {issue.severity.upper()} [{issue.identity}] {issue.message}"
            for issue in plan.issues
        )

    lines.extend(["", "Retained builds:"])
    lines.extend(
        f"- {retention.preset_name}: {retention.created_at or 'unknown date'} | "
        f"{retention.roster_name} | source={retention.source_record_id or 'none'}"
        for retention in plan.retentions
    )

    if details:
        lines.extend(["", "Files to delete:"])
        lines.extend(f"- {path}" for path in plan.delete_paths)
        if plan.missing_paths:
            lines.extend(["", "Already-missing artifact paths:"])
            lines.extend(f"- {path}" for path in plan.missing_paths)

    lines.extend(
        [
            "",
            "No files were changed. Run again with --apply to back up and apply.",
        ]
    )
    return "\n".join(lines)


def _matching_history_indices(
    preset_name: str,
    preset_config: dict[str, Any],
    history: list[dict[str, Any]],
) -> list[int]:
    build_number = preset_config.get("_gui_build_number")
    roster_name = _optional_text(preset_config.get("_gui_roster_name"))
    name_match = re.match(r"^preset_(\d{3})_", preset_name)
    inferred_number = int(name_match.group(1)) if name_match else None

    return [
        index
        for index, record in enumerate(history)
        if record.get("preset_name") == preset_name
        or (build_number is not None and record.get("build_number") == build_number)
        or (roster_name is not None and record.get("roster_name") == roster_name)
        or (
            inferred_number is not None
            and record.get("build_number") == inferred_number
        )
    ]


def _record_sort_key(record: dict[str, Any]) -> tuple[str, int]:
    created_at = str(record.get("created_at") or "")
    build_number = record.get("build_number")
    numeric_build = int(build_number) if str(build_number or "").isdigit() else -1
    return created_at, numeric_build


def _record_artifact_paths(
    records: Any,
    project_root: Path,
    output_dir: Path,
    issues: list[CleanupIssue],
) -> set[Path]:
    paths: set[Path] = set()
    for record in records:
        for field in ("html_output", "snapshot_path"):
            value = _optional_text(record.get(field))
            if value is None:
                continue
            path = _safe_output_path(value, project_root, output_dir)
            if path is None:
                issues.append(
                    CleanupIssue(
                        "warning",
                        str(record.get("id") or "unknown"),
                        f"Ignored {field} outside the output directory: {value}",
                    )
                )
                continue
            paths.add(path)
    return paths


def _active_preset_paths(
    presets: dict[str, Any],
    project_root: Path,
    output_dir: Path,
    issues: list[CleanupIssue],
) -> set[Path]:
    paths: set[Path] = set()
    for preset_name, preset_config in presets.items():
        values = [
            preset_roster_output_path(str(preset_name)),
            preset_upgrade_output_path(str(preset_name)),
        ]
        configured_html = _optional_text(preset_config.get("_gui_html_output"))
        if configured_html:
            values.extend(
                [configured_html, str(snapshot_path_for_html(configured_html))]
            )
        for value in values:
            path = _safe_output_path(value, project_root, output_dir)
            if path is None:
                issues.append(
                    CleanupIssue(
                        "warning",
                        str(preset_name),
                        f"Ignored active artifact outside the output directory: {value}",
                    )
                )
                continue
            paths.add(path)
    return paths


def _safe_output_path(
    value: str, project_root: Path, output_dir: Path
) -> Path | None:
    path = Path(value)
    if not path.is_absolute():
        path = project_root / path
    resolved = path.resolve()
    try:
        resolved.relative_to(output_dir)
    except ValueError:
        return None
    return resolved


def _verify_unchanged(plan: CleanupPlan) -> None:
    if _sha256(_required_file_bytes(plan.config_path, "config")) != plan.config_fingerprint:
        raise CleanupError("Config changed after the cleanup preview; preview again.")
    if (
        _sha256(_required_file_bytes(plan.history_path, "history registry"))
        != plan.history_fingerprint
    ):
        raise CleanupError("History changed after the cleanup preview; preview again.")


def _write_backup(plan: CleanupPlan, backup_dir: Path) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup_path = backup_dir / f"legacy_cleanup_{timestamp}.zip"
    temporary_path = backup_path.with_suffix(".zip.tmp")
    manifest = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "config_fingerprint": plan.config_fingerprint,
        "history_fingerprint": plan.history_fingerprint,
        "original_record_count": len(plan.original_records),
        "retained_record_count": len(plan.retained_records),
        "removed_record_count": plan.removed_record_count,
        "retained_presets": [
            {
                "preset_name": item.preset_name,
                "source_record_id": item.source_record_id,
                "created_at": item.created_at,
            }
            for item in plan.retentions
        ],
        "delete_paths": [str(path) for path in plan.delete_paths],
    }
    try:
        with zipfile.ZipFile(
            temporary_path, mode="w", compression=zipfile.ZIP_DEFLATED
        ) as archive:
            archive.write(plan.config_path, "source/config.toml")
            archive.write(plan.history_path, "source/roster_build_registry.json")
            for path in plan.backup_paths:
                relative = path.relative_to(plan.output_dir)
                archive.write(path, Path("artifacts") / relative)
            archive.writestr("cleanup_manifest.json", json.dumps(manifest, indent=2))
        with zipfile.ZipFile(temporary_path) as archive:
            damaged_member = archive.testzip()
            if damaged_member is not None:
                raise CleanupError(
                    f"Backup verification failed for archive member {damaged_member}."
                )
        temporary_path.replace(backup_path)
    except CleanupError:
        temporary_path.unlink(missing_ok=True)
        raise
    except (OSError, zipfile.BadZipFile) as exc:
        temporary_path.unlink(missing_ok=True)
        raise CleanupError(f"Could not create cleanup backup: {exc}") from exc
    return backup_path


def _write_history_atomically(
    history_path: Path, records: tuple[dict[str, Any], ...]
) -> None:
    temporary_path = history_path.with_suffix(history_path.suffix + ".tmp")
    try:
        temporary_path.write_text(
            json.dumps(list(records), indent=2) + "\n", encoding="utf-8"
        )
        temporary_path.replace(history_path)
    except OSError as exc:
        temporary_path.unlink(missing_ok=True)
        raise CleanupError(f"Could not rewrite history registry: {exc}") from exc


def _decode_history(history_bytes: bytes) -> list[dict[str, Any]]:
    try:
        decoded = json.loads(history_bytes)
    except json.JSONDecodeError as exc:
        raise CleanupError(f"History registry is invalid JSON: {exc}") from exc
    if not isinstance(decoded, list) or not all(
        isinstance(record, dict) for record in decoded
    ):
        raise CleanupError("History registry must contain a list of objects.")
    return decoded


def _required_file_bytes(path: Path, label: str) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        raise CleanupError(f"Cannot read {label} at {path}: {exc}") from exc


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _optional_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None
