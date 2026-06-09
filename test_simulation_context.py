import pytest

from ootp_opt.config import load_config
from ootp_opt.domain.simulation_context import (
    apply_simulation_context_to_config,
    load_era_factors,
    load_park_factors,
    resolve_simulation_context,
)
from ootp_opt.roster.rules import build_ruleset_from_base_profile


def test_load_era_factors_by_year():
    era = load_era_factors(1919)

    assert era.year == 1919
    assert era.contact > 0
    assert era.hr_power > 0
    assert era.stuff > 0


def test_load_park_factors_by_independent_park_year():
    park = load_park_factors("Dodger Stadium", 1962)

    assert park.year == 1962
    assert park.park == "Dodger Stadium"
    assert park.hr_overall == pytest.approx(0.775)


def test_unknown_park_has_useful_error():
    with pytest.raises(ValueError, match="not found for park year 1886"):
        load_park_factors("Swampoodle Grounds", 1886)


def test_resolve_context_keeps_simulation_and_ballpark_year_separate():
    context = resolve_simulation_context(
        simulation_year=1919,
        ballpark="Dodger Stadium",
        ballpark_year=1962,
    )

    assert context.simulation_year == 1919
    assert context.era.year == 1919
    assert context.ballpark_year == 1962
    assert context.park.year == 1962


def test_custom_park_factors_allow_unknown_tournament_park_name():
    context = resolve_simulation_context(
        simulation_year=1919,
        ballpark="1886 Swampoodle Grounds",
        ballpark_year=1886,
        custom_park_factors={
            "ba_lh": 0.975,
            "ba_rh": 0.975,
            "hr_lh": 0.975,
            "hr_rh": 0.975,
            "doubles_overall": 1.000,
            "triples_overall": 1.000,
        },
    )

    assert context.simulation_year == 1919
    assert context.park.park == "1886 Swampoodle Grounds"
    assert context.park.year == 1886
    assert context.park.ba_overall == pytest.approx(0.975)
    assert context.park.hr_overall == pytest.approx(0.975)


def test_apply_context_changes_scoring_weights_without_mutating_original_config():
    cfg = load_config("config.toml")
    context = resolve_simulation_context(
        simulation_year=1919,
        ballpark="Dodger Stadium",
        ballpark_year=1962,
    )

    adjusted = apply_simulation_context_to_config(cfg, context)

    assert adjusted is not cfg
    assert adjusted["hitters"]["power"] != cfg["hitters"]["power"]
    assert adjusted["pitchers"]["sp_hr_rate"] != cfg["pitchers"]["sp_hr_rate"]
    assert cfg["hitters"]["power"] == pytest.approx(1.15)


def test_ruleset_parses_simulation_and_ballpark_fields_from_overrides():
    cfg = load_config("config.toml")

    ruleset = build_ruleset_from_base_profile(
        cfg,
        "playoff_pt",
        overrides={
            "simulation_year": 1919,
            "ballpark": "Dodger Stadium",
            "ballpark_year": 1962,
            "custom_park_factors": {"ba_lh": 0.975, "hr_lh": 0.975},
        },
    )

    assert ruleset.simulation_year == 1919
    assert ruleset.ballpark == "Dodger Stadium"
    assert ruleset.ballpark_year == 1962
    assert ruleset.custom_park_factors == {"ba_lh": 0.975, "hr_lh": 0.975}
