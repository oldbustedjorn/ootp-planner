import pandas as pd

from ootp_opt.domain.candidate_identity import CANDIDATE_ID_COLUMN
from ootp_opt.services.store_upgrade_service import (
    StoreUpgradeRequest,
    build_direct_upgrade_rows,
    build_output_name,
    build_ruleset,
    resolve_upgrade_build_method,
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
                "build_method": "optimizer",
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


def test_store_upgrade_inherits_optimizer_method_from_preset():
    cfg = sample_config()

    method = resolve_upgrade_build_method(
        cfg,
        StoreUpgradeRequest(preset="bronze_nonlive"),
    )

    assert method == "optimizer"


def test_store_upgrade_explicit_method_overrides_preset():
    cfg = sample_config()

    method = resolve_upgrade_build_method(
        cfg,
        StoreUpgradeRequest(preset="bronze_nonlive", build_method="greedy"),
    )

    assert method == "greedy"


def test_direct_upgrade_rows_apply_listing_and_price_filters():
    opportunities = pd.DataFrame(
        [
            {
                CANDIDATE_ID_COLUMN: "listed",
                "type": "hitter",
                "role": "vs RHP DH",
                "current_player": "Current DH",
                "current_score": 100.0,
                "candidate_score": 120.0,
                "direct_score_gain": 20.0,
                "estimated_objective_gain": 14.0,
            },
            {
                CANDIDATE_ID_COLUMN: "unlisted",
                "type": "hitter",
                "role": "vs RHP DH",
                "current_player": "Current DH",
                "current_score": 100.0,
                "candidate_score": 130.0,
                "direct_score_gain": 30.0,
                "estimated_objective_gain": 21.0,
            },
        ]
    )
    store_hitters = pd.DataFrame(
        [
            {
                CANDIDATE_ID_COLUMN: "listed",
                "name": "Listed Card",
                "pt_tier": "gold",
                "card_value": 89,
                "sell_order_low": 1200,
                "buy_order_high": 800,
                "last_10_price": 1000,
            },
            {
                CANDIDATE_ID_COLUMN: "unlisted",
                "name": "Unlisted Card",
                "pt_tier": "perfect",
                "card_value": 100,
                "sell_order_low": 0,
                "buy_order_high": 500,
                "last_10_price": 900,
            },
        ]
    )

    rows = build_direct_upgrade_rows(
        opportunities=opportunities,
        store_hitters=store_hitters,
        store_pitchers=pd.DataFrame(),
        min_gain=5.0,
        max_price=1500,
        require_sell_order=True,
    )

    assert list(rows["candidate"]) == ["Listed Card"]
    assert rows.iloc[0]["purchase_price"] == 1200
    assert rows.iloc[0]["cost_per_gain"] == 85.71
