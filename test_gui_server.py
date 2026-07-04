from pathlib import Path

from ootp_opt.gui.server import (
    MAX_OOTP_ROSTER_NAME_LENGTH,
    append_history_record_as_preset,
    build_auto_roster_name,
    build_gui_request,
    build_overrides_from_form,
    delete_preset,
    delete_preset_block,
    next_build_number,
    preset_owned_output_paths,
    preset_roster_output_path,
    preset_upgrade_output_path,
    render_presets_panel,
    resolve_preset_build_metadata,
    slugify,
    update_preset_notes,
)


def form(**kwargs):
    return {
        key: value if isinstance(value, list) else [str(value)]
        for key, value in kwargs.items()
    }


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


def test_next_build_number_uses_existing_registry_max():
    assert next_build_number([]) == 1
    assert next_build_number([{"build_number": 2}, {"build_number": 14}]) == 15


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
    assert "Save Notes" in html
    assert "Delete Preset" in html
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
        },
        preset_name="saved_from_history",
    )

    text = config_path.read_text(encoding="utf-8")
    assert "[tournament_presets.saved_from_history]" in text
    assert "dh_enabled = false" in text
    assert 'allowed_card_types = ["UnH", "Snap"]' in text
    assert "[tournament_presets.saved_from_history.tier_slots]" in text
    assert '_gui_roster_name = "T-006-Smax-Y1986-NoDH"' in text


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
    assert metadata["html_output"] == "outputs\\gui_standard_pt_regular_season_20260627_202711.html"


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
