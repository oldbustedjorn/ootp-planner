from ootp_opt.services.store_upgrade_service import (
    StoreUpgradeRequest,
    build_output_name,
    build_ruleset,
)


def sample_config():
    util_requirement = {
        "required_positions_any": ["C"],
        "required_positions": [],
        "preferred_positions": ["C"],
    }
    return {
        "roster": {"default_base_profile": "standard_pt"},
        "roster_base_profiles": {
            "standard_pt": {
                "mode": "standard_pt",
                "hitter_count": 2,
                "pitcher_count": 13,
                "dh_enabled": True,
                "platoons_allowed": False,
                "lineup_fill_order": ["C"],
                "rotation_size": 5,
                "primary_rp_count": 6,
                "specialist_lhp_count": 1,
                "long_man_count": 1,
                "bench_roles": ["UTIL"],
                "bench_role_requirements": {"UTIL": util_requirement},
            },
            "playoff_pt": {
                "mode": "playoff_pt",
                "hitter_count": 2,
                "pitcher_count": 12,
                "dh_enabled": True,
                "platoons_allowed": False,
                "lineup_fill_order": ["C"],
                "rotation_size": 4,
                "primary_rp_count": 6,
                "specialist_lhp_count": 1,
                "long_man_count": 1,
                "bench_roles": ["UTIL"],
                "bench_role_requirements": {"UTIL": util_requirement},
            },
        },
        "tournament_presets": {
            "bronze_nonlive": {
                "base_profile": "playoff_pt",
                "tier_max": "bronze",
                "live_mode": "non_live",
            }
        },
    }


def test_store_upgrade_ruleset_uses_preset():
    cfg = sample_config()

    ruleset = build_ruleset(
        cfg,
        StoreUpgradeRequest(preset="bronze_nonlive"),
    )

    assert ruleset.name == "bronze_nonlive"
    assert ruleset.tier_max == "bronze"
    assert ruleset.live_mode == "non_live"


def test_store_upgrade_ruleset_uses_base_profile_overrides():
    cfg = sample_config()

    ruleset = build_ruleset(
        cfg,
        StoreUpgradeRequest(
            base_profile="playoff_pt",
            overrides={"tier_max": "gold", "simulation_year": 1999},
        ),
    )

    assert ruleset.name == "playoff_pt"
    assert ruleset.tier_max == "gold"
    assert ruleset.simulation_year == 1999


def test_store_upgrade_output_name_is_stable_for_ruleset():
    cfg = sample_config()
    ruleset = build_ruleset(cfg, StoreUpgradeRequest(preset="bronze_nonlive"))

    assert build_output_name(ruleset) == "outputs\\store_upgrades_bronze_nonlive.html"
