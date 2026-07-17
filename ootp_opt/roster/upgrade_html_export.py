from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Any

import pandas as pd


def export_upgrade_html(
    path: str | Path,
    hitter_upgrades: pd.DataFrame,
    pitcher_upgrades: pd.DataFrame,
    title: str = "OOTP Upgrade Finder",
    summary_rows: list[tuple[str, Any]] | None = None,
) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    html = f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>{escape(title)}</title>
<style>
{CSS}
</style>
</head>
<body>
<h1>{escape(title)}</h1>

{render_summary(summary_rows or [])}

<section>
<h2>Hitter Upgrades</h2>
{render_table(hitter_upgrades)}
</section>

<section>
<h2>Pitcher Upgrades</h2>
{render_table(pitcher_upgrades)}
</section>

<script>
{JS}
</script>
</body>
</html>
"""

    path.write_text(html, encoding="utf-8")


def render_summary(rows: list[tuple[str, Any]]) -> str:
    if not rows:
        return ""

    body = "".join(
        f"<tr><th>{escape(str(label))}</th><td>{escape(str(value))}</td></tr>"
        for label, value in rows
    )
    return f"""
<section class="summary">
<table>
<tbody>{body}</tbody>
</table>
</section>
"""


def render_table(df: pd.DataFrame) -> str:
    if df.empty:
        return "<p>No upgrades found.</p>"

    columns = list(df.columns)

    header = "".join(
        f"<th onclick='sortTable(this)'>{escape(str(col))}</th>" for col in columns
    )

    rows = []
    for _, row in df.iterrows():
        cells = []
        for col in columns:
            value = row.get(col, "")
            cells.append(f"<td>{format_value(value)}</td>")
        rows.append(f"<tr>{''.join(cells)}</tr>")

    return f"""
<table>
<thead><tr>{header}</tr></thead>
<tbody>
{''.join(rows)}
</tbody>
</table>
"""


def format_value(value: object) -> str:
    if value is None:
        return ""

    if isinstance(value, int):
        return escape(f"{value:,}")

    if isinstance(value, float):
        if value.is_integer():
            return escape(f"{int(value):,}")
        return escape(f"{value:,.2f}")

    return escape(str(value))


CSS = """
body {
    margin: 16px;
    background: #111014;
    color: #f2edf4;
    font-family: Arial, Helvetica, sans-serif;
    font-size: 14px;
}

h1 {
    margin-bottom: 12px;
}

h2 {
    margin-top: 28px;
    color: #ffffff;
}

table {
    border-collapse: collapse;
    width: 100%;
    margin-bottom: 28px;
    background: #1c1b1f;
    border: 1px solid #3a313d;
}

th {
    background: #ff00d4;
    color: white;
    cursor: pointer;
    padding: 6px 8px;
    text-align: left;
    position: sticky;
    top: 0;
    z-index: 1;
}

td {
    padding: 5px 8px;
    border-bottom: 1px solid rgba(255,255,255,0.08);
    white-space: nowrap;
}

tbody tr:nth-child(even) {
    background: rgba(255,255,255,0.035);
}

tbody tr:hover {
    background: rgba(255,0,212,0.16);
}

td:nth-child(8),
td:nth-child(9),
td:nth-child(10),
td:nth-child(11) {
    text-align: right;
}

section {
    overflow-x: auto;
}

td {
    font-variant-numeric: tabular-nums;
}

td:nth-child(n+7) {
    text-align: right;
}

"""


JS = """
function sortTable(header) {
    const table = header.closest("table");
    const tbody = table.querySelector("tbody");
    const index = Array.from(header.parentNode.children).indexOf(header);
    const currentDir = header.getAttribute("data-sort-dir") || "asc";
    const newDir = currentDir === "asc" ? "desc" : "asc";

    table.querySelectorAll("th").forEach(th => th.removeAttribute("data-sort-dir"));
    header.setAttribute("data-sort-dir", newDir);

    const rows = Array.from(tbody.querySelectorAll("tr"));

    rows.sort((a, b) => {
        const av = a.children[index].innerText.trim();
        const bv = b.children[index].innerText.trim();

        const an = parseFloat(av.replace(/,/g, ""));
        const bn = parseFloat(bv.replace(/,/g, ""));

        let result;
        if (!isNaN(an) && !isNaN(bn)) {
            result = an - bn;
        } else {
            result = av.localeCompare(bv);
        }

        return newDir === "asc" ? result : -result;
    });

    rows.forEach(row => tbody.appendChild(row));
}
"""
