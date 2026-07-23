import pandas as pd

from ootp_opt.roster.html_export import (
    format_variant_flag,
    render_build_summary,
    render_build_timing_summary,
    render_lineup_panel,
    render_optimizer_summary,
)
from ootp_opt.config import load_config
from ootp_opt.roster.rules import build_ruleset_from_base_profile
from ootp_opt.roster.models import HitterRoster


def test_format_variant_flag_uses_normalized_boolean():
    assert format_variant_flag(pd.Series({"is_variant": True})) == "Yes"
    assert format_variant_flag(pd.Series({"is_variant": False})) == "No"


def test_format_variant_flag_supports_raw_var_column():
    assert format_variant_flag(pd.Series({"VAR": "Y"})) == "Yes"
    assert format_variant_flag(pd.Series({"VAR": "N"})) == "No"


def test_render_build_timing_summary_shows_stage_rows():
    html = render_build_timing_summary(
        [
            ("Initial roster selection", "1.250 s"),
            ("Pre-export subtotal", "2.500 s"),
        ]
    )

    assert "Build Timings" in html
    assert "Initial roster selection" in html
    assert "1.250 s" in html
    assert "Pre-export subtotal" in html


def test_roster_html_includes_lineup_pitcher_and_coverage_summary():
    cfg = load_config("config.toml")
    ruleset = build_ruleset_from_base_profile(cfg, "standard_pt")

    html = render_build_summary(
        ruleset=ruleset,
        eligibility_summary={},
    )

    assert "Lineup assignments" in html
    assert "vs RHP: C, SS, CF, 2B, 3B, LF, RF, 1B, DH" in html
    assert "Pitcher groups" in html
    assert "Middle Relief x6" in html
    assert "Lineup bench coverage" in html
    assert "SS x1 per lineup (rating &gt;= 85)" in html


def test_optimizer_summary_renders_solver_diagnostics():
    html = render_optimizer_summary(
        [
            ("Optimizer status", "optimal"),
            ("Optimizer solve time", "11.400 s"),
        ]
    )

    assert "Optimizer Result" in html
    assert "optimal" in html
    assert "11.400 s" in html


def test_lineup_panel_uses_starters_for_requested_split():
    positions = ["C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "DH"]
    rhp = {
        position: pd.Series(
            {
                "name": f"RHP {position}",
                "bats": "R",
                "batting_score_vs_rhp": 100 - index,
                "batting_score_vs_lhp": 50 - index,
            }
        )
        for index, position in enumerate(positions)
    }
    lhp = {
        position: pd.Series(
            {
                "name": f"LHP {position}",
                "bats": "L",
                "batting_score_vs_rhp": 50 - index,
                "batting_score_vs_lhp": 100 - index,
            }
        )
        for index, position in enumerate(positions)
    }
    roster = HitterRoster(
        starters_by_position=rhp,
        bench_players=pd.DataFrame(),
        unused_players=pd.DataFrame(),
        starters_by_split={"vs_rhp": rhp, "vs_lhp": lhp},
    )

    html = render_lineup_panel(roster, split="vs_lhp", title="Lineup vs. LHP")

    assert "LHP C" in html
    assert "LHP DH" in html
    assert "RHP C" not in html
