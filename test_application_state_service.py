from pathlib import Path

import pytest

from ootp_opt.services.application_state_service import (
    ApplicationStateError,
    add_application_preset_from_build,
    append_application_build_record,
    archive_application_roster_plan,
    create_application_roster_plan,
    delete_application_preset,
    get_application_roster_plan,
    list_application_roster_plans,
    list_base_profile_templates,
    load_application_build_records,
    load_runtime_config,
    rename_application_roster_plan,
    update_application_roster_plan,
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
hitter_count = 14
pitcher_count = 12
dh_enabled = true
platoons_allowed = true
lineup_fill_order = ["C"]
rotation_size = 4
primary_rp_count = 6
specialist_lhp_count = 1
long_man_count = 1
bench_roles = []

[roster_base_profiles.playoff_pt.bench_role_requirements.UTIL]
required_positions_any = ["C"]
required_positions = []
preferred_positions = ["C"]

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
        "_roster_plan_status": "active",
        "_roster_plan_type": "pt_tournament",
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


def test_delete_application_roster_plan_removes_its_build_history(tmp_path):
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
    assert builds == []


def test_roster_plan_lifecycle_preserves_invalid_draft_and_stable_id(tmp_path):
    config_path = write_config(tmp_path)
    initialize_database(tmp_path / "planner.sqlite3")

    draft = create_application_roster_plan(
        config_path=config_path,
        plan_key="new diamond roster",
        display_title="Daily Diamond",
        plan_type="pt_tournament",
        base_profile="playoff_pt",
        build_method="optimizer",
        rules={"ballpark": "Not A Real Park", "ballpark_year": 1955},
    )

    assert draft.lifecycle_status == "draft"
    assert "ballpark" in draft.validation_errors
    original_id = draft.id

    corrected, validation = update_application_roster_plan(
        config_path=config_path,
        plan_name=draft.command_name,
        base_profile="playoff_pt",
        plan_type="pt_tournament",
        build_method="optimizer",
        rules={"tier_max": "diamond"},
    )
    renamed = rename_application_roster_plan(
        config_path=config_path,
        plan_name=draft.command_name,
        display_title="Diamond Quick",
    )

    assert validation.is_valid
    assert corrected.id == original_id
    assert corrected.validation_errors == {}
    assert renamed.id == original_id
    assert renamed.display_title == "Diamond Quick"
    assert set(list_base_profile_templates(config_path)) == {"playoff_pt"}

    archived = archive_application_roster_plan(
        config_path=config_path,
        plan_name=draft.command_name,
    )
    assert archived.lifecycle_status == "archived"
    assert list_application_roster_plans(config_path) == []
    assert len(list_application_roster_plans(config_path, include_archived=True)) == 1
    assert draft.command_name not in load_runtime_config(config_path)[
        "tournament_presets"
    ]


def test_planless_build_run_automatically_creates_roster_plan(tmp_path):
    config_path = write_config(tmp_path)
    initialize_database(tmp_path / "planner.sqlite3")

    record = append_application_build_record(
        config_path=config_path,
        build_number=31,
        roster_name="T-031-Gmax",
        build_type="pt_tournament",
        preset_name=None,
        base_profile="playoff_pt",
        overrides={"tier_max": "gold"},
        html_output="outputs/roster.html",
        snapshot_path="outputs/roster.snapshot.json",
        status="success",
        build_method="optimizer",
    )

    assert record["preset_name"].startswith("roster_031_")
    plan = get_application_roster_plan(config_path, record["preset_name"])
    assert plan.lifecycle_status == "active"
    assert plan.rules["tier_max"] == "gold"
    assert load_application_build_records(config_path)[0]["preset_name"] == plan.command_name
