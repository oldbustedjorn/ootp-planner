from ootp_opt.gui.server import (
    MAX_OOTP_ROSTER_NAME_LENGTH,
    build_auto_roster_name,
    build_gui_request,
    build_overrides_from_form,
    next_build_number,
    slugify,
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


def test_slugify_creates_safe_output_name_component():
    assert slugify("Daily Diamond Heart (1850072)") == "daily_diamond_heart_1850072"
