from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from sqlite3 import Connection
from typing import Any, Iterator, cast
from uuid import uuid4

from ootp_opt.config import load_config
from ootp_opt.services.preset_service import (
    delete_existing_files,
    preset_owned_output_paths,
    safe_preset_name,
)
from ootp_opt.storage.database import connect_database, database_path_from_config
from ootp_opt.storage.migrator import migrate_database
from ootp_opt.storage.models import BuildMethod, BuildRecord, PresetRecord
from ootp_opt.storage.repositories import (
    SqliteBuildRepository,
    SqlitePresetRepository,
)

APPLICATION_MODEL_VERSION = "sqlite-runtime-v1"


class ApplicationStateError(RuntimeError):
    """Raised when SQLite application state is unavailable or inconsistent."""


def load_runtime_config(config_path: str | Path = "config.toml") -> dict[str, Any]:
    config_path = Path(config_path)
    config = load_config(config_path)
    database_path = resolve_application_database_path(config_path, config)
    if not database_path.is_file():
        return config

    with application_connection(config_path, require_existing=True) as connection:
        presets = SqlitePresetRepository(connection).list_all()
    runtime = dict(config)
    runtime["tournament_presets"] = {
        preset.command_name: preset_config(preset) for preset in presets
    }
    return runtime


def load_application_build_records(
    config_path: str | Path = "config.toml",
) -> list[dict[str, Any]]:
    with application_connection(config_path) as connection:
        presets = SqlitePresetRepository(connection).list_all()
        builds = SqliteBuildRepository(connection).list_all()
        preset_names = {preset.id: preset.command_name for preset in presets}
        artifact_rows = connection.execute(
            "SELECT build_id, artifact_type, path FROM build_artifacts"
        ).fetchall()
    artifacts: dict[str, dict[str, str]] = {}
    for row in artifact_rows:
        artifacts.setdefault(str(row["build_id"]), {})[str(row["artifact_type"])] = str(
            row["path"]
        )
    return [
        build_record_to_legacy_dict(build, preset_names, artifacts.get(build.id, {}))
        for build in builds
    ]


