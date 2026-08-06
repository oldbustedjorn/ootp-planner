from __future__ import annotations

import hashlib
import json
import sqlite3
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

BACKUP_FORMAT_VERSION = 1
CONFIG_MEMBER = "source/config.toml"
HISTORY_MEMBER = "source/roster_build_registry.json"
DATABASE_MEMBER = "database/ootp_planner.sqlite3"
MANIFEST_MEMBER = "storage_manifest.json"


class StorageBackupError(RuntimeError):
    """Raised when a storage backup cannot be created, verified, or restored."""


@dataclass(frozen=True, slots=True)
class StorageBackup:
    path: Path
    manifest: dict[str, Any]

    @property
    def includes_database(self) -> bool:
        return bool(self.manifest.get("database", {}).get("included"))


@dataclass(frozen=True, slots=True)
class StorageRestoreResult:
    archive_path: Path
    database_restored: bool
    sources_restored: bool
    safety_backup_path: Path | None


def create_storage_backup(
    *,
    config_path: str | Path,
    history_path: str | Path,
    database_path: str | Path,
    backup_dir: str | Path = "state/backups",
    purpose: str = "manual",
) -> StorageBackup:
    config_path = Path(config_path)
    history_path = Path(history_path)
    database_path = Path(database_path)
    backup_dir = Path(backup_dir)
    config_bytes = _required_bytes(config_path, "config")
    history_bytes = _required_bytes(history_path, "history registry")
    backup_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup_path = backup_dir / f"storage_{purpose}_{timestamp}.zip"
    temporary_archive = backup_path.with_suffix(".zip.tmp")
    temporary_database = backup_dir / f".database_{uuid4().hex}.sqlite3"
    database_included = database_path.is_file()

    try:
        if database_included:
            _backup_database(database_path, temporary_database)
        manifest = _build_manifest(
            purpose=purpose,
            config_bytes=config_bytes,
            history_bytes=history_bytes,
            database_path=temporary_database if database_included else None,
        )
        with zipfile.ZipFile(
            temporary_archive, mode="w", compression=zipfile.ZIP_DEFLATED
        ) as archive:
            archive.writestr(CONFIG_MEMBER, config_bytes)
            archive.writestr(HISTORY_MEMBER, history_bytes)
            if database_included:
                archive.write(temporary_database, DATABASE_MEMBER)
            archive.writestr(MANIFEST_MEMBER, json.dumps(manifest, indent=2))
        verified = verify_storage_backup(temporary_archive)
        temporary_archive.replace(backup_path)
        return StorageBackup(path=backup_path, manifest=verified.manifest)
    except StorageBackupError:
        temporary_archive.unlink(missing_ok=True)
        raise
    except (OSError, sqlite3.Error, zipfile.BadZipFile) as exc:
        temporary_archive.unlink(missing_ok=True)
        raise StorageBackupError(f"Could not create storage backup: {exc}") from exc
    finally:
        temporary_database.unlink(missing_ok=True)


def verify_storage_backup(archive_path: str | Path) -> StorageBackup:
    archive_path = Path(archive_path)
    try:
        with zipfile.ZipFile(archive_path) as archive:
            damaged_member = archive.testzip()
            if damaged_member is not None:
                raise StorageBackupError(
                    f"Backup contains a damaged member: {damaged_member}."
                )
            names = set(archive.namelist())
            required = {CONFIG_MEMBER, HISTORY_MEMBER, MANIFEST_MEMBER}
            missing = required - names
            if missing:
                raise StorageBackupError(
                    f"Backup is missing required members: {sorted(missing)}."
                )
            manifest = json.loads(archive.read(MANIFEST_MEMBER))
            if manifest.get("format_version") != BACKUP_FORMAT_VERSION:
                raise StorageBackupError(
                    f"Unsupported backup format: {manifest.get('format_version')}."
                )
            _verify_member_hash(archive, manifest, "config", CONFIG_MEMBER)
            _verify_member_hash(archive, manifest, "history", HISTORY_MEMBER)
            database_info = manifest.get("database", {})
            if database_info.get("included"):
                if DATABASE_MEMBER not in names:
                    raise StorageBackupError("Manifest database member is missing.")
                _verify_member_hash(
                    archive, manifest, "database", DATABASE_MEMBER
                )
            elif DATABASE_MEMBER in names:
                raise StorageBackupError(
                    "Backup has a database member not declared by its manifest."
                )
    except StorageBackupError:
        raise
    except (OSError, KeyError, json.JSONDecodeError, zipfile.BadZipFile) as exc:
        raise StorageBackupError(f"Could not verify storage backup: {exc}") from exc
    return StorageBackup(path=archive_path, manifest=manifest)


