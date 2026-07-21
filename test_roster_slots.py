from copy import deepcopy

import pytest

from ootp_opt.config import load_config
from ootp_opt.roster.rules import build_ruleset_from_base_profile
from ootp_opt.roster.slots import PitcherRoleGroup, RosterSlotPlan


def test_standard_profile_builds_split_lineups_and_pitcher_groups():
    cfg = load_config("config.toml")
    ruleset = build_ruleset_from_base_profile(cfg, "standard_pt")

    assert ruleset.slot_plan is not None
    plan = ruleset.slot_plan

    assert plan.hitter_count == 13
    assert plan.pitcher_count == 13
    assert len(plan.lineup_for_split("vs_rhp")) == 9
    assert len(plan.lineup_for_split("vs_lhp")) == 9
    assert plan.lineup_slot("vs_rhp", "3B").score_column == "score_3B_vs_rhp"
    assert plan.lineup_slot("vs_lhp", "DH").score_column == "batting_score_vs_lhp"
    assert plan.lineup_slot("vs_lhp", "DH").rating_column is None

    assert plan.pitcher_group("middle_relief").count == 6
    assert plan.pitcher_group("middle_relief").label == "Middle Relief"
    assert not plan.pitcher_group("middle_relief").member_order_matters
    assert plan.pitcher_group("rotation").count == 5
    assert plan.pitcher_group("rotation").member_order_matters
    assert plan.pitcher_group("lefty_specialist").count == 1
    assert plan.pitcher_group("long_relief").count == 1


def test_coverage_is_split_specific_and_requires_available_bench_players():
    cfg = load_config("config.toml")
    ruleset = build_ruleset_from_base_profile(cfg, "standard_pt")

    requirements = {
        (requirement.split, requirement.position): requirement
        for requirement in ruleset.lineup_coverage_requirements
    }

    assert len(requirements) == 16
    assert ("vs_rhp", "DH") not in requirements
    assert requirements[("vs_rhp", "SS")].minimum_bench_players == 1
    assert requirements[("vs_rhp", "SS")].minimum_rating == 85
    assert requirements[("vs_lhp", "CF")].rating_column == "fld_CF"


def test_bench_is_not_a_permanent_assignment_or_scored_role():
    cfg = load_config("config.toml")
    ruleset = build_ruleset_from_base_profile(cfg, "standard_pt")

    assert ruleset.slot_plan is not None
    assert not hasattr(ruleset.slot_plan, "groups")
    assert not any(
        "bench" in slot.key for slot in ruleset.slot_plan.lineup_slots
    )
    assert all(
        "bench" not in group.key for group in ruleset.slot_plan.pitcher_groups
    )


def test_no_dh_profile_has_eight_assignments_per_split_and_more_derived_bench():
    cfg = load_config("config.toml")
    ruleset = build_ruleset_from_base_profile(
        cfg,
        "standard_pt",
        overrides={"dh_enabled": False},
    )

    assert ruleset.slot_plan is not None
    assert len(ruleset.slot_plan.lineup_for_split("vs_rhp")) == 8
    assert len(ruleset.slot_plan.lineup_for_split("vs_lhp")) == 8
    assert all(slot.position != "DH" for slot in ruleset.slot_plan.lineup_slots)
    assert ruleset.slot_plan.hitter_count == 13


def test_plan_accepts_future_pitching_groups_without_new_model_fields():
    plan = RosterSlotPlan(
        lineup_slots=(),
        pitcher_groups=(
            PitcherRoleGroup(
                key="setup",
                label="Setup Relief",
                count=2,
                score_column="reliever_score_overall",
            ),
            PitcherRoleGroup(
                key="closer",
                label="Closer",
                count=1,
                score_column="reliever_score_overall",
            ),
        ),
        hitter_count=0,
        pitcher_count=3,
    )

    assert plan.pitcher_group("setup").count == 2
    assert plan.pitcher_group("closer").label == "Closer"


def test_plan_rejects_pitcher_counts_that_do_not_match_roster_shape():
    with pytest.raises(ValueError, match="Pitcher role groups do not match"):
        RosterSlotPlan(
            lineup_slots=(),
            pitcher_groups=(
                PitcherRoleGroup(
                    key="rotation",
                    label="Rotation",
                    count=4,
                    score_column="starter_score_overall",
                ),
            ),
            hitter_count=0,
            pitcher_count=5,
        )


def test_legacy_pitcher_count_keys_still_build_the_same_slot_plan():
    cfg = deepcopy(load_config("config.toml"))
    profile = cfg["roster_base_profiles"]["standard_pt"]
    profile["primary_rp_count"] = profile.pop("middle_relief_count")
    profile["specialist_lhp_count"] = profile.pop("lefty_specialist_count")
    profile["long_man_count"] = profile.pop("long_relief_count")

    ruleset = build_ruleset_from_base_profile(cfg, "standard_pt")

    assert ruleset.slot_plan is not None
    assert ruleset.slot_plan.pitcher_group("middle_relief").count == 6
    assert ruleset.slot_plan.pitcher_group("lefty_specialist").count == 1
    assert ruleset.slot_plan.pitcher_group("long_relief").count == 1


def test_negative_lineup_backup_coverage_count_is_rejected():
    cfg = deepcopy(load_config("config.toml"))
    cfg["roster_base_profiles"]["standard_pt"][
        "minimum_lineup_backup_coverage"
    ]["SS"] = -1

    with pytest.raises(ValueError, match="counts cannot be negative"):
        build_ruleset_from_base_profile(cfg, "standard_pt")


def test_legacy_roster_coverage_counts_convert_to_bench_counts():
    cfg = deepcopy(load_config("config.toml"))
    profile = cfg["roster_base_profiles"]["standard_pt"]
    coverage = profile.pop("minimum_lineup_backup_coverage")
    profile["minimum_roster_coverage"] = {
        position: count + 1 for position, count in coverage.items()
    }

    ruleset = build_ruleset_from_base_profile(cfg, "standard_pt")

    assert ruleset.minimum_lineup_backup_coverage["SS"] == 1
