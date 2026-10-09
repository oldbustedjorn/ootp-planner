from pathlib import Path
import json
from http.server import ThreadingHTTPServer
from threading import Thread
from urllib.request import urlopen

import ootp_opt.gui.server as gui_server

from ootp_opt.gui.server import (
    MAX_OOTP_ROSTER_NAME_LENGTH,
    PlannerHTTPServer,
    build_auto_roster_name,
    build_gui_request,
    build_overrides_from_form,
    render_presets_panel,
)
from ootp_opt.services.preset_service import (
    append_history_record_as_preset,
    delete_preset,
    delete_preset_block,
    preset_owned_output_paths,
    preset_roster_output_path,
    preset_upgrade_output_path,
    resolve_preset_build_metadata,
    slugify,
    update_preset_notes,
    update_preset_build_method,
)


def form(**kwargs):
    return {
        key: value if isinstance(value, list) else [str(value)]
        for key, value in kwargs.items()
    }


def test_automation_status_endpoint_reports_current_contract():
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0),
        gui_server.build_handler(config_path="config.toml"),
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with urlopen(
            f"http://127.0.0.1:{server.server_port}/automation-status",
            timeout=3,
        ) as response:
            status = json.load(response)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)

    assert status["automation_contract_version"] == 13
    assert status["ui_plan_schema_version"] == 15
    assert status["features"]["single_calibration_batching"] is True
    assert status["features"]["checkpoint_repair_gate"] is True
    assert status["features"]["targeted_repair_retries"] is True
    assert status["features"]["split_pinch_calibration"] is True
    assert status["features"]["distinct_repair_strategies"] is True
    assert status["features"]["in_place_assignment_pause"] is True
    assert status["features"]["drag_capability_preflight"] is True
    assert status["features"]["drag_gesture_fail_fast"] is True
    assert status["features"]["context_menu_lineup_assignment"] is False
    assert status["features"]["context_menu_isolated_repair_only"] is True
    assert status["features"]["lower_pane_drag_sources"] is True
    assert status["features"]["upper_list_drag_disabled"] is False
    assert status["features"]["failed_preflight_manual_handoff"] is True
    assert status["features"]["windows_held_drag"] is True
    assert status["features"]["upper_pitcher_list_drag"] is True
    assert status["features"]["player_name_drag_source"] is True
    assert status["features"]["local_assignment_captures"] is True
    assert status["features"]["native_drag_batches"] is True
    assert status["features"]["card_subtype_constraints"] is True


def test_planner_server_disables_shared_port_reuse():
    assert PlannerHTTPServer.allow_reuse_address is False


def test_standard_pt_gui_request_uses_standard_profile():
    request = build_gui_request(
        form(
            roster_name="Main PT",
            build_type="pt_standard",
            simulation_year="1965",
        )
    )

    assert request.roster_name == "Main PT"
    assert request.roster_request.base_profile == "standard_pt"
    assert request.roster_request.preset is None
    assert request.roster_request.overrides == {"simulation_year": 1965}
    assert request.roster_request.build_method == "greedy"


def test_gui_request_accepts_optimizer_build_method():
    request = build_gui_request(
        form(
            roster_name="Optimized PT",
            build_type="pt_standard",
            build_method="optimizer",
        )
    )

    assert request.roster_request.build_method == "optimizer"
    assert request.roster_request.roster_name == "Optimized PT"


def test_render_home_preserves_submitted_build_form_after_error(monkeypatch):
    monkeypatch.setattr(
        gui_server,
        "load_runtime_config",
        lambda _config_path: {"tournament_presets": {}},
    )
    monkeypatch.setattr(
        gui_server,
        "load_application_build_records",
        lambda _config_path: [],
    )

    html = gui_server.render_home(
        "config.toml",
        error="Unknown ballpark",
        form_values=form(
            roster_name="My New Roster",
            build_type="pt_tournament",
            build_method="optimizer",
            base_profile="playoff_pt",
            scoring_environment="diamond",
            simulation_year="1959",
            ballpark="Imaginary Park",
            ballpark_year="1959",
            ba_lh="1.05",
            tier_max="diamond",
            card_value_max="99",
            allowed_card_types=["UnH", "Snap"],
            excluded_card_subtypes=["LE"],
            slot_D="2",
        ),
    )

    assert 'name="roster_name" value="My New Roster"' in html
    assert '<option value="pt_tournament" selected>' in html
    assert '<option value="optimizer" selected>' in html
    assert '<option value="playoff_pt" selected>' in html
    assert '<option value="diamond" selected>' in html
    assert 'name="simulation_year" value="1959"' in html
    assert 'name="ballpark" value="Imaginary Park"' in html
    assert 'name="ballpark_year" value="1959"' in html
    assert "<details open>" in html
    assert 'name="ba_lh" value="1.05"' in html
    assert 'name="card_value_max" value="99"' in html
    assert 'value="UnH" checked' in html
    assert 'value="Snap" checked' in html
    assert 'name="excluded_card_subtypes" value="LE" checked' in html
    assert 'name="slot_D" value="2"' in html


