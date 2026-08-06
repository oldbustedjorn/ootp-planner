from pathlib import Path

import pytest

from ootp_opt.services.application_state_service import (
    ApplicationStateError,
    add_application_preset_from_build,
    append_application_build_record,
    delete_application_preset,
    load_application_build_records,
    load_runtime_config,
    update_application_preset_build_method,
    update_application_preset_notes,
)
from ootp_opt.storage import (
    PresetRecord,
    SqlitePresetRepository,
    connect_database,
    initialize_database,
)


def write_config(tmp_path: Path, database_name: str = "planner.sqlite3") -> Path:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        f'''
[storage]
database_path = "{database_name}"

[paths]
output_dir = "outputs"

[roster_base_profiles.playoff_pt]
mode = "playoff_pt"

[tournament_presets.stale_toml]
base_profile = "playoff_pt"
tier_max = "bronze"
'''.strip()
        + "\n",
        encoding="utf-8",
    )
    return config_path


def seed_preset(database_path: Path) -> PresetRecord:
    initialize_database(database_path)
    connection = connect_database(database_path)
    try:
        preset = SqlitePresetRepository(connection).add(
            PresetRecord(
                id="preset-1",
                command_name="sqlite_gold",
                display_title="SQLite Gold",
                note="Stored in SQLite",
                base_profile="playoff_pt",
                build_method="optimizer",
                rules={"tier_max": "gold", "variant_limit": 0},
                source="test",
            )
        )
        connection.commit()
        return preset
    finally:
        connection.close()


def test_runtime_config_uses_sqlite_presets_and_keeps_static_toml(tmp_path):
    config_path = write_config(tmp_path)
    seed_preset(tmp_path / "planner.sqlite3")

    config = load_runtime_config(config_path)

    assert config["paths"] == {"output_dir": "outputs"}
    assert set(config["tournament_presets"]) == {"sqlite_gold"}
    assert config["tournament_presets"]["sqlite_gold"] == {
        "tier_max": "gold",
        "variant_limit": 0,
        "base_profile": "playoff_pt",
        "build_method": "optimizer",
        "_gui_title": "SQLite Gold",
        "_gui_note": "Stored in SQLite",
    }


def test_application_state_requires_an_imported_database(tmp_path):
    config_path = write_config(tmp_path)

    with pytest.raises(ApplicationStateError, match="import_storage.py --apply"):
        load_application_build_records(config_path)


def test_preset_edits_and_build_history_write_only_to_sqlite(tmp_path):
    config_path = write_config(tmp_path)
    database_path = tmp_path / "planner.sqlite3"
    seed_preset(database_path)
    original_config = config_path.read_bytes()

    update_application_preset_notes(
        config_path=config_path,
        preset_name="sqlite_gold",
        title="Gold Daily",
        note="Server slot 4",
    )
    update_application_preset_build_method(
        config_path=config_path,
        preset_name="sqlite_gold",
        build_method="greedy",
    )
    record = append_application_build_record(
        config_path=config_path,
        build_number=21,
        roster_name="T-021-Gmax",
        build_type="pt_tournament",
        preset_name="sqlite_gold",
        base_profile=None,
        overrides={},
        html_output=Path("outputs/preset_roster_sqlite_gold.html"),
        snapshot_path=Path("outputs/preset_roster_sqlite_gold.snapshot.json"),
        status="success",
        build_method="greedy",
        objective_score=123.5,
        diagnostics={"total_seconds": 2.25},
    )

    assert config_path.read_bytes() == original_config
    runtime = load_runtime_config(config_path)
    preset = runtime["tournament_presets"]["sqlite_gold"]
    assert preset["_gui_title"] == "Gold Daily"
    assert preset["_gui_note"] == "Server slot 4"
    assert preset["build_method"] == "greedy"
    assert record["id"]
    assert record["html_output"].endswith("preset_roster_sqlite_gold.html")
    assert isinstance(record["html_output"], str)
    assert isinstance(record["snapshot_path"], str)
    assert record["objective_score"] == 123.5
    assert load_application_build_records(config_path)[0]["id"] == record["id"]


def test_add_and_delete_application_preset_preserves_build_history(tmp_path):
    config_path = write_config(tmp_path)
    database_path = tmp_path / "planner.sqlite3"
    initialize_database(database_path)
    history_record = {
        "build_number": 7,
        "roster_name": "T-007-Smax",
        "build_type": "pt_tournament",
        "base_profile": "playoff_pt",
        "overrides": {"tier_max": "silver"},
        "build_method": "optimizer",
        "html_output": "outputs/gui_t_007_smax.html",
    }

    created = add_application_preset_from_build(
        config_path=config_path,
        record=history_record,
        preset_name="saved silver",
    )
    append_application_build_record(
        config_path=config_path,
        build_number=7,
        roster_name="T-007-Smax",
        build_type="pt_tournament",
        preset_name=created.command_name,
        base_profile=None,
        overrides={},
        html_output="outputs/preset_roster_saved_silver.html",
        snapshot_path="outputs/preset_roster_saved_silver.snapshot.json",
        status="success",
        build_method="optimizer",
    )

    assert created.command_name == "saved_silver"
    assert (
        load_runtime_config(config_path)["tournament_presets"]["saved_silver"][
            "tier_max"
        ]
        == "silver"
    )

    deleted_files = delete_application_preset(
        config_path=config_path,
        preset_name="saved_silver",
    )

    assert deleted_files == []
    assert load_runtime_config(config_path)["tournament_presets"] == {}
    builds = load_application_build_records(config_path)
    assert len(builds) == 1
    assert builds[0]["preset_name"] == "saved_silver"
