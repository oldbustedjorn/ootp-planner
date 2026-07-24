import math

from ootp_opt.roster.upgrade_html_export import format_value


def test_upgrade_html_formats_missing_exact_results_as_blank():
    assert format_value(None) == ""
    assert format_value(math.nan) == ""
