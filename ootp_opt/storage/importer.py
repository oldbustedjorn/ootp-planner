from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from ootp_opt.config import load_config
from ootp_opt.storage.backup import StorageBackup, create_storage_backup
from ootp_opt.storage.database import connect_database, database_path_from_config
from ootp_opt.storage.import_preview import ImportPreview, preview_existing_state
from ootp_opt.storage.migrator import migrate_database
from ootp_opt.storage.repositories import (
    SqliteBuildRepository,
    SqlitePresetRepository,
)


class StorageImportError(RuntimeError):
    """Raised when legacy state cannot be imported transactionally."""


@dataclass(frozen=True, slots=True)
class ImportVerification:
    expected_presets: int
    stored_presets: int
    expected_builds: int
    stored_builds: int
    expected_artifacts: int
    stored_artifacts: int
    preset_ids_match: bool
    build_ids_match: bool
    foreign_key_errors: int
    integrity_check: str

    @property
    def passed(self) -> bool:
        return (
            self.expected_presets == self.stored_presets
            and self.expected_builds == self.stored_builds
            and self.expected_artifacts == self.stored_artifacts
            and self.preset_ids_match
            and self.build_ids_match
            and self.foreign_key_errors == 0
            and self.integrity_check == "ok"
        )


@dataclass(frozen=True, slots=True)
class StorageImportResult:
    database_path: Path
    backup: StorageBackup
    verification: ImportVerification


def import_existing_state(
    *,
    config_path: str | Path = "config.toml",
    history_path: str | Path = "outputs/roster_build_registry.json",
    database_path: str | Path | None = None,
    backup_dir: str | Path = "state/backups",
) -> StorageImportResult:
    config_path = Path(config_path)
    history_path = Path(history_path)
    database_path = _resolve_database_path(config_path, database_path)
    preview = preview_existing_state(config_path, history_path)
    if preview.error_count:
        raise StorageImportError(
            f"Import preview contains {preview.error_count} errors."
        )

    backup = create_storage_backup(
        config_path=config_path,
        history_path=history_path,
        database_path=database_path,
        backup_dir=backup_dir,
        purpose="pre_import",
    )
    _verify_sources_match_backup(preview, backup)

    connection = connect_database(database_path)
    try:
        migrate_database(connection)
        _require_empty_import_target(connection)
        connection.execute("BEGIN IMMEDIATE")
        try:
            _insert_preview(connection, preview)
            verification = _verify_connection(connection, preview)
            if not verification.passed:
                raise StorageImportError(
                    f"Post-import verification failed: {verification}."
                )
            _verify_sources_match_backup(preview, backup)
        except Exception:
            connection.rollback()
            raise
        else:
            connection.commit()
    except StorageImportError:
        raise
    except (OSError, sqlite3.Error, ValueError) as exc:
        raise StorageImportError(f"Storage import failed: {exc}") from exc
    finally:
        connection.close()

    final_verification = verify_imported_state(
        config_path=config_path,
        history_path=history_path,
        database_path=database_path,
    )
    if not final_verification.passed:
        raise StorageImportError(
            f"Committed import verification failed: {final_verification}."
        )
    return StorageImportResult(
        database_path=database_path,
        backup=backup,
        verification=final_verification,
    )