def test_blank_standard_pt_roster_name_is_auto_named():
    request = build_gui_request(
        form(
            roster_name="",
            build_type="pt_standard",
            simulation_year="1965",
        ),
        build_number=42,
    )

    assert request.roster_name == "PT-042-Y1965"


def test_tournament_gui_request_maps_restrictions():
    request = build_gui_request(
        form(
            roster_name="Gold Daily",
            build_type="pt_tournament",
            base_profile="playoff_pt",
            tier_max="gold",
            live_mode="non_live",
            card_value_max="84",
            variant_limit="0",
            allowed_card_types=["UnH", "Snap", "RS"],
            excluded_card_subtypes=["LE"],
            slot_P="1",
            slot_D="2",
        )
    )

    assert request.roster_request.base_profile == "playoff_pt"
    assert request.roster_request.overrides["tier_max"] == "gold"
    assert request.roster_request.overrides["live_mode"] == "non_live"
    assert request.roster_request.overrides["card_value_max"] == 84
    assert request.roster_request.overrides["variant_limit"] == 0
    assert request.roster_request.overrides["allowed_card_types"] == [
        "UnH",
        "Snap",
        "RS",
    ]
    assert request.roster_request.overrides["excluded_card_subtypes"] == ["LE"]
    assert request.roster_request.overrides["tier_slots"] == {"P": 1, "D": 2}


def test_blank_tournament_roster_name_uses_compact_requirements():
    request = build_gui_request(
        form(
            roster_name="",
            build_type="pt_tournament",
            base_profile="playoff_pt",
            tier_max="gold",
            live_mode="non_live",
            card_value_max="84",
            allowed_card_types=["UnH", "Snap", "RS"],
            simulation_year="1999",
            dh_enabled="true",
        ),
        build_number=42,
    )

    assert request.roster_name == "T-042-Gmax-v84-NL-Y1999-DH"
    assert len(request.roster_name) <= MAX_OOTP_ROSTER_NAME_LENGTH


def test_blank_variant_limit_is_not_sent_as_override():
    overrides = build_overrides_from_form(
        form(build_type="pt_tournament", variant_limit=""),
        include_tournament=True,
    )

    assert "variant_limit" not in overrides


def test_preset_gui_request_uses_preset_instead_of_base_profile():
    request = build_gui_request(
        form(
            roster_name="Preset run",
            build_type="pt_tournament",
            base_profile="playoff_pt",
            preset_name="bronze_nonlive",
        )
    )

    assert request.roster_request.preset == "bronze_nonlive"
    assert request.roster_request.base_profile is None


def test_blank_preset_roster_name_includes_reference_number():
    request = build_gui_request(
        form(
            roster_name="",
            build_type="pt_tournament",
            base_profile="playoff_pt",
            preset_name="bronze_nonlive",
        ),
        build_number=42,
    )

    assert request.roster_name == "T-042-B-nonlive"


def test_auto_roster_name_is_capped_at_30_characters():
    name = build_auto_roster_name(
        build_type="pt_tournament",
        base_profile="playoff_pt",
        build_number=42,
        preset_name=None,
        overrides={
            "tier_min": "bronze",
            "tier_max": "diamond",
            "allowed_card_types": ["UnH", "Snap", "RS", "HaH"],
            "card_year_min": 1930,
            "card_year_max": 1989,
            "simulation_year": 1958,
            "point_cap_total": 1699,
        },
    )

    assert len(name) <= MAX_OOTP_ROSTER_NAME_LENGTH


