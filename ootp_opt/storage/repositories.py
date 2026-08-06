from __future__ import annotations

import json
import sqlite3
from typing import Any, Protocol

from ootp_opt.storage.models import BuildRecord, PresetRecord


class PresetRepository(Protocol):
    def list_all(self) -> list[PresetRecord]: ...

    def get(self, preset_id: str) -> PresetRecord | None: ...

    def get_by_command_name(self, command_name: str) -> PresetRecord | None: ...

    def add(self, preset: PresetRecord) -> PresetRecord: ...


class BuildRepository(Protocol):
    def list_all(self, *, limit: int | None = None) -> list[BuildRecord]: ...

    def get(self, build_id: str) -> BuildRecord | None: ...

    def add(self, build: BuildRecord) -> BuildRecord: ...


class SqlitePresetRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def list_all(self) -> list[PresetRecord]:
        rows = self.connection.execute(
            "SELECT * FROM presets ORDER BY command_name"
        ).fetchall()
        return [_preset_from_row(row) for row in rows]

    def get(self, preset_id: str) -> PresetRecord | None:
        row = self.connection.execute(
            "SELECT * FROM presets WHERE id = ?", (preset_id,)
        ).fetchone()
        return _preset_from_row(row) if row is not None else None

    def get_by_command_name(self, command_name: str) -> PresetRecord | None:
        row = self.connection.execute(
            "SELECT * FROM presets WHERE command_name = ?", (command_name,)
        ).fetchone()
        return _preset_from_row(row) if row is not None else None

    def add(self, preset: PresetRecord) -> PresetRecord:
        columns = [
            "id",
            "command_name",
            "display_title",
            "note",
            "base_profile",
            "build_method",
            "rules_json",
            "source",
        ]
        values: list[Any] = [
            preset.id,
            preset.command_name,
            preset.display_title,
            preset.note,
            preset.base_profile,
            preset.build_method,
            _encode_json(preset.rules),
            preset.source,
        ]
        if preset.created_at is not None:
            columns.append("created_at")
            values.append(preset.created_at)
        if preset.updated_at is not None:
            columns.append("updated_at")
            values.append(preset.updated_at)

        placeholders = ", ".join("?" for _ in columns)
        self.connection.execute(
            f"INSERT INTO presets ({', '.join(columns)}) VALUES ({placeholders})",
            values,
        )
        stored = self.get(preset.id)
        if stored is None:
            raise RuntimeError(f"Preset {preset.id} was not stored.")
        return stored


class SqliteBuildRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def list_all(self, *, limit: int | None = None) -> list[BuildRecord]:
        sql = "SELECT * FROM builds ORDER BY created_at DESC, id"
        parameters: tuple[Any, ...] = ()
        if limit is not None:
            if limit < 0:
                raise ValueError("Build list limit cannot be negative.")
            sql += " LIMIT ?"
            parameters = (limit,)
        rows = self.connection.execute(sql, parameters).fetchall()
        return [_build_from_row(row) for row in rows]

    def get(self, build_id: str) -> BuildRecord | None:
        row = self.connection.execute(
            "SELECT * FROM builds WHERE id = ?", (build_id,)
        ).fetchone()
        return _build_from_row(row) if row is not None else None

    def add(self, build: BuildRecord) -> BuildRecord:
        columns = [
            "id",
            "source_record_id",
            "build_number",
            "preset_id",
            "roster_name",
            "build_type",
            "build_method",
            "status",
            "model_version",
            "request_json",
            "ruleset_json",
            "diagnostics_json",
            "objective_score",
            "source_fingerprint",
        ]
        values: list[Any] = [
            build.id,
            build.source_record_id,
            build.build_number,
            build.preset_id,
            build.roster_name,
            build.build_type,
            build.build_method,
            build.status,
            build.model_version,
            _encode_json(build.request),
            _encode_json(build.ruleset),
            _encode_json(build.diagnostics),
            build.objective_score,
            build.source_fingerprint,
        ]
        if build.created_at is not None:
            columns.append("created_at")
            values.append(build.created_at)

        placeholders = ", ".join("?" for _ in columns)
        self.connection.execute(
            f"INSERT INTO builds ({', '.join(columns)}) VALUES ({placeholders})",
            values,
        )
        stored = self.get(build.id)
        if stored is None:
            raise RuntimeError(f"Build {build.id} was not stored.")
        return stored


def _preset_from_row(row: sqlite3.Row) -> PresetRecord:
    return PresetRecord(
        id=str(row["id"]),
        command_name=str(row["command_name"]),
        display_title=row["display_title"],
        note=row["note"],
        base_profile=str(row["base_profile"]),
        build_method=row["build_method"],
        rules=_decode_json(row["rules_json"]),
        source=str(row["source"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def _build_from_row(row: sqlite3.Row) -> BuildRecord:
    return BuildRecord(
        id=str(row["id"]),
        source_record_id=row["source_record_id"],
        build_number=row["build_number"],
        preset_id=row["preset_id"],
        roster_name=str(row["roster_name"]),
        build_type=str(row["build_type"]),
        build_method=row["build_method"],
        status=str(row["status"]),
        model_version=str(row["model_version"]),
        request=_decode_json(row["request_json"]),
        ruleset=_decode_json(row["ruleset_json"]),
        diagnostics=_decode_json(row["diagnostics_json"]),
        objective_score=row["objective_score"],
        source_fingerprint=row["source_fingerprint"],
        created_at=str(row["created_at"]),
    )


def _encode_json(value: dict[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _decode_json(value: str) -> dict[str, Any]:
    decoded = json.loads(value)
    if not isinstance(decoded, dict):
        raise ValueError("Stored JSON payload must be an object.")
    return decoded