def append_application_build_record(
    *,
    config_path: str | Path,
    build_number: int,
    roster_name: str,
    build_type: str,
    preset_name: str | None,
    base_profile: str | None,
    overrides: dict[str, Any],
    html_output: str | Path,
    snapshot_path: str | Path,
    status: str,
    build_method: BuildMethod,
    objective_score: float | None = None,
    diagnostics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    html_output = str(html_output)
    snapshot_path = str(snapshot_path)
    with application_connection(config_path) as connection:
        preset_repository = SqlitePresetRepository(connection)
        preset = (
            preset_repository.get_by_command_name(preset_name) if preset_name else None
        )
        if preset_name and preset is None:
            raise ApplicationStateError(f"Preset '{preset_name}' does not exist.")
        request = {
            "base_profile": base_profile,
            "preset_name": preset_name,
            "overrides": overrides,
        }
        ruleset = (
            dict(preset.rules)
            if preset is not None
            else {"base_profile": base_profile, **overrides}
        )
        build = SqliteBuildRepository(connection).add(
            BuildRecord(
                id=str(uuid4()),
                source_record_id=None,
                build_number=build_number,
                preset_id=preset.id if preset else None,
                roster_name=roster_name,
                build_type=build_type,
                build_method=build_method,
                status=status,
                model_version=APPLICATION_MODEL_VERSION,
                request=request,
                ruleset=ruleset,
                diagnostics=diagnostics or {},
                objective_score=objective_score,
            )
        )
        _insert_artifact(connection, build.id, "roster_html", html_output)
        _insert_artifact(connection, build.id, "roster_snapshot", snapshot_path)
        connection.commit()
        return build_record_to_legacy_dict(
            build,
            {preset.id: preset.command_name} if preset else {},
            {"roster_html": html_output, "roster_snapshot": snapshot_path},
        )


def add_application_preset_from_build(
    *,
    config_path: str | Path,
    record: dict[str, Any],
    preset_name: str,
) -> PresetRecord:
    command_name = safe_preset_name(preset_name)
    with application_connection(config_path) as connection:
        repository = SqlitePresetRepository(connection)
        if repository.get_by_command_name(command_name) is not None:
            raise ValueError(f"Preset '{command_name}' already exists.")
        rules = {
            "base_profile": record.get("base_profile") or "playoff_pt",
            **dict(record.get("overrides") or {}),
            "build_method": str(record.get("build_method") or "greedy"),
            "_gui_title": str(record.get("roster_name") or command_name),
            "_gui_roster_name": str(record.get("roster_name") or command_name),
            "_gui_build_type": str(record.get("build_type") or "pt_tournament"),
        }
        if str(record.get("build_number") or "").isdigit():
            rules["_gui_build_number"] = int(record["build_number"])
        if record.get("html_output"):
            rules["_gui_html_output"] = str(record["html_output"])
        preset = repository.add(
            PresetRecord(
                id=str(uuid4()),
                command_name=command_name,
                display_title=str(record.get("roster_name") or command_name),
                base_profile=str(rules["base_profile"]),
                build_method=_build_method(rules["build_method"]),
                rules=rules,
                source="gui",
            )
        )
        connection.commit()
        return preset


def update_application_preset_notes(
    *,
    config_path: str | Path,
    preset_name: str,
    title: str | None,
    note: str | None,
) -> PresetRecord:
    with application_connection(config_path) as connection:
        repository = SqlitePresetRepository(connection)
        preset = _required_preset(repository, preset_name)
        title = (title or "").strip()
        note = (note or "").strip()
        rules = dict(preset.rules)
        _set_optional(rules, "_gui_title", title)
        _set_optional(rules, "_gui_note", note)
        updated = repository.update(
            replace(
                preset,
                display_title=title or None,
                note=note or None,
                rules=rules,
            )
        )
        connection.commit()
        return updated


def update_application_preset_build_method(
    *,
    config_path: str | Path,
    preset_name: str,
    build_method: str,
) -> PresetRecord:
    method = _build_method(build_method)
    with application_connection(config_path) as connection:
        repository = SqlitePresetRepository(connection)
        preset = _required_preset(repository, preset_name)
        rules = dict(preset.rules)
        rules["build_method"] = method
        updated = repository.update(replace(preset, build_method=method, rules=rules))
        connection.commit()
        return updated


def delete_application_preset(
    *, config_path: str | Path, preset_name: str
) -> list[Path]:
    with application_connection(config_path) as connection:
        repository = SqlitePresetRepository(connection)
        preset = _required_preset(repository, preset_name)
        output_paths = preset_owned_output_paths(preset_name, preset_config(preset))
        repository.delete(preset.id)
        connection.commit()
    return delete_existing_files(output_paths)


def preset_config(preset: PresetRecord) -> dict[str, Any]:
    config = dict(preset.rules)
    config["base_profile"] = preset.base_profile
    config["build_method"] = preset.build_method
    _set_optional(config, "_gui_title", preset.display_title or "")
    _set_optional(config, "_gui_note", preset.note or "")
    return config


def build_record_to_legacy_dict(
    build: BuildRecord,
    preset_names: dict[str, str],
    artifacts: dict[str, str],
) -> dict[str, Any]:
    return {
        "id": build.id,
        "source_record_id": build.source_record_id,
        "build_number": build.build_number,
        "created_at": build.created_at,
        "roster_name": build.roster_name,
        "build_type": build.build_type,
        "preset_name": preset_names.get(build.preset_id or "")
        or build.request.get("preset_name"),
        "base_profile": build.request.get("base_profile"),
        "overrides": dict(build.request.get("overrides") or {}),
        "html_output": artifacts.get("roster_html"),
        "snapshot_path": artifacts.get("roster_snapshot"),
        "status": build.status,
        "build_method": build.build_method,
        "model_version": build.model_version,
        "objective_score": build.objective_score,
    }


def resolve_application_database_path(
    config_path: Path, config: dict[str, Any] | None = None
) -> Path:
    configured = database_path_from_config(config or load_config(config_path))
    if configured.is_absolute():
        return configured
    return config_path.parent / configured


@contextmanager
def application_connection(
    config_path: str | Path, *, require_existing: bool = True
) -> Iterator[Connection]:
    config_path = Path(config_path)
    database_path = resolve_application_database_path(config_path)
    if require_existing and not database_path.is_file():
        raise ApplicationStateError(
            f"Application database does not exist at {database_path}. "
            "Restore a storage backup or run import_storage.py --apply."
        )
    connection = connect_database(database_path)
    try:
        migrate_database(connection)
        yield connection
    finally:
        connection.close()


def _insert_artifact(
    connection: Connection, build_id: str, artifact_type: str, path: str
) -> None:
    connection.execute(
        """
        INSERT INTO build_artifacts (build_id, artifact_type, path)
        VALUES (?, ?, ?)
        """,
        (build_id, artifact_type, path),
    )


def _required_preset(
    repository: SqlitePresetRepository, preset_name: str
) -> PresetRecord:
    preset = repository.get_by_command_name(preset_name)
    if preset is None:
        raise ValueError(f"Preset '{preset_name}' does not exist.")
    return preset


def _set_optional(values: dict[str, Any], key: str, value: str) -> None:
    if value:
        values[key] = value
    else:
        values.pop(key, None)


def _build_method(value: Any) -> BuildMethod:
    if value not in {"greedy", "optimizer"}:
        raise ValueError(f"Unknown build method: {value}")
    return cast(BuildMethod, value)
