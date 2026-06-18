from ootp_opt.config import load_config
from ootp_opt.services.roster_build_service import (
    RosterBuildRequest,
    build_output_name,
    build_ruleset,
)


def test_build_ruleset_uses_base_profile_and_overrides():
    cfg = load_config("config.toml")

    ruleset = build_ruleset(
        cfg,
        RosterBuildRequest(
            base_profile="playoff_pt",
            overrides={
                "tier_max": "gold",
                "simulation_year": 1965,
                "variant_limit": 0,
            },
        ),
    )

    assert ruleset.name == "playoff_pt"
    assert ruleset.tier_max == "gold"
    assert ruleset.simulation_year == 1965
    assert ruleset.variant_limit == 0


def test_build_ruleset_uses_tournament_preset():
    cfg = load_config("config.toml")

    ruleset = build_ruleset(
        cfg,
        RosterBuildRequest(preset="goldmax_nonlive_1580cap_variantmax10_DH"),
    )

    assert ruleset.name == "goldmax_nonlive_1580cap_variantmax10_DH"
    assert ruleset.tier_max == "gold"
    assert ruleset.live_mode == "non_live"
    assert ruleset.variant_limit == 10


def test_build_output_name_reflects_key_filters():
    cfg = load_config("config.toml")
    overrides = {
        "allowed_card_types": ["UnH", "Snap", "RS"],
        "dh_enabled": False,
    }
    ruleset = build_ruleset(
        cfg,
        RosterBuildRequest(base_profile="playoff_pt", overrides=overrides),
    )

    assert (
        build_output_name(ruleset, overrides)
        == "outputs/roster_build_playoff_pt_no_dh_types_unh_snap_rs.html"
    )
