from ootp_opt.config import load_config
from ootp_opt.roster.rules import (
    build_ruleset_from_base_profile,
    build_ruleset_from_tournament_preset,
)


def test_unspecified_variant_limit_means_no_limit():
    cfg = load_config("config.toml")

    ruleset = build_ruleset_from_base_profile(cfg, "standard_pt")

    assert ruleset.variant_limit is None


def test_explicit_zero_variant_limit_means_no_variants():
    cfg = load_config("config.toml")

    ruleset = build_ruleset_from_base_profile(
        cfg,
        "standard_pt",
        overrides={"variant_limit": 0},
    )

    assert ruleset.variant_limit == 0


def test_preset_variant_limit_is_preserved():
    cfg = load_config("config.toml")

    ruleset = build_ruleset_from_tournament_preset(
        cfg,
        "goldmax_nonlive_1580cap_variantmax10_DH",
    )

    assert ruleset.variant_limit == 10