def restore_storage_backup(
    archive_path: str | Path,
    *,
    config_path: str | Path,
    history_path: str | Path,
    database_path: str | Path,
    backup_dir: str | Path = "state/backups",
    include_sources: bool = False,
) -> StorageRestoreResult:
    archive = verify_storage_backup(archive_path)
    config_path = Path(config_path)
    history_path = Path(history_path)
    database_path = Path(database_path)
    safety_backup = create_storage_backup(
        config_path=config_path,
        history_path=history_path,
        database_path=database_path,
        backup_dir=backup_dir,
        purpose="pre_restore",
    )
    database_restored = False
    sources_restored = False
    temporary_database = Path(backup_dir) / f".restore_{uuid4().hex}.sqlite3"

    try:
        with zipfile.ZipFile(archive.path) as source_archive:
            if archive.includes_database:
                temporary_database.write_bytes(source_archive.read(DATABASE_MEMBER))
                _assert_database_integrity(temporary_database)
                _restore_database(temporary_database, database_path)
                database_restored = True
            if include_sources:
                _write_bytes_atomically(
                    config_path, source_archive.read(CONFIG_MEMBER)
                )
                _write_bytes_atomically(
                    history_path, source_archive.read(HISTORY_MEMBER)
                )
                sources_restored = True
    except (OSError, sqlite3.Error, zipfile.BadZipFile) as exc:
        raise StorageBackupError(f"Could not restore storage backup: {exc}") from exc
    finally:
        temporary_database.unlink(missing_ok=True)

    return StorageRestoreResult(
        archive_path=archive.path,
        database_restored=database_restored,
        sources_restored=sources_restored,
        safety_backup_path=safety_backup.path,
    )


def _backup_database(source_path: Path, destination_path: Path) -> None:
    source = sqlite3.connect(f"{source_path.resolve().as_uri()}?mode=ro", uri=True)
    destination = sqlite3.connect(destination_path)
    try:
        source.backup(destination)
    finally:
        destination.close()
        source.close()
    _assert_database_integrity(destination_path)


def _restore_database(source_path: Path, destination_path: Path) -> None:
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    source = sqlite3.connect(f"{source_path.resolve().as_uri()}?mode=ro", uri=True)
    destination = sqlite3.connect(destination_path)
    try:
        source.backup(destination)
        integrity = destination.execute("PRAGMA integrity_check").fetchone()
        if integrity is None or integrity[0] != "ok":
            raise StorageBackupError(
                f"Restored database failed integrity check: {integrity}."
            )
    finally:
        destination.close()
        source.close()


def _assert_database_integrity(database_path: Path) -> None:
    connection = sqlite3.connect(
        f"{database_path.resolve().as_uri()}?mode=ro", uri=True
    )
    try:
        result = connection.execute("PRAGMA integrity_check").fetchone()
    finally:
        connection.close()
    if result is None or result[0] != "ok":
        raise StorageBackupError(
            f"Database failed integrity check: {database_path}: {result}."
        )


def _build_manifest(
    *,
    purpose: str,
    config_bytes: bytes,
    history_bytes: bytes,
    database_path: Path | None,
) -> dict[str, Any]:
    database_bytes = database_path.read_bytes() if database_path else None
    return {
        "format_version": BACKUP_FORMAT_VERSION,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "purpose": purpose,
        "config": _member_manifest(CONFIG_MEMBER, config_bytes),
        "history": _member_manifest(HISTORY_MEMBER, history_bytes),
        "database": {
            "included": database_bytes is not None,
            **(
                _member_manifest(DATABASE_MEMBER, database_bytes)
                if database_bytes is not None
                else {}
            ),
        },
    }


def _member_manifest(member: str, contents: bytes) -> dict[str, Any]:
    return {
        "member": member,
        "size": len(contents),
        "sha256": hashlib.sha256(contents).hexdigest(),
    }


def _verify_member_hash(
    archive: zipfile.ZipFile,
    manifest: dict[str, Any],
    key: str,
    member: str,
) -> None:
    contents = archive.read(member)
    expected = manifest.get(key, {})
    if expected.get("member") != member:
        raise StorageBackupError(f"Manifest member mismatch for {key}.")
    if expected.get("size") != len(contents):
        raise StorageBackupError(f"Backup size mismatch for {key}.")
    if expected.get("sha256") != hashlib.sha256(contents).hexdigest():
        raise StorageBackupError(f"Backup hash mismatch for {key}.")


def _required_bytes(path: Path, label: str) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        raise StorageBackupError(f"Cannot read {label} at {path}: {exc}") from exc


def _write_bytes_atomically(path: Path, contents: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".restore.tmp")
    try:
        temporary.write_bytes(contents)
        temporary.replace(path)
    except OSError:
        temporary.unlink(missing_ok=True)
        raise