def test_preset_output_paths_are_stable():
    assert (
        preset_roster_output_path("bronze_nonlive")
        == "outputs\\preset_roster_bronze_nonlive.html"
    )
    assert (
        preset_upgrade_output_path("bronze_nonlive")
        == "outputs\\preset_upgrades_bronze_nonlive.html"
    )


def test_render_presets_panel_includes_actions():
    html = render_presets_panel(
        {
            "tournament_presets": {
                "bronze_nonlive": {
                    "_gui_title": "Bronze Quick",
                    "_gui_note": "Bronze quick tournament",
                    "base_profile": "playoff_pt",
                    "tier_max": "bronze",
                    "live_mode": "non_live",
                }
            }
        },
        ["bronze_nonlive"],
        "bronze_nonlive",
    )

    assert "bronze_nonlive" in html
    assert "Bronze Quick" in html
    assert "Bronze quick tournament" in html
    assert 'action="/preset-build"' in html
    assert 'action="/preset-upgrades"' in html
    assert 'action="/preset-notes"' in html
    assert 'action="/preset-delete"' in html
    assert "Build Roster" in html
    assert "Find Upgrades" in html
    assert 'name="exact_results"' in html
    assert 'name="max_price"' in html
    assert 'name="require_sell_order"' in html
    assert "Save Notes" in html
    assert "Roster Plans" in html
    assert "Delete Roster Plan" in html
    assert "&lt;=bronze" in html


def test_append_history_record_as_preset_writes_valid_toml():
    config_path = Path("outputs/test_append_history_config.toml")
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        """
[roster]
default_base_profile = "standard_pt"

[roster_build_defaults]

[roster_base_profiles.playoff_pt]
mode = "playoff_pt"
hitter_count = 14
pitcher_count = 12
dh_enabled = true
platoons_allowed = false
lineup_fill_order = ["C"]
rotation_size = 4
primary_rp_count = 6
specialist_lhp_count = 1
long_man_count = 1
bench_roles = []

[tournament_presets.existing]
base_profile = "playoff_pt"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    append_history_record_as_preset(
        config_path=config_path,
        record={
            "roster_name": "T-006-Smax-Y1986-NoDH",
            "base_profile": "playoff_pt",
            "overrides": {
                "dh_enabled": False,
                "tier_max": "silver",
                "allowed_card_types": ["UnH", "Snap"],
                "tier_slots": {"P": 1, "D": 1},
            },
            "build_method": "optimizer",
        },
        preset_name="saved_from_history",
    )

    text = config_path.read_text(encoding="utf-8")
    assert "[tournament_presets.saved_from_history]" in text
    assert "dh_enabled = false" in text
    assert 'allowed_card_types = ["UnH", "Snap"]' in text
    assert "[tournament_presets.saved_from_history.tier_slots]" in text
    assert '_gui_roster_name = "T-006-Smax-Y1986-NoDH"' in text
    assert 'build_method = "optimizer"' in text


def test_saved_history_preset_metadata_reuses_original_roster_identity():
    metadata = resolve_preset_build_metadata(
        preset_name="saved_from_history",
        preset_cfg={
            "base_profile": "standard_pt",
            "_gui_roster_name": "Standard PT Regular Season",
            "_gui_build_type": "pt_standard",
            "_gui_build_number": 8,
            "_gui_html_output": "outputs\\gui_standard_pt_regular_season.html",
        },
        records=[],
    )

    assert metadata == {
        "roster_name": "Standard PT Regular Season",
        "build_type": "pt_standard",
        "build_number": 8,
        "html_output": "outputs\\gui_standard_pt_regular_season.html",
    }


def test_legacy_history_preset_recovers_original_roster_identity_from_registry():
    metadata = resolve_preset_build_metadata(
        preset_name="preset_008_standard_pt_regular_season",
        preset_cfg={"base_profile": "standard_pt"},
        records=[
            {
                "build_number": 9,
                "roster_name": "T-009",
                "build_type": "pt_tournament",
                "preset_name": "preset_008_standard_pt_regular_season",
                "html_output": "outputs\\preset_roster_preset_008_standard_pt_regular_season.html",
            },
            {
                "build_number": 8,
                "roster_name": "Standard PT Regular Season",
                "build_type": "pt_standard",
                "preset_name": None,
                "html_output": "outputs\\gui_standard_pt_regular_season_20260627_202711.html",
            },
        ],
    )

    assert metadata["roster_name"] == "Standard PT Regular Season"
    assert metadata["build_type"] == "pt_standard"
    assert metadata["build_number"] == 8
    assert (
        metadata["html_output"]
        == "outputs\\gui_standard_pt_regular_season_20260627_202711.html"
    )


def test_update_preset_notes_writes_and_clears_metadata():
    config_path = Path("outputs/test_update_preset_notes_config.toml")
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        """
[tournament_presets.keep]
base_profile = "playoff_pt"
tier_max = "bronze"

