import pandas as pd

from ootp_opt.roster.html_export import format_variant_flag


def test_format_variant_flag_uses_normalized_boolean():
    assert format_variant_flag(pd.Series({"is_variant": True})) == "Yes"
    assert format_variant_flag(pd.Series({"is_variant": False})) == "No"


def test_format_variant_flag_supports_raw_var_column():
    assert format_variant_flag(pd.Series({"VAR": "Y"})) == "Yes"
    assert format_variant_flag(pd.Series({"VAR": "N"})) == "No"
