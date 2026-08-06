import sqlite3
from dataclasses import replace

import pytest

from ootp_opt.storage import (
    BuildRecord,
    LATEST_SCHEMA_VERSION,
    MigrationError,
    PresetRecord,
    SqliteBuildRepository,
    SqlitePresetRepository,
    connect_database,
    current_schema_version,
    database_path_from_config,
    initialize_database,
    migrate_database,
)


def test_database_path_uses_default_and_config_override():
    assert database_path_from_config().as_posix() == "state/ootp_planner.sqlite3"
    assert database_path_from_config(
        {"storage": {"database_path": "custom/planner.db"}}
    ).as_posix() == "custom/planner.db"


def test_initialize_database_applies_all_migrations(tmp_path):
    database_path = tmp_path / "nested" / "planner.sqlite3"

    version = initialize_database(database_path)

    assert version == LATEST_SCHEMA_VERSION
    assert database_path.exists()

    connection = connect_database(database_path)
    try:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert {
            "schema_migrations",
            "presets",
            "builds",
            "build_players",
            "build_assignments",
            "build_artifacts",
        } <= tables
        assert current_schema_version(connection) == LATEST_SCHEMA_VERSION
    finally:
        connection.close()


def test_migrations_are_idempotent(tmp_path):
    database_path = tmp_path / "planner.sqlite3"
    initialize_database(database_path)

    connection = connect_database(database_path)
    try:
        assert migrate_database(connection) == LATEST_SCHEMA_VERSION
        migration_count = connection.execute(
            "SELECT COUNT(*) FROM schema_migrations"
        ).fetchone()[0]
        assert migration_count == LATEST_SCHEMA_VERSION
    finally:
        connection.close()


def test_foreign_keys_and_cascades_are_enabled(tmp_path):
    database_path = tmp_path / "planner.sqlite3"
    initialize_database(database_path)
    connection = connect_database(database_path)

    try:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO builds (
                    id, preset_id, roster_name, build_type, build_method, status,
                    model_version, request_json, ruleset_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "build-1",
                    "missing-preset",
                    "Test Roster",
                    "pt_tournament",
                    "optimizer",
                    "complete",
                    "test-model",
                    "{}",
                    "{}",
                ),
            )

        connection.execute(
            """
            INSERT INTO builds (
                id, roster_name, build_type, build_method, status,
                model_version, request_json, ruleset_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "build-2",
                "Test Roster",
                "standard_pt",
                "optimizer",
                "complete",
                "test-model",
                "{}",
                "{}",
            ),
        )
        connection.execute(
            """
            INSERT INTO build_players (
                build_id, card_id, player_name, player_type,
                card_snapshot_json, score_snapshot_json
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("build-2", "card-1", "Test Player", "hitter", "{}", "{}"),
        )
        connection.execute("DELETE FROM builds WHERE id = ?", ("build-2",))

        remaining = connection.execute(
            "SELECT COUNT(*) FROM build_players WHERE build_id = ?", ("build-2",)
        ).fetchone()[0]
        assert remaining == 0
    finally:
        connection.close()


def test_newer_database_schema_is_rejected(tmp_path):
    database_path = tmp_path / "planner.sqlite3"
    initialize_database(database_path)
    connection = connect_database(database_path)

    try:
        connection.execute(
            "INSERT INTO schema_migrations (version, name) VALUES (?, ?)",
            (LATEST_SCHEMA_VERSION + 1, "future_schema"),
        )
        connection.commit()

        with pytest.raises(MigrationError, match="newer than supported"):
            migrate_database(connection)
    finally:
        connection.close()


def test_sqlite_repositories_round_trip_typed_records():
    connection = connect_database(":memory:")
    migrate_database(connection)
    presets = SqlitePresetRepository(connection)
    builds = SqliteBuildRepository(connection)

    try:
        preset = presets.add(
            PresetRecord(
                id="preset-id",
                command_name="gold_test",
                display_title="Gold Test",
                note="Test note",
                base_profile="playoff_pt",
                build_method="optimizer",
                rules={"tier_max": "gold", "variant_limit": 0},
                source="config.toml",
            )
        )
        build = builds.add(
            BuildRecord(
                id="build-id",
                source_record_id="008-main-roster",
                build_number=8,
                preset_id=preset.id,
                roster_name="Main Roster",
                build_type="pt_standard",
                build_method="optimizer",
                status="success",
                model_version="test-v1",
                request={"preset_name": "gold_test"},
                ruleset={"tier_max": "gold"},
                diagnostics={"solver_status": "optimal"},
                objective_score=123.45,
                source_fingerprint="abc123",
                created_at="2026-08-05T12:00:00",
            )
        )

        assert presets.get_by_command_name("gold_test") == preset
        assert presets.list_all() == [preset]
        updated = presets.update(
            replace(
                preset,
                display_title="Updated Gold Test",
                rules={"tier_max": "diamond"},
            )
        )
        assert updated.display_title == "Updated Gold Test"
        assert updated.rules == {"tier_max": "diamond"}
        assert builds.get("build-id") == build
        assert builds.list_all(limit=1) == [build]
        with pytest.raises(ValueError, match="cannot be negative"):
            builds.list_all(limit=-1)

        presets.delete(preset.id)
        assert presets.get(preset.id) is None
        assert builds.get("build-id").preset_id is None
        with pytest.raises(KeyError, match="does not exist"):
            presets.delete(preset.id)
    finally:
        connection.close()