[tournament_presets.keep.tier_slots]
P = 1
""".strip()
        + "\n",
        encoding="utf-8",
    )

    update_preset_notes(
        config_path=config_path,
        preset_name="keep",
        title="Bronze Daily",
        note="Server slot 7",
    )

    text = config_path.read_text(encoding="utf-8")
    assert '_gui_title = "Bronze Daily"' in text
    assert '_gui_note = "Server slot 7"' in text
    assert "[tournament_presets.keep.tier_slots]" in text

    update_preset_notes(
        config_path=config_path,
        preset_name="keep",
        title="",
        note="",
    )

    text = config_path.read_text(encoding="utf-8")
    assert "_gui_title" not in text
    assert "_gui_note" not in text
    assert "[tournament_presets.keep]" in text


def test_update_preset_build_method_persists_selection():
    config_path = Path("outputs/test_update_preset_method_config.toml")
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        """
[tournament_presets.keep]
base_profile = "playoff_pt"
tier_max = "gold"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    update_preset_build_method(config_path, "keep", "optimizer")

    text = config_path.read_text(encoding="utf-8")
    assert 'build_method = "optimizer"' in text
    assert 'tier_max = "gold"' in text


def test_delete_preset_block_removes_main_and_nested_blocks():
    config_path = Path("outputs/test_delete_preset_config.toml")
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        """
[tournament_presets.keep]
base_profile = "playoff_pt"

[tournament_presets.remove_me]
base_profile = "playoff_pt"

[tournament_presets.remove_me.tier_slots]
P = 1

[tournament_presets.after]
base_profile = "playoff_pt"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    delete_preset_block(config_path, "remove_me")

    text = config_path.read_text(encoding="utf-8")
    assert "[tournament_presets.remove_me]" not in text
    assert "[tournament_presets.remove_me.tier_slots]" not in text
    assert "[tournament_presets.keep]" in text
    assert "[tournament_presets.after]" in text


def test_preset_owned_output_paths_include_stable_and_gui_outputs():
    paths = preset_owned_output_paths(
        "remove_me",
        {"_gui_html_output": "outputs/gui_remove_me.html"},
    )

    assert {path.name for path in paths} == {
        "preset_roster_remove_me.html",
        "preset_roster_remove_me.snapshot.json",
        "preset_upgrades_remove_me.html",
        "preset_upgrades_remove_me.snapshot.json",
        "gui_remove_me.html",
        "gui_remove_me.snapshot.json",
    }


def test_preset_owned_output_paths_ignore_gui_html_outside_outputs():
    paths = preset_owned_output_paths(
        "remove_me",
        {"_gui_html_output": "../outside.html"},
    )

    assert {path.name for path in paths} == {
        "preset_roster_remove_me.html",
        "preset_roster_remove_me.snapshot.json",
        "preset_upgrades_remove_me.html",
        "preset_upgrades_remove_me.snapshot.json",
    }


def test_delete_preset_removes_config_even_if_outputs_are_absent():
    config_path = Path("outputs/test_delete_preset_owned_config.toml")
    config_path.parent.mkdir(parents=True, exist_ok=True)
    for path in preset_owned_output_paths("remove_me", {}):
        if path.exists():
            path.unlink()
    config_path.write_text(
        """
[tournament_presets.remove_me]
base_profile = "playoff_pt"

[tournament_presets.keep]
base_profile = "playoff_pt"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    deleted = delete_preset(config_path, "remove_me")

    assert deleted == []
    text = config_path.read_text(encoding="utf-8")
    assert "[tournament_presets.remove_me]" not in text
    assert "[tournament_presets.keep]" in text


def test_slugify_creates_safe_output_name_component():
    assert slugify("Daily Diamond Heart (1850072)") == "daily_diamond_heart_1850072"
