import json
import sqlite3

import pytest

from ootp_opt.storage.backup import verify_storage_backup
from ootp_opt.storage.importer import (
    ImportVerification,
    StorageImportError,
    import_existing_state,
    verify_imported_state,
)


def test_transactional_import_backs_up_and_preserves_sources(tmp_path):
    config_path, history_path, database_path = _write_import_fixture(tmp_path)
    original_config = config_path.read_bytes()
    original_history = history_path.read_bytes()

    result = import_existing_state(
        config_path=config_path,
        history_path=history_path,
        database_path=database_path,
        backup_dir=tmp_path / "backups",
    )

    assert result.verification.passed
    assert result.verification.stored_presets == 1
    assert result.verification.stored_builds == 1
    assert result.verification.stored_artifacts == 2
    assert not result.backup.includes_database
    assert verify_storage_backup(result.backup.path).path == result.backup.path
    assert config_path.read_bytes() == original_config
    assert history_path.read_bytes() == original_history
    assert verify_imported_state(
        config_path=config_path,
        history_path=history_path,
        database_path=database_path,
    ).passed


def test_reimport_rejects_nonempty_database_after_backing_it_up(tmp_path):
    config_path, history_path, database_path = _write_import_fixture(tmp_path)
    backup_dir = tmp_path / "backups"
    import_existing_state(
        config_path=config_path,
        history_path=history_path,
        database_path=database_path,
        backup_dir=backup_dir,
    )
    backups_before = set(backup_dir.glob("*.zip"))

    with pytest.raises(StorageImportError, match="already contains"):
        import_existing_state(
            config_path=config_path,
            history_path=history_path,
            database_path=database_path,
            backup_dir=backup_dir,
        )

    new_backups = set(backup_dir.glob("*.zip")) - backups_before
    assert len(new_backups) == 1
    assert verify_storage_backup(new_backups.pop()).includes_database
    assert verify_imported_state(
        config_path=config_path,
        history_path=history_path,
        database_path=database_path,
    ).passed


def test_failed_verification_rolls_back_application_rows(tmp_path, monkeypatch):
    config_path, history_path, database_path = _write_import_fixture(tmp_path)
    failed = ImportVerification(
        expected_presets=1,
        stored_presets=0,
        expected_builds=1,
        stored_builds=0,
        expected_artifacts=2,
        stored_artifacts=0,
        preset_ids_match=False,
        build_ids_match=False,
        foreign_key_errors=0,
        integrity_check="ok",
    )
    monkeypatch.setattr(
        "ootp_opt.storage.importer._verify_connection", lambda *_: failed
    )

    with pytest.raises(StorageImportError, match="verification failed"):
        import_existing_state(
            config_path=config_path,
            history_path=history_path,
            database_path=database_path,
            backup_dir=tmp_path / "backups",
        )

    connection = sqlite3.connect(database_path)
    try:
        assert connection.execute("SELECT COUNT(*) FROM presets").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM builds").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM build_artifacts").fetchone()[0] == 0
    finally:
        connection.close()


def _write_import_fixture(tmp_path):
    config_path = tmp_path / "config.toml"
    history_path = tmp_path / "outputs" / "roster_build_registry.json"
    database_path = tmp_path / "state" / "planner.sqlite3"
    history_path.parent.mkdir()
    report_path = history_path.parent / "roster.html"
    snapshot_path = history_path.parent / "roster.snapshot.json"
    report_path.write_text("report", encoding="utf-8")
    snapshot_path.write_text("{}", encoding="utf-8")
    config_path.write_text(
        f"""
[storage]
database_path = "{database_path.as_posix()}"

[tournament_presets.test]
base_profile = "playoff_pt"
build_method = "optimizer"
tier_max = "gold"
""".strip(),
        encoding="utf-8",
    )
    history_path.write_text(
        json.dumps(
            [
                {
                    "id": "001-test",
                    "build_number": 1,
                    "created_at": "2026-08-05T12:00:00",
                    "roster_name": "Test",
                    "build_type": "pt_tournament",
                    "preset_name": "test",
                    "base_profile": None,
                    "overrides": {},
                    "html_output": str(report_path),
                    "snapshot_path": str(snapshot_path),
                    "status": "success",
                    "build_method": "optimizer",
                }
            ]
        ),
        encoding="utf-8",
    )
    return config_path, history_path, database_path
