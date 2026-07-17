from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Any

import pandas as pd

from ootp_opt.domain.scoring_environment import ScoringEnvironment
from ootp_opt.domain.simulation_context import SimulationContext
from ootp_opt.roster.lineup import (
    build_lineup_order,
    assign_position_backups,
    build_pinch_hitters,
    build_pinch_runners,
)
from ootp_opt.roster.models import HitterRoster, PitcherRoster
from ootp_opt.roster.rules import Ruleset
from ootp_opt.roster.tier_slot_report import build_tier_slot_rows, normalize_tier_slots
from ootp_opt.roster.tier_slot_repair import TierSlotRepairResult
from ootp_opt.roster.variant_report import is_variant_card

DEPTH_ORDER = ["C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "DH"]


def export_roster_html(
    path: str | Path,
    ruleset: Ruleset,
    hitter_roster: HitterRoster,
    pitcher_roster: PitcherRoster,
    eligibility_summary: dict[str, Any] | None = None,
    change_statuses: dict[str, str] | None = None,
    tier_slot_repair_result: TierSlotRepairResult | None = None,
    simulation_context: SimulationContext | None = None,
    scoring_environment: ScoringEnvironment | None = None,
) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    html = build_roster_html(
        ruleset=ruleset,
        hitter_roster=hitter_roster,
        pitcher_roster=pitcher_roster,
        eligibility_summary=eligibility_summary or {},
        change_statuses=change_statuses or {},
        tier_slot_repair_result=tier_slot_repair_result,
        simulation_context=simulation_context,
        scoring_environment=scoring_environment,
    )

    path.write_text(html, encoding="utf-8")


def build_roster_html(
    ruleset: Ruleset,
    hitter_roster: HitterRoster,
    pitcher_roster: PitcherRoster,
    eligibility_summary: dict[str, Any],
    change_statuses: dict[str, str],
    tier_slot_repair_result: TierSlotRepairResult | None = None,
    simulation_context: SimulationContext | None = None,
    scoring_environment: ScoringEnvironment | None = None,
) -> str:
    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>OOTP Roster Build - {escape(ruleset.name)}</title>
<style>
{CSS}
</style>
</head>
<body>
  <h1>OOTP Roster Build: {escape(ruleset.name)}</h1>

  {render_build_summary(ruleset, eligibility_summary, simulation_context, scoring_environment)}
  {render_tier_slot_summary(ruleset, hitter_roster, pitcher_roster)}
  {render_tier_slot_repair_summary(tier_slot_repair_result)}
  {render_roster_checklist(hitter_roster, pitcher_roster, change_statuses)}

  <section class="screen two-col">
    {render_rotation(pitcher_roster)}
    {render_bullpen(pitcher_roster)}
  </section>

  <section class="screen lineup-screen">
    {render_lineup_panel(hitter_roster, split="vs_rhp", title="Lineup vs. RHP")}
    {render_depth_chart_panel(hitter_roster, ruleset, title="Depth Chart vs. RHP")}
    {render_side_panel(hitter_roster, split="vs_rhp")}
  </section>

  <section class="screen lineup-screen">
    {render_lineup_panel(hitter_roster, split="vs_lhp", title="Lineup vs. LHP")}
    {render_depth_chart_panel(hitter_roster, ruleset, title="Depth Chart vs. LHP")}
    {render_side_panel(hitter_roster, split="vs_lhp")}
  </section>
</body>
</html>
"""


def render_build_summary(
    ruleset: Ruleset,
    eligibility_summary: dict[str, Any],
    simulation_context: SimulationContext | None = None,
    scoring_environment: ScoringEnvironment | None = None,
) -> str:
    rows = [
        (
            "Roster shape",
            f"{ruleset.hitter_count} hitters / {ruleset.pitcher_count} pitchers",
        ),
        ("DH", "Yes" if ruleset.dh_enabled else "No"),
        ("Tier min/max", f"{ruleset.tier_min or '-'} / {ruleset.tier_max or '-'}"),
        (
            "Card value min/max",
            f"{ruleset.card_value_min or '-'} / {ruleset.card_value_max or '-'}",
        ),
        ("Live mode", ruleset.live_mode),
        (
            "Allowed card types",
            ", ".join(ruleset.allowed_card_types) or "-",
        ),
        (
            "Excluded card types",
            ", ".join(ruleset.excluded_card_types) or "-",
        ),
        (
            "Card year min/max",
            f"{ruleset.card_year_min or '-'} / {ruleset.card_year_max or '-'}",
        ),
        (
            "Simulation year",
            "-" if ruleset.simulation_year is None else str(ruleset.simulation_year),
        ),
        (
            "Ballpark",
            ruleset.ballpark or "-",
        ),
        (
            "Ballpark year",
            "-" if ruleset.ballpark_year is None else str(ruleset.ballpark_year),
        ),
        (
            "Custom park factors",
            format_custom_park_factors(ruleset.custom_park_factors),
        ),
        (
            "Variant limit",
            "-" if ruleset.variant_limit is None else str(ruleset.variant_limit),
        ),
        (
            "Tier slots",
            format_tier_slots(ruleset.tier_slots),
        ),
        (
            "Point cap",
            "-" if ruleset.point_cap_total is None else str(ruleset.point_cap_total),
        ),
    ]

    if scoring_environment is not None:
        rows.extend(scoring_environment.summary_rows())

    if simulation_context is not None:
        rows.extend(simulation_context.summary_rows())

    if eligibility_summary:
        for key, value in eligibility_summary.items():
            rows.append((str(key), str(value)))

    body = "".join(
        f"<tr><th>{escape(label)}</th><td>{escape(value)}</td></tr>"
        for label, value in rows
    )

    return f"""
<section class="summary">
  <table>
    {body}
  </table>
</section>
"""


def format_tier_slots(tier_slots: dict[str, int]) -> str:
    if not tier_slots:
        return "-"

    normalized_slots = normalize_tier_slots(tier_slots)
    if not normalized_slots:
        return "-"

    return (
        ", ".join(f"{tier}: {count}" for tier, count in normalized_slots.items())
        + ", iron: unlimited"
    )


def format_custom_park_factors(factors: dict[str, float]) -> str:
    if not factors:
        return "-"

    return ", ".join(f"{key}: {value:g}" for key, value in factors.items())


def render_tier_slot_summary(
    ruleset: Ruleset,
    hitter_roster: HitterRoster,
    pitcher_roster: PitcherRoster,
) -> str:
    if not ruleset.tier_slots:
        return ""

    rows = build_tier_slot_rows(
        hitter_roster=hitter_roster,
        pitcher_roster=pitcher_roster,
        tier_slots=ruleset.tier_slots,
    )

    if not rows:
        return ""

    body = "".join(
        "<tr>"
        f"<td>{escape(row.tier)}</td>"
        f"<td class='num'>{row.selected_count}</td>"
        f"<td class='num'>{row.direct_slots}</td>"
        f"<td class='num'>{row.cumulative_selected}</td>"
        f"<td class='num'>{slot_value(row.cumulative_slots)}</td>"
        f"<td class='num'>{signed_delta(row.remaining)}</td>"
        f"<td class='{tier_slot_status_class(row.is_over_limit, ruleset)}'>"
        f"{'OVER' if row.is_over_limit else 'OK'}</td>"
        "</tr>"
        for row in rows
    )

    return f"""
<section class="screen">
  <div class="panel">
    <div class="panel-title">Tier Slot Summary</div>
    <table>
      <thead>
        <tr>
          <th>Tier</th>
          <th>Selected</th>
          <th>Slots</th>
          <th>Selected or Better</th>
          <th>Slots or Better</th>
          <th>Remaining</th>
          <th>Status</th>
        </tr>
      </thead>
      <tbody>{body}</tbody>
    </table>
  </div>
</section>
"""


def signed_delta(value: int | None) -> str:
    if value is None:
        return "unlimited"
    if value > 0:
        return f"+{value}"
    return str(value)


def slot_value(value: int | None) -> str:
    return "unlimited" if value is None else str(value)


def tier_slot_status_class(is_over_limit: bool, ruleset: Ruleset) -> str:
    if not ruleset.tier_slots:
        return ""
    if is_over_limit:
        return "status-over"
    return "status-ok"


def render_tier_slot_repair_summary(
    result: TierSlotRepairResult | None,
) -> str:
    if result is None:
        return ""

    if not result.steps:
        status = "Successful" if result.success else "Incomplete"
        detail = "No tier slot repair needed." if result.success else (
            f"No tier slot repair steps were available; still over {result.final_over_tier}."
        )
        return f"""
<section class="screen">
  <div class="panel">
    <div class="panel-title">Tier Slot Repair</div>
    <table>
      <tbody>
        <tr><th>Status</th><td>{escape(status)}</td></tr>
        <tr><th>Detail</th><td>{escape(detail)}</td></tr>
      </tbody>
    </table>
  </div>
</section>
"""

    body = "".join(
        "<tr>"
        f"<td class='num'>{idx}</td>"
        f"<td>{escape(step.role)}</td>"
        f"<td>{escape(step.old_name)}</td>"
        f"<td>{escape(step.old_tier)}</td>"
        f"<td>{escape(step.new_name)}</td>"
        f"<td>{escape(step.new_tier)}</td>"
        f"<td class='num'>{step.score_loss:.1f}</td>"
        f"<td>{escape(step.repaired_tier)}</td>"
        f"<td>{escape(step.still_over_tier or 'none')}</td>"
        "</tr>"
        for idx, step in enumerate(result.steps, start=1)
    )

    status = "Successful" if result.success else "Incomplete"
    if not result.success and result.final_over_tier:
        status = f"{status}: still over {result.final_over_tier}"

    return f"""
<section class="screen">
  <div class="panel">
    <div class="panel-title">Tier Slot Repair - {escape(status)}</div>
    <table>
      <thead>
        <tr>
          <th>#</th>
          <th>Role</th>
          <th>Old Player</th>
          <th>Old Tier</th>
          <th>New Player</th>
          <th>New Tier</th>
          <th>Score Loss</th>
          <th>Repaired Tier</th>
          <th>Still Over</th>
        </tr>
      </thead>
      <tbody>{body}</tbody>
    </table>
  </div>
</section>
"""


def render_rotation(pitcher_roster: PitcherRoster) -> str:
    rows = []
    for idx, (_, row) in enumerate(pitcher_roster.rotation.iterrows(), start=1):
        rows.append(
            "<tr>"
            f"<td>{idx}</td>"
            f"<td>{escape(str(row.get('throws', '')))}</td>"
            f"<td>{escape(str(row.get('name', '')))}</td>"
            f"<td class='num'>{float(row.get('starter_score_overall', 0.0)):.1f}</td>"
            "</tr>"
        )

    return f"""
<div class="panel rotation">
  <div class="panel-title"># &nbsp; T &nbsp; Starting Rotation</div>
  <table>
    <thead>
      <tr><th>#</th><th>T</th><th>Starting Rotation</th><th>Score</th></tr>
    </thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
</div>
"""


def render_bullpen(pitcher_roster: PitcherRoster) -> str:
    rows = []

    for _, row in pitcher_roster.bullpen.iterrows():
        rows.append(
            render_pitcher_role_row(row, role="Middle Relief", usage="Normal Usage")
        )

    for _, row in pitcher_roster.lefty_specialist.iterrows():
        rows.append(
            render_pitcher_role_row(row, role="Specialist", usage="vs Left-Handed")
        )

    for _, row in pitcher_roster.long_man.iterrows():
        rows.append(
            render_pitcher_role_row(row, role="Long Relief", usage="Normal Usage")
        )

    return f"""
<div class="panel bullpen">
  <div class="panel-title">T &nbsp; Bullpen</div>
  <table>
    <thead>
      <tr>
        <th>T</th><th>Bullpen</th><th>Primary Role</th><th>Usage Option</th><th>Secondary Role</th><th>Score</th>
      </tr>
    </thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
</div>
"""


def render_pitcher_role_row(row: pd.Series, role: str, usage: str) -> str:
    return (
        "<tr>"
        f"<td>{escape(str(row.get('throws', '')))}</td>"
        f"<td>{escape(str(row.get('name', '')))}</td>"
        f"<td>{escape(role)}</td>"
        f"<td>{escape(usage)}</td>"
        f"<td>{'Long Relief' if role != 'Long Relief' and bool(row.get('is_long_secondary', False)) else '-'}</td>"
        f"<td class='num'>{float(row.get('reliever_score_overall', row.get('starter_score_overall', 0.0))):.1f}</td>"
        "</tr>"
    )


def render_lineup_panel(
    hitter_roster: HitterRoster,
    split: str,
    title: str,
) -> str:
    lineup = build_lineup_order(
        hitter_roster.starters_by_position,
        split=split,
        smooth_handedness=True,
    )

    score_col = "batting_score_vs_rhp" if split == "vs_rhp" else "batting_score_vs_lhp"

    rows = []
    for spot, position, row in lineup:
        rows.append(
            "<tr>"
            f"<td>{spot}</td>"
            f"<td>{escape(str(row.get('bats', '')))}</td>"
            f"<td>{escape(str(row.get('name', '')))}</td>"
            f"<td>{escape(position)}</td>"
            f"<td class='num'>{float(row.get(score_col, 0.0)):.1f}</td>"
            "</tr>"
        )

    return f"""
<div class="panel lineup">
  <div class="panel-title"># &nbsp; B &nbsp; {escape(title)}</div>
  <table>
    <thead>
      <tr><th>#</th><th>B</th><th>Player</th><th>POS</th><th>Bat Score</th></tr>
    </thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
</div>
"""


def render_roster_checklist(
    hitter_roster: HitterRoster,
    pitcher_roster: PitcherRoster,
    change_statuses: dict[str, str],
) -> str:
    rows = []

    for position, row in hitter_roster.starters_by_position.items():
        role = f"Starter {position}"
        rows.append(
            render_checklist_row(
                row,
                role=role,
                status=change_statuses.get(role, ""),
            )
        )

    for idx, (_, row) in enumerate(hitter_roster.bench_players.iterrows(), start=1):
        role = f"Bench {idx}"
        rows.append(
            render_checklist_row(
                row,
                role=role,
                status=change_statuses.get(role, ""),
            )
        )

    for idx, (_, row) in enumerate(pitcher_roster.rotation.iterrows(), start=1):
        role = f"SP{idx}"
        rows.append(
            render_checklist_row(
                row,
                role=role,
                status=change_statuses.get(role, ""),
            )
        )

    for idx, (_, row) in enumerate(pitcher_roster.bullpen.iterrows(), start=1):
        role = f"RP{idx}"
        rows.append(
            render_checklist_row(
                row,
                role=role,
                status=change_statuses.get(role, ""),
            )
        )

    for idx, (_, row) in enumerate(pitcher_roster.lefty_specialist.iterrows(), start=1):
        role = f"LHP Specialist {idx}"
        rows.append(
            render_checklist_row(
                row,
                role=role,
                status=change_statuses.get(role, ""),
            )
        )

    for idx, (_, row) in enumerate(pitcher_roster.long_man.iterrows(), start=1):
        role = f"Long Man {idx}"
        rows.append(
            render_checklist_row(
                row,
                role=role,
                status=change_statuses.get(role, ""),
            )
        )

    return f"""
<section class="screen">
  <div class="panel">
    <div class="panel-title">Roster Checklist</div>
    <table>
      <thead>
        <tr>
          <th>Status</th>
          <th>Done</th>
          <th>Role</th>
          <th>Player</th>
          <th>Value</th>
          <th>Tier</th>
          <th>Year</th>
          <th>Type</th>
          <th>Variant</th>
        </tr>
      </thead>
      <tbody>{''.join(rows)}</tbody>
    </table>
  </div>
</section>
"""


def render_checklist_row(
    row: pd.Series,
    role: str,
    status: str = "",
) -> str:
    status_label = status.upper() if status else ""
    css_class = f"checklist-{status}" if status else ""

    return (
        f"<tr class='{escape(css_class)}'>"
        f"<td>{escape(status_label)}</td>"
        f"<td><input type='checkbox'></td>"
        f"<td>{escape(role)}</td>"
        f"<td>{escape(str(row.get('name', '')))}</td>"
        f"<td>{escape(str(row.get('card_value', '')))}</td>"
        f"<td>{escape(str(row.get('pt_tier', '')))}</td>"
        f"<td>{escape(str(row.get('pt_year', '')))}</td>"
        f"<td>{escape(str(row.get('pt_type', '')))}</td>"
        f"<td>{format_variant_flag(row)}</td>"
        "</tr>"
    )


def format_variant_flag(row: pd.Series) -> str:
    return "Yes" if is_variant_card(row) else "No"


def render_depth_chart_panel(
    hitter_roster: HitterRoster,
    ruleset: Ruleset,
    title: str,
) -> str:
    rows = []

    for position in DEPTH_ORDER:
        starter = hitter_roster.starters_by_position.get(position)
        if starter is None:
            continue

        backups = assign_position_backups(
            position=position,
            bench_players=hitter_roster.bench_players,
            ruleset=ruleset,
            limit=2,
        )

        util_1 = backups[0].get("name", "") if len(backups) >= 1 else ""
        util_2 = backups[1].get("name", "") if len(backups) >= 2 else ""

        rows.append(
            "<tr>"
            f"<td>{escape(position)}</td>"
            f"<td>{escape(str(starter.get('name', '')))}</td>"
            f"<td>{escape(str(util_1))}</td>"
            f"<td>If Starter tired</td>"
            f"<td>{escape(str(util_2))}</td>"
            f"<td>{'If Starter tired' if util_2 else ''}</td>"
            f"<td class='def-sub'></td>"
            "</tr>"
        )

    return f"""
<div class="panel depth">
  <div class="panel-title">POS &nbsp; {escape(title)}</div>
  <table>
    <thead>
      <tr>
        <th>POS</th><th>Depth Starter</th><th>Utility 1</th><th>Starts</th>
        <th>Utility 2</th><th>Starts</th><th>Defense Sub.</th>
      </tr>
    </thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
</div>
"""


def render_side_panel(
    hitter_roster: HitterRoster,
    split: str,
) -> str:
    pinch_hitters = build_pinch_hitters(
        hitter_roster.bench_players, split=split, limit=4
    )
    pinch_runners = build_pinch_runners(hitter_roster.bench_players, limit=4)

    ph_rows = "".join(
        f"<tr><td>{idx}</td><td>{escape(str(row.get('name', '')))}</td></tr>"
        for idx, (_, row) in enumerate(pinch_hitters.iterrows(), start=1)
    )

    pr_rows = "".join(
        f"<tr><td>{idx}</td><td>{escape(str(row.get('name', '')))}</td></tr>"
        for idx, (_, row) in enumerate(pinch_runners.iterrows(), start=1)
    )

    return f"""
<div class="side-stack">
  <div class="panel side">
    <div class="panel-title"># &nbsp; Pinch Hitters</div>
    <table><tbody>{ph_rows}</tbody></table>
  </div>
  <div class="panel side">
    <div class="panel-title"># &nbsp; Pinch Runners</div>
    <table><tbody>{pr_rows}</tbody></table>
  </div>
</div>
"""


CSS = """
:root {
  --bg: #100d13;
  --panel: #1c1b1f;
  --panel2: #241825;
  --grid: #4a414f;
  --text: #f2edf4;
  --muted: #b9aeba;
  --hot: #ff00d4;
  --warn: #4e151f;
}

* {
  box-sizing: border-box;
}

body {
  margin: 16px;
  background: radial-gradient(circle at top left, #231929, #0e0c10 55%);
  color: var(--text);
  font-family: Arial, Helvetica, sans-serif;
  font-size: 14px;
}

h1 {
  margin: 0 0 14px 0;
  font-size: 22px;
}

.screen {
  display: grid;
  gap: 14px;
  margin: 16px 0;
}

.two-col {
  grid-template-columns: 0.8fr 1.4fr;
}

.lineup-screen {
  grid-template-columns: 0.9fr 2.5fr 0.75fr;
  align-items: start;
}

.panel,
.summary {
  background: linear-gradient(90deg, rgba(255,255,255,0.03), rgba(255,0,212,0.04));
  border: 1px solid #2f2733;
  border-radius: 6px;
  overflow: hidden;
  box-shadow: 0 0 10px rgba(0,0,0,0.35);
}

.panel-title {
  background: var(--hot);
  color: white;
  font-weight: 700;
  padding: 4px 8px;
  font-size: 14px;
}

table {
  width: 100%;
  border-collapse: collapse;
}

th {
  background: var(--hot);
  color: white;
  text-align: left;
  font-weight: 700;
  padding: 4px 6px;
}

td {
  padding: 4px 6px;
  border-bottom: 1px solid rgba(255,255,255,0.08);
  white-space: nowrap;
}

tbody tr:nth-child(even) {
  background: rgba(255,255,255,0.025);
}

.num {
  text-align: right;
}

.summary {
  max-width: 900px;
}

.summary th {
  width: 220px;
  background: rgba(255,0,212,0.25);
}

.def-sub {
  background: rgba(110, 20, 32, 0.45);
}

.side-stack {
  display: grid;
  gap: 10px;
}

.side table td:first-child {
  width: 32px;
}

.checklist-new {
  background: rgba(38, 125, 65, 0.35) !important;
}

.checklist-changed {
  background: rgba(200, 145, 30, 0.38) !important;
}

.checklist-unchanged {
  opacity: 0.72;
}

.status-ok {
  color: #8ee6a2;
  font-weight: 700;
}

.status-over {
  color: #ffb3b3;
  background: rgba(180, 20, 35, 0.35);
  font-weight: 700;
}

input[type="checkbox"] {
  transform: scale(1.15);
}

@media print {
  body {
    background: white;
    color: black;
  }

  .panel,
  .summary {
    box-shadow: none;
  }

  .screen {
    break-inside: avoid;
  }
}
"""
