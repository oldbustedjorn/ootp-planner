import json
import sqlite3
import zipfile

import pytest

from ootp_opt.storage import initialize_database
from ootp_opt.storage.backup import (
    StorageBackupError,
    create_storage_backup,
    restore_storage_backup,
    verify_storage_backup,
)


def test_backup_without_database_preserves_sources(tmp_path):
    config_path, history_path = _write_sources(tmp_path)

    backup = create_storage_backup(
        config_path=config_path,
        history_path=history_path,
        database_path=tmp_path / "missing.sqlite3",
        backup_dir=tmp_path / "backups",
        purpose="test",
    )
    verified = verify_storage_backup(backup.path)

    assert not verified.includes_database
    with zipfile.ZipFile(backup.path) as archive:
        assert archive.read("source/config.toml") == config_path.read_bytes()
        assert archive.read("source/roster_build_registry.json") == history_path.read_bytes()


def test_database_backup_and_restore_with_safety_backup(tmp_path):
    config_path, history_path = _write_sources(tmp_path)
    database_path = tmp_path / "state" / "planner.sqlite3"
    initialize_database(database_path)
    _insert_test_preset(database_path, "before")
    backup = create_storage_backup(
        config_path=config_path,
        history_path=history_path,
        database_path=database_path,
        backup_dir=tmp_path / "backups",
        purpose="test",
    )
    assert backup.includes_database

    _insert_test_preset(database_path, "after")
    original_config = config_path.read_bytes()
    original_history = history_path.read_bytes()
    result = restore_storage_backup(
        backup.path,
        config_path=config_path,
        history_path=history_path,
        database_path=database_path,
        backup_dir=tmp_path / "backups",
    )

    assert result.database_restored
    assert not result.sources_restored
    assert result.safety_backup_path is not None
    assert verify_storage_backup(result.safety_backup_path).includes_database
    assert _preset_names(database_path) == ["before"]
    assert config_path.read_bytes() == original_config
    assert history_path.read_bytes() == original_history


def test_restore_can_include_config_and_history(tmp_path):
    config_path, history_path = _write_sources(tmp_path)
    database_path = tmp_path / "state" / "planner.sqlite3"
    initialize_database(database_path)
    backup = create_storage_backup(
        config_path=config_path,
        history_path=history_path,
        database_path=database_path,
        backup_dir=tmp_path / "backups",
    )
    expected_config = config_path.read_bytes()
    expected_history = history_path.read_bytes()
    config_path.write_text("changed", encoding="utf-8")
    history_path.write_text("[]", encoding="utf-8")

    result = restore_storage_backup(
        backup.path,
        config_path=config_path,
        history_path=history_path,
        database_path=database_path,
        backup_dir=tmp_path / "backups",
        include_sources=True,
    )

    assert result.sources_restored
    assert config_path.read_bytes() == expected_config
    assert history_path.read_bytes() == expected_history


def test_backup_verification_rejects_tampered_member(tmp_path):
    config_path, history_path = _write_sources(tmp_path)
    backup = create_storage_backup(
        config_path=config_path,
        history_path=history_path,
        database_path=tmp_path / "missing.sqlite3",
        backup_dir=tmp_path / "backups",
    )
    tampered = tmp_path / "tampered.zip"
    with zipfile.ZipFile(backup.path) as source, zipfile.ZipFile(tampered, "w") as target:
        for name in source.namelist():
            contents = source.read(name)
            if name == "source/config.toml":
                contents = b"tampered"
            target.writestr(name, contents)

    with pytest.raises(StorageBackupError, match="mismatch"):
        verify_storage_backup(tampered)


def _write_sources(tmp_path):
    config_path = tmp_path / "config.toml"
    history_path = tmp_path / "outputs" / "roster_build_registry.json"
    history_path.parent.mkdir()
    config_path.write_text("[storage]\n", encoding="utf-8")
    history_path.write_text(json.dumps([{"id": "one"}]), encoding="utf-8")
    return config_path, history_path


def _insert_test_preset(database_path, command_name):
    connection = sqlite3.connect(database_path)
    try:
        connection.execute(
            """
            INSERT INTO presets (
                id, command_name, base_profile, build_method, rules_json
            ) VALUES (?, ?, 'playoff_pt', 'optimizer', '{}')
            """,
            (command_name, command_name),
        )
        connection.commit()
    finally:
        connection.close()


def _preset_names(database_path):
    connection = sqlite3.connect(database_path)
    try:
        return [
            row[0]
            for row in connection.execute(
                "SELECT command_name FROM presets ORDER BY command_name"
            )
        ]
    finally:
        connection.close()
