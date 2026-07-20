import pandas as pd

from ootp_opt.roster.html_export import (
    format_variant_flag,
    render_build_timing_summary,
)


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