def verify_imported_state(
    *,
    config_path: str | Path = "config.toml",
    history_path: str | Path = "outputs/roster_build_registry.json",
    database_path: str | Path | None = None,
) -> ImportVerification:
    config_path = Path(config_path)
    history_path = Path(history_path)
    database_path = _resolve_database_path(config_path, database_path)
    if not database_path.is_file():
        raise StorageImportError(f"Database does not exist: {database_path}.")
    preview = preview_existing_state(config_path, history_path)
    if preview.error_count:
        raise StorageImportError(
            f"Import preview contains {preview.error_count} errors."
        )

    connection = sqlite3.connect(
        f"{database_path.resolve().as_uri()}?mode=ro", uri=True
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        return _verify_connection(connection, preview)
    except sqlite3.Error as exc:
        raise StorageImportError(f"Could not verify imported state: {exc}") from exc
    finally:
        connection.close()


def _insert_preview(connection: sqlite3.Connection, preview: ImportPreview) -> None:
    preset_repository = SqlitePresetRepository(connection)
    build_repository = SqliteBuildRepository(connection)
    for preset in preview.presets:
        preset_repository.add(preset)
    for candidate in preview.builds:
        build_repository.add(candidate.record)
        _insert_artifact(
            connection,
            build_id=candidate.record.id,
            artifact_type="roster_html",
            path=candidate.html_output,
            project_root=preview.config_path.parent,
        )
        _insert_artifact(
            connection,
            build_id=candidate.record.id,
            artifact_type="roster_snapshot",
            path=candidate.snapshot_path,
            project_root=preview.config_path.parent,
        )


def _insert_artifact(
    connection: sqlite3.Connection,
    *,
    build_id: str,
    artifact_type: str,
    path: str | None,
    project_root: Path,
) -> None:
    if path is None:
        return
    artifact_path = Path(path)
    if not artifact_path.is_absolute():
        artifact_path = project_root / artifact_path
    content_hash = (
        hashlib.sha256(artifact_path.read_bytes()).hexdigest()
        if artifact_path.is_file()
        else None
    )
    connection.execute(
        """
        INSERT INTO build_artifacts (
            build_id, artifact_type, path, content_hash
        ) VALUES (?, ?, ?, ?)
        """,
        (build_id, artifact_type, path, content_hash),
    )


def _verify_connection(
    connection: sqlite3.Connection, preview: ImportPreview
) -> ImportVerification:
    preset_ids = {
        str(row[0]) for row in connection.execute("SELECT id FROM presets")
    }
    build_ids = {
        str(row[0]) for row in connection.execute("SELECT id FROM builds")
    }
    stored_artifacts = int(
        connection.execute("SELECT COUNT(*) FROM build_artifacts").fetchone()[0]
    )
    expected_artifacts = sum(
        candidate.html_output is not None for candidate in preview.builds
    ) + sum(candidate.snapshot_path is not None for candidate in preview.builds)
    foreign_key_errors = len(connection.execute("PRAGMA foreign_key_check").fetchall())
    integrity_row = connection.execute("PRAGMA integrity_check").fetchone()
    integrity_check = str(integrity_row[0]) if integrity_row is not None else "missing"
    expected_preset_ids = {preset.id for preset in preview.presets}
    expected_build_ids = {candidate.record.id for candidate in preview.builds}
    return ImportVerification(
        expected_presets=len(expected_preset_ids),
        stored_presets=len(preset_ids),
        expected_builds=len(expected_build_ids),
        stored_builds=len(build_ids),
        expected_artifacts=expected_artifacts,
        stored_artifacts=stored_artifacts,
        preset_ids_match=preset_ids == expected_preset_ids,
        build_ids_match=build_ids == expected_build_ids,
        foreign_key_errors=foreign_key_errors,
        integrity_check=integrity_check,
    )


def _require_empty_import_target(connection: sqlite3.Connection) -> None:
    preset_count = int(connection.execute("SELECT COUNT(*) FROM presets").fetchone()[0])
    build_count = int(connection.execute("SELECT COUNT(*) FROM builds").fetchone()[0])
    if preset_count or build_count:
        raise StorageImportError(
            "Import target already contains application data "
            f"({preset_count} presets, {build_count} builds)."
        )


def _verify_sources_match_backup(
    preview: ImportPreview, backup: StorageBackup
) -> None:
    expected_config = backup.manifest["config"]["sha256"]
    expected_history = backup.manifest["history"]["sha256"]
    actual_config = hashlib.sha256(preview.config_path.read_bytes()).hexdigest()
    actual_history = hashlib.sha256(preview.history_path.read_bytes()).hexdigest()
    if actual_config != expected_config:
        raise StorageImportError("Config changed after the pre-import backup.")
    if actual_history != expected_history:
        raise StorageImportError("History changed after the pre-import backup.")


def _resolve_database_path(
    config_path: Path, explicit_path: str | Path | None
) -> Path:
    if explicit_path is not None:
        return Path(explicit_path)
    configured = database_path_from_config(load_config(config_path))
    if configured.is_absolute():
        return configured
    return config_path.parent / configured
