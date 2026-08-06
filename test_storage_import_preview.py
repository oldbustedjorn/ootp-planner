import json

from ootp_opt.storage.import_preview import (
    preview_existing_state,
    render_import_preview,
)


def test_preview_is_read_only_and_assigns_unique_build_ids(tmp_path):
    database_path = tmp_path / "state" / "planner.sqlite3"
    config_path = tmp_path / "config.toml"
    history_path = tmp_path / "history.json"
    config_path.write_text(
        f"""
[storage]
database_path = "{database_path.as_posix()}"

[tournament_presets.gold_test]
base_profile = "playoff_pt"
build_method = "optimizer"
tier_max = "gold"
_gui_title = "Gold Test"
""".strip(),
        encoding="utf-8",
    )
    history_path.write_text(
        json.dumps(
            [
                {
                    "id": "008-main",
                    "build_number": 8,
                    "created_at": "2026-08-04T12:00:00",
                    "roster_name": "Main",
                    "build_type": "pt_standard",
                    "preset_name": "gold_test",
                    "overrides": {},
                    "status": "success",
                    "build_method": "optimizer",
                },
                {
                    "id": "008-main",
                    "build_number": 8,
                    "created_at": "2026-08-05T12:00:00",
                    "roster_name": "Main",
                    "build_type": "pt_standard",
                    "preset_name": "gold_test",
                    "overrides": {},
                    "status": "success",
                    "build_method": "optimizer",
                },
            ]
        ),
        encoding="utf-8",
    )

    preview = preview_existing_state(config_path, history_path)
    repeated_preview = preview_existing_state(config_path, history_path)

    assert len(preview.presets) == 1
    assert len(preview.builds) == 2
    assert preview.error_count == 0
    assert preview.warning_count == 1
    assert len({candidate.record.id for candidate in preview.builds}) == 2
    assert [candidate.record.id for candidate in preview.builds] == [
        candidate.record.id for candidate in repeated_preview.builds
    ]
    assert not database_path.exists()
    assert "No database was created or modified." in render_import_preview(preview)


def test_preview_reports_invalid_and_orphaned_records(tmp_path):
    config_path = tmp_path / "config.toml"
    history_path = tmp_path / "history.json"
    config_path.write_text(
        """
[tournament_presets.valid]
base_profile = "playoff_pt"

[tournament_presets.invalid]
build_method = "optimizer"
""".strip(),
        encoding="utf-8",
    )
    history_path.write_text(
        json.dumps(
            [
                {
                    "id": "orphan",
                    "roster_name": "Old Roster",
                    "build_type": "pt_tournament",
                    "preset_name": "deleted_preset",
                    "status": "success",
                    "build_method": "optimizer",
                },
                {"id": "invalid", "roster_name": "Missing Type"},
            ]
        ),
        encoding="utf-8",
    )

    preview = preview_existing_state(config_path, history_path)

    assert [preset.command_name for preset in preview.presets] == ["valid"]
    assert [candidate.record.source_record_id for candidate in preview.builds] == [
        "orphan"
    ]
    assert preview.error_count == 2
    assert preview.warning_count == 1


def test_preview_handles_missing_history_registry(tmp_path):
    config_path = tmp_path / "config.toml"
    config_path.write_text("", encoding="utf-8")

    preview = preview_existing_state(config_path, tmp_path / "missing.json")

    assert preview.builds == ()
    assert preview.error_count == 0
    assert preview.warning_count == 1
