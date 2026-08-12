from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from sqlite3 import Connection
from typing import Any, Iterator, cast
from uuid import uuid4

from ootp_opt.config import load_config
from ootp_opt.roster.rules import build_ruleset_from_tournament_preset
from ootp_opt.services.preset_service import (
    delete_existing_files,
    preset_owned_output_paths,
    safe_preset_name,
)
from ootp_opt.storage.database import connect_database, database_path_from_config
from ootp_opt.storage.migrator import migrate_database
from ootp_opt.services.candidate_service import resolve_build_context
from ootp_opt.storage.models import (
    BuildMethod,
    BuildRunRecord,
    RosterPlanRecord,
    RosterPlanStatus,
)
from ootp_opt.storage.repositories import (
    SqliteBuildRunRepository,
    SqliteRosterPlanRepository,
)

APPLICATION_MODEL_VERSION = "sqlite-runtime-v1"


class ApplicationStateError(RuntimeError):
    """Raised when SQLite application state is unavailable or inconsistent."""


@dataclass(frozen=True, slots=True)
class RosterPlanValidation:
    plan_key: str
    errors: dict[str, str]

    @property
    def is_valid(self) -> bool:
        return not self.errors


def load_runtime_config(config_path: str | Path = "config.toml") -> dict[str, Any]:
    config_path = Path(config_path)
    config = load_config(config_path)
    database_path = resolve_application_database_path(config_path, config)
    if not database_path.is_file():
        return config

    with application_connection(config_path, require_existing=True) as connection:
        presets = SqliteRosterPlanRepository(connection).list_active()
    runtime = dict(config)
    runtime["tournament_presets"] = {
        preset.command_name: preset_config(preset) for preset in presets
    }
    return runtime


