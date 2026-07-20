import pandas as pd
import pytest

from ootp_opt.config import load_config
from ootp_opt.roster.rules import build_ruleset_from_base_profile
from ootp_opt.services.candidate_service import (
    build_candidate_pool,
    resolve_build_context,
)


def test_resolve_build_context_combines_environment_and_simulation_config():
    cfg = load_config("config.toml")
    ruleset = build_ruleset_from_base_profile(
        cfg,
        base_profile_name="standard_pt",
        overrides={"scoring_environment": "open", "simulation_year": 1999},
    )

    context = resolve_build_context(cfg, ruleset)

    assert context.ruleset is ruleset
    assert context.scoring_environment.name == "open"
    assert context.simulation_context.simulation_year == 1999
    assert context.scoring_config["hitters"] != cfg["hitters"]


def test_candidate_pool_preserves_scored_cards_and_exposes_eligible_subset():
    cfg = load_config("config.toml")
    ruleset = build_ruleset_from_base_profile(
        cfg,
        base_profile_name="playoff_pt",
        overrides={"tier_max": "bronze"},
    )
    context = resolve_build_context(cfg, ruleset)
    hitters = pd.DataFrame(
        [
            {"name": "Bronze Hitter", "pt_tier": "bronze"},
            {"name": "Gold Hitter", "pt_tier": "gold"},
        ]
    )
    pitchers = pd.DataFrame(
        [
            {"name": "Iron Pitcher", "pt_tier": "iron"},
            {"name": "Silver Pitcher", "pt_tier": "silver"},
        ]
    )

    pool = build_candidate_pool(
        source="owned",
        context=context,
        scored_hitters=hitters,
        scored_pitchers=pitchers,
    )

    assert pool.source == "owned"
    assert pool.scored_counts == (2, 2)
    assert pool.eligible_counts == (1, 1)
    assert pool.eligible_hitters.iloc[0]["name"] == "Bronze Hitter"
    assert pool.eligible_pitchers.iloc[0]["name"] == "Iron Pitcher"


def test_candidate_pool_rejects_missing_eligible_group():
    cfg = load_config("config.toml")
    ruleset = build_ruleset_from_base_profile(
        cfg,
        base_profile_name="playoff_pt",
        overrides={"tier_max": "bronze"},
    )
    context = resolve_build_context(cfg, ruleset)
    pool = build_candidate_pool(
        source="store",
        context=context,
        scored_hitters=pd.DataFrame([{"name": "Gold Hitter", "pt_tier": "gold"}]),
        scored_pitchers=pd.DataFrame(
            [{"name": "Bronze Pitcher", "pt_tier": "bronze"}]
        ),
    )

    with pytest.raises(ValueError) as exc_info:
        pool.require_eligible_cards()

    assert str(exc_info.value) == "No eligible hitters after applying filters."
