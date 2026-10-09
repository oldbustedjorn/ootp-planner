from pathlib import Path

import pandas as pd

from ootp_opt.roster.portfolio_upgrade_html_export import (
    export_portfolio_upgrade_html,
)
from ootp_opt.services.portfolio_upgrade_service import (
    aggregate_portfolio_upgrades,
    exclude_card_titles,
)


def upgrade_rows() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "type": "hitter",
                "candidate": "Broad Upgrade",
                "pt_card_id": 101,
                "is_variant": False,
                "card_title": "Historical All-Star",
                "estimated_objective_gain": 50.0,
                "roster_id": "one",
                "roster_name": "Roster One",
            },
            {
                "type": "hitter",
                "candidate": "Broad Upgrade",
                "pt_card_id": 101,
                "is_variant": False,
                "card_title": "Historical All-Star",
                "estimated_objective_gain": 20.0,
                "roster_id": "two",
                "roster_name": "Roster Two",
            },
            {
                "type": "hitter",
                "candidate": "Narrow Upgrade",
                "pt_card_id": 102,
                "is_variant": False,
                "card_title": "Snapshot",
                "estimated_objective_gain": 100.0,
                "roster_id": "one",
                "roster_name": "Roster One",
            },
            {
                "type": "hitter",
                "candidate": "Excluded Card",
                "pt_card_id": 103,
                "is_variant": False,
                "card_title": "PTCS 5 - Rookie Sensation",
                "estimated_objective_gain": 500.0,
                "roster_id": "two",
                "roster_name": "Roster Two",
            },
        ]
    )


def test_exclude_card_titles_is_case_insensitive() -> None:
    filtered = exclude_card_titles(
        upgrade_rows(), ("ptcs", "Limited Edition")
    )

    assert filtered["candidate"].tolist() == [
        "Broad Upgrade",
        "Broad Upgrade",
        "Narrow Upgrade",
    ]


def test_aggregate_rewards_normalized_impact_and_breadth() -> None:
    filtered = exclude_card_titles(upgrade_rows(), ("PTCS",))
    result = aggregate_portfolio_upgrades(filtered, top=20)

    broad = result.loc[result["candidate"].eq("Broad Upgrade")].iloc[0]
    narrow = result.loc[result["candidate"].eq("Narrow Upgrade")].iloc[0]
    assert broad["rosters_helped"] == 2
    assert broad["portfolio_score"] == 160.0
    assert narrow["portfolio_score"] == 105.0
    assert broad["rank"] == 1


def test_export_portfolio_report_is_sortable_and_filterable() -> None:
    rows = aggregate_portfolio_upgrades(
        exclude_card_titles(upgrade_rows(), ("PTCS",)), top=20
    )
    output = "outputs/portfolio-test-report.html"

    export_portfolio_upgrade_html(
        output,
        hitter_upgrades=rows,
        pitcher_upgrades=pd.DataFrame(),
        completed_rosters=["Roster One", "Roster Two"],
        failed_rosters={},
        excluded_title_terms=("PTCS",),
        applied_overrides={"roster_one": {"ballpark_year": 2023}},
    )

    html = Path(output).read_text(encoding="utf-8")
    assert "Portfolio Score" in html
    assert "table-filter" in html
    assert "Broad Upgrade" in html
    assert "PTCS" in html
    assert "ballpark_year" in html