def load_application_build_records(
    config_path: str | Path = "config.toml",
) -> list[dict[str, Any]]:
    with application_connection(config_path) as connection:
        presets = SqliteRosterPlanRepository(connection).list_all()
        builds = SqliteBuildRunRepository(connection).list_all()
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
        preset_repository = SqliteRosterPlanRepository(connection)
        preset = (
            preset_repository.get_by_command_name(preset_name) if preset_name else None
        )
        if preset_name and preset is None:
            raise ApplicationStateError(f"Preset '{preset_name}' does not exist.")
        if preset is None:
            preset = _create_plan_for_run(
                preset_repository,
                build_number=build_number,
                roster_name=roster_name,
                build_type=build_type,
                base_profile=base_profile or "playoff_pt",
                build_method=build_method,
                overrides=overrides,
            )
            preset_name = preset.command_name
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
        build = SqliteBuildRunRepository(connection).add(
            BuildRunRecord(
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
        preset_repository.update(
            replace(preset, lifecycle_status="active", validation_errors={})
        )
        connection.commit()
        return build_record_to_legacy_dict(
            build,
            {preset.id: preset.command_name} if preset else {},
            {"roster_html": html_output, "roster_snapshot": snapshot_path},
        )


def create_application_roster_plan(
    *,
    config_path: str | Path,
    plan_key: str,
    display_title: str,
    plan_type: str,
    base_profile: str,
    build_method: BuildMethod,
    rules: dict[str, Any],
    note: str | None = None,
    lifecycle_status: RosterPlanStatus = "draft",
    source: str = "application",
) -> RosterPlanRecord:
    command_name = safe_preset_name(plan_key)
    normalized_rules = {
        **rules,
        "base_profile": base_profile,
        "build_method": build_method,
        "_gui_title": display_title,
        "_gui_roster_name": display_title,
        "_gui_build_type": plan_type,
    }
    with application_connection(config_path) as connection:
        repository = SqliteRosterPlanRepository(connection)
        if repository.get_by_command_name(command_name) is not None:
            raise ValueError(f"Roster plan '{command_name}' already exists.")
        repository.add(
            RosterPlanRecord(
                id=str(uuid4()),
                command_name=command_name,
                display_title=display_title.strip() or command_name,
                note=(note or "").strip() or None,
                base_profile=base_profile,
                build_method=build_method,
                rules=normalized_rules,
                plan_type=plan_type,
                lifecycle_status=lifecycle_status,
                source=source,
            )
        )
        connection.commit()
    validate_application_roster_plan(
        config_path=config_path,
        plan_name=command_name,
    )
    return get_application_roster_plan(config_path, command_name)


def add_application_preset_from_build(
    *,
    config_path: str | Path,
    record: dict[str, Any],
    preset_name: str,
) -> RosterPlanRecord:
    command_name = safe_preset_name(preset_name)
    with application_connection(config_path) as connection:
        repository = SqliteRosterPlanRepository(connection)
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
            RosterPlanRecord(
                id=str(uuid4()),
                command_name=command_name,
                display_title=str(record.get("roster_name") or command_name),
                base_profile=str(rules["base_profile"]),
                build_method=_build_method(rules["build_method"]),
                rules=rules,
                plan_type=str(record.get("build_type") or "pt_tournament"),
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
) -> RosterPlanRecord:
    with application_connection(config_path) as connection:
        repository = SqliteRosterPlanRepository(connection)
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
) -> RosterPlanRecord:
    method = _build_method(build_method)
    with application_connection(config_path) as connection:
        repository = SqliteRosterPlanRepository(connection)
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
        repository = SqliteRosterPlanRepository(connection)
        preset = _required_preset(repository, preset_name)
        output_paths = preset_owned_output_paths(preset_name, preset_config(preset))
        SqliteBuildRunRepository(connection).delete_for_roster_plan(preset.id)
        repository.delete(preset.id)
        connection.commit()
    return delete_existing_files(output_paths)


def list_application_roster_plans(
    config_path: str | Path = "config.toml",
    *,
    include_archived: bool = False,
) -> list[RosterPlanRecord]:
    with application_connection(config_path) as connection:
        repository = SqliteRosterPlanRepository(connection)
        return repository.list_all() if include_archived else repository.list_active()


def get_application_roster_plan(
    config_path: str | Path,
    plan_name: str,
) -> RosterPlanRecord:
    with application_connection(config_path) as connection:
        return _required_preset(SqliteRosterPlanRepository(connection), plan_name)


def list_base_profile_templates(
    config_path: str | Path = "config.toml",
) -> dict[str, dict[str, Any]]:
    config = load_config(config_path)
    return {
        str(name): dict(values)
        for name, values in config.get("roster_base_profiles", {}).items()
    }


def update_application_roster_plan(
    *,
    config_path: str | Path,
    plan_name: str,
    base_profile: str,
    plan_type: str,
    build_method: BuildMethod,
    rules: dict[str, Any],
) -> tuple[RosterPlanRecord, RosterPlanValidation]:
    with application_connection(config_path) as connection:
        repository = SqliteRosterPlanRepository(connection)
        plan = _required_preset(repository, plan_name)
        normalized_rules = {
            **rules,
            "base_profile": base_profile,
            "build_method": build_method,
            "_gui_title": plan.display_title or plan.command_name,
            "_gui_roster_name": plan.rules.get(
                "_gui_roster_name", plan.display_title or plan.command_name
            ),
            "_gui_build_type": plan_type,
        }
        repository.update(
            replace(
                plan,
                base_profile=base_profile,
                plan_type=plan_type,
                build_method=build_method,
                rules=normalized_rules,
            )
        )
        connection.commit()
    validation = validate_application_roster_plan(
        config_path=config_path,
        plan_name=plan_name,
    )
    return get_application_roster_plan(config_path, plan_name), validation


def rename_application_roster_plan(
    *,
    config_path: str | Path,
    plan_name: str,
    display_title: str,
) -> RosterPlanRecord:
    title = display_title.strip()
    if not title:
        raise ValueError("Roster plan display title cannot be blank.")
    with application_connection(config_path) as connection:
        repository = SqliteRosterPlanRepository(connection)
        plan = _required_preset(repository, plan_name)
        rules = dict(plan.rules)
        rules["_gui_title"] = title
        updated = repository.update(
            replace(plan, display_title=title, rules=rules)
        )
        connection.commit()
        return updated


def archive_application_roster_plan(
    *,
    config_path: str | Path,
    plan_name: str,
    archived: bool = True,
) -> RosterPlanRecord:
    with application_connection(config_path) as connection:
        repository = SqliteRosterPlanRepository(connection)
        plan = _required_preset(repository, plan_name)
        status: RosterPlanStatus = "archived" if archived else "active"
        updated = repository.update(replace(plan, lifecycle_status=status))
        connection.commit()
        return updated


def validate_application_roster_plan(
    *,
    config_path: str | Path,
    plan_name: str,
) -> RosterPlanValidation:
    errors: dict[str, str] = {}
    try:
        config = load_runtime_config(config_path)
        ruleset = build_ruleset_from_tournament_preset(config, plan_name)
        resolve_build_context(config, ruleset)
    except (KeyError, TypeError, ValueError) as exc:
        errors[_validation_field(str(exc))] = str(exc)

    with application_connection(config_path) as connection:
        repository = SqliteRosterPlanRepository(connection)
        plan = _required_preset(repository, plan_name)
        repository.update(replace(plan, validation_errors=errors))
        connection.commit()
    return RosterPlanValidation(plan_key=plan_name, errors=errors)


def record_application_roster_plan_error(
    *,
    config_path: str | Path,
    plan_name: str,
    error: Exception,
) -> RosterPlanRecord:
    message = str(error)
    with application_connection(config_path) as connection:
        repository = SqliteRosterPlanRepository(connection)
        plan = _required_preset(repository, plan_name)
        updated = repository.update(
            replace(plan, validation_errors={_validation_field(message): message})
        )
        connection.commit()
        return updated


def preset_config(preset: RosterPlanRecord) -> dict[str, Any]:
    config = dict(preset.rules)
    config["base_profile"] = preset.base_profile
    config["build_method"] = preset.build_method
    _set_optional(config, "_gui_title", preset.display_title or "")
    _set_optional(config, "_gui_note", preset.note or "")
    config["_roster_plan_status"] = preset.lifecycle_status
    config["_roster_plan_type"] = preset.plan_type
    if preset.validation_errors:
        config["_validation_errors"] = dict(preset.validation_errors)
    return config


def build_record_to_legacy_dict(
    build: BuildRunRecord,
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
    repository: SqliteRosterPlanRepository, preset_name: str
) -> RosterPlanRecord:
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


def _create_plan_for_run(
    repository: SqliteRosterPlanRepository,
    *,
    build_number: int,
    roster_name: str,
    build_type: str,
    base_profile: str,
    build_method: BuildMethod,
    overrides: dict[str, Any],
) -> RosterPlanRecord:
    base_key = safe_preset_name(f"roster_{build_number:03d}_{roster_name}")
    command_name = base_key
    suffix = 2
    while repository.get_by_command_name(command_name) is not None:
        command_name = f"{base_key}_{suffix}"
        suffix += 1
    rules = {
        "base_profile": base_profile,
        **overrides,
        "build_method": build_method,
        "_gui_title": roster_name,
        "_gui_roster_name": roster_name,
        "_gui_build_type": build_type,
        "_gui_build_number": build_number,
    }
    return repository.add(
        RosterPlanRecord(
            id=str(uuid4()),
            command_name=command_name,
            display_title=roster_name,
            base_profile=base_profile,
            build_method=build_method,
            rules=rules,
            plan_type=build_type,
            lifecycle_status="active",
            source="automatic-build",
        )
    )


def _validation_field(message: str) -> str:
    normalized = message.lower()
    field_keywords = (
        ("ballpark year", "ballpark_year"),
        ("ballpark", "ballpark"),
        ("simulation year", "simulation_year"),
        ("base roster profile", "base_profile"),
        ("tier slot", "tier_slots"),
        ("card value", "card_value"),
        ("variant", "variant_limit"),
        ("point cap", "point_cap_total"),
    )
    for keyword, field in field_keywords:
        if keyword in normalized:
            return field
    return "_form"
