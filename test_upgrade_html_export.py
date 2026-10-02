import math

import pandas as pd

from ootp_opt.roster.upgrade_html_export import export_upgrade_html, format_value


def test_upgrade_html_formats_missing_exact_results_as_blank():
    assert format_value(None) == ""
    assert format_value(math.nan) == ""


def test_upgrade_html_formats_boolean_metadata_as_yes_no():
    assert format_value(True) == "Yes"
    assert format_value(False) == "No"


def test_upgrade_html_includes_store_card_metadata_columns(tmp_path):
    output = tmp_path / "upgrades.html"
    upgrades = pd.DataFrame(
        [
            {
                "pt_card_id": 86730,
                "is_variant": True,
                "card_title": "Clubhouse - Snapshot Example",
                "is_clubhouse_card": True,
                "clubhouse_star_cost": 50,
                "pp_per_clubhouse_star": 1234.5,
            }
        ]
    )

    export_upgrade_html(output, upgrades, pd.DataFrame())

    html = output.read_text(encoding="utf-8")
    assert "card_title" in html
    assert "CID" in html
    assert "86,730" in html
    assert "Variant" in html
    assert "Clubhouse Card" in html
    assert "Clubhouse Stars" in html
    assert "PP / Clubhouse Star" in html
    assert "1,234.50" in html
    assert ">Yes<" in html
