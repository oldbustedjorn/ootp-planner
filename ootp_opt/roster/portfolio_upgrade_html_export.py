from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Any

import pandas as pd

from ootp_opt.roster.upgrade_html_export import JS, format_value


COLUMN_LABELS = {
    "rank": "Rank",
    "candidate": "Card",
    "pt_card_id": "CID",
    "is_variant": "Variant",
    "candidate_tier": "Tier",
    "candidate_value": "OVR",
    "card_title": "Card Title",
    "is_clubhouse_card": "Clubhouse",
    "clubhouse_star_cost": "Clubhouse Stars",
    "pp_per_clubhouse_star": "PP / Star",
    "portfolio_score": "Portfolio Score",
    "rosters_helped": "Rosters Helped",
    "total_estimated_gain": "Total Est. Gain",
    "best_estimated_gain": "Best Est. Gain",
    "best_roster": "Best Roster",
    "purchase_price": "Estimated Price",
    "sell_order_low": "Sell Order",
    "helped_rosters": "Roster Benefits",
}


def export_portfolio_upgrade_html(
    path: str | Path,
    *,
    hitter_upgrades: pd.DataFrame,
    pitcher_upgrades: pd.DataFrame,
    completed_rosters: list[str],
    failed_rosters: dict[str, str],
    excluded_title_terms: tuple[str, ...],
    applied_overrides: dict[str, dict[str, Any]] | None = None,
) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    failures = "".join(
        f"<li><strong>{escape(name)}</strong>: {escape(error)}</li>"
        for name, error in failed_rosters.items()
    )
    failure_section = (
        f"<details><summary>Failed rosters ({len(failed_rosters)})</summary>"
        f"<ul>{failures}</ul></details>"
        if failed_rosters
        else ""
    )
    exclusions = ", ".join(excluded_title_terms)
    override_rows = "".join(
        f"<li><strong>{escape(plan)}</strong>: {escape(str(values))}</li>"
        for plan, values in (applied_overrides or {}).items()
    )
    override_section = (
        f"<details><summary>Run-only roster overrides "
        f"({len(applied_overrides or {})})</summary><ul>{override_rows}</ul></details>"
        if applied_overrides
        else ""
    )
    html = f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>All-Roster Upgrade Portfolio</title>
<style>{CSS}</style>
</head>
<body>
<h1>All-Roster Upgrade Portfolio</h1>
<section class="summary">
  <p><strong>Rosters analyzed:</strong> {len(completed_rosters)}</p>
  <p><strong>Excluded card-title terms:</strong> {escape(exclusions)}</p>
  <p><strong>Portfolio Score:</strong> For each roster helped, the card receives
  100 points times its estimated gain divided by that roster's best eligible
  gain, plus 5 breadth points. Scores are summed across rosters. This makes
  unlike scoring environments comparable while rewarding cards useful to more
  teams.</p>
  {override_section}
  {failure_section}
</section>
<label class="filter">Filter both tables
  <input id="table-filter" type="search" placeholder="Card, title, roster, CID...">
</label>
<section>
<h2>Top 20 Hitters</h2>
{render_table(hitter_upgrades)}
</section>
<section>
<h2>Top 20 Pitchers</h2>
{render_table(pitcher_upgrades)}
</section>
<script>{JS}\n{FILTER_JS}</script>
</body>
</html>
"""
    path.write_text(html, encoding="utf-8")


def render_table(rows: pd.DataFrame) -> str:
    if rows.empty:
        return "<p>No upgrades found.</p>"
    columns = list(rows.columns)
    headers = "".join(
        f"<th onclick='sortTable(this)'>{escape(COLUMN_LABELS.get(column, column))}</th>"
        for column in columns
    )
    body = []
    for _, row in rows.iterrows():
        cells = "".join(
            f"<td>{format_value(row.get(column, ''))}</td>" for column in columns
        )
        body.append(f"<tr>{cells}</tr>")
    return (
        f"<table><thead><tr>{headers}</tr></thead>"
        f"<tbody>{''.join(body)}</tbody></table>"
    )


CSS = """
body { margin: 18px; background: #111418; color: #eef1f4;
       font-family: Arial, Helvetica, sans-serif; font-size: 14px; }
h1 { margin-bottom: 10px; }
h2 { margin-top: 28px; }
.summary { max-width: 1100px; line-height: 1.45; }
.filter { display: flex; align-items: center; gap: 10px; margin: 20px 0 8px;
          font-weight: bold; }
.filter input { width: min(520px, 70vw); padding: 8px 10px; color: #fff;
                background: #222831; border: 1px solid #596270; }
section { overflow-x: auto; }
table { border-collapse: collapse; width: 100%; margin-bottom: 30px;
        background: #1b2027; border: 1px solid #3e4652; }
th { background: #a8008c; color: #fff; cursor: pointer; padding: 7px 8px;
     text-align: left; position: sticky; top: 0; z-index: 1; white-space: nowrap; }
td { padding: 6px 8px; border-bottom: 1px solid rgba(255,255,255,.09);
     white-space: nowrap; font-variant-numeric: tabular-nums; }
td:last-child { white-space: normal; min-width: 420px; }
tbody tr:nth-child(even) { background: rgba(255,255,255,.035); }
tbody tr:hover { background: rgba(168,0,140,.22); }
"""


FILTER_JS = """
document.getElementById("table-filter").addEventListener("input", event => {
    const query = event.target.value.trim().toLowerCase();
    document.querySelectorAll("tbody tr").forEach(row => {
        row.hidden = query && !row.innerText.toLowerCase().includes(query);
    });
});
"""
