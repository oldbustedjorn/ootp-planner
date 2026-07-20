from __future__ import annotations

import argparse
import html
import re
from dataclasses import dataclass
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from ootp_opt.config import load_config
from ootp_opt.services.preset_service import (
    append_build_record,
    append_history_record_as_preset,
    delete_preset,
    find_record,
    format_build_number,
    infer_build_type_from_base_profile,
    load_build_records,
    next_build_number,
    preset_name_from_record,
    preset_roster_output_path,
    preset_upgrade_output_path,
    resolve_preset_build_metadata,
    slugify,
    update_preset_notes,
)
from ootp_opt.services.roster_build_service import RosterBuildRequest, build_roster
from ootp_opt.services.store_upgrade_service import (
    StoreUpgradeRequest,
    find_store_upgrades,
)

CARD_TYPES = ["2026Live", "AS", "FL", "HaH", "Leg", "NeL", "RS", "Snap", "UnH", "VET"]
TIERS = ["iron", "bronze", "silver", "gold", "diamond", "perfect"]
SCORING_ENVIRONMENTS = ["auto", "iron", "bronze", "silver", "gold", "diamond", "open", "none"]
TIER_SLOT_KEYS = ["P", "D", "G", "S", "B"]
MAX_OOTP_ROSTER_NAME_LENGTH = 30
GUI_PRESET_META_KEYS = {
    "_gui_title",
    "_gui_note",
    "_gui_roster_name",
    "_gui_build_type",
    "_gui_build_number",
    "_gui_html_output",
}
BUILD_TYPES = {
    "pt_standard": ("Perfect Team Regular", "standard_pt"),
    "pt_playoffs": ("Perfect Team Playoffs", "playoff_pt"),
    "pt_tournament": ("Perfect Team Tournament", "playoff_pt"),
}


@dataclass(frozen=True)
class GuiBuildRequest:
    roster_name: str
    build_type: str
    build_number: int
    preset_name: str | None
    roster_request: RosterBuildRequest


def main() -> None:
    parser = argparse.ArgumentParser(description="Launch the OOTP Planner local UI.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--config", default="config.toml")
    args = parser.parse_args()

    handler_cls = build_handler(config_path=args.config)
    server = ThreadingHTTPServer((args.host, args.port), handler_cls)
    print(f"OOTP Planner UI running at http://{args.host}:{args.port}")
    print("Press Ctrl+C to stop.")
    server.serve_forever()


def build_handler(config_path: str):
    class OotpPlannerHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/":
                query = parse_qs(parsed.query)
                self.respond_html(
                    render_home(
                        config_path=config_path,
                        selected_preset=text_value(query, "preset"),
                    )
                )
                return

            if parsed.path.startswith("/reports/"):
                self.respond_report(parsed.path.removeprefix("/reports/"))
                return

            self.respond_text("Not found", HTTPStatus.NOT_FOUND)

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/build":
                self.handle_build(form=None, config_path=config_path)
                return

            if parsed.path == "/preset-build":
                self.handle_preset_build(form=None, config_path=config_path)
                return

            if parsed.path == "/preset-upgrades":
                self.handle_preset_upgrades(form=None, config_path=config_path)
                return

            if parsed.path == "/history-save-preset":
                self.handle_history_save_preset(form=None, config_path=config_path)
                return

            if parsed.path == "/preset-delete":
                self.handle_preset_delete(form=None, config_path=config_path)
                return

            if parsed.path == "/preset-notes":
                self.handle_preset_notes(form=None, config_path=config_path)
                return

            self.respond_text("Not found", HTTPStatus.NOT_FOUND)

        def read_form(self) -> dict[str, list[str]]:
            length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(length).decode("utf-8")
            return parse_qs(raw_body, keep_blank_values=True)

        def handle_build(
            self,
            form: dict[str, list[str]] | None,
            config_path: str,
        ) -> None:
            form = form or self.read_form()
            try:
                build_number = next_build_number(load_build_records())
                gui_request = build_gui_request(
                    form,
                    config_path=config_path,
                    build_number=build_number,
                )
                result = build_roster(gui_request.roster_request)
                record = append_build_record(
                    build_number=gui_request.build_number,
                    roster_name=gui_request.roster_name,
                    build_type=gui_request.build_type,
                    preset_name=gui_request.preset_name,
                    base_profile=gui_request.roster_request.base_profile,
                    overrides=gui_request.roster_request.overrides,
                    html_output=result.html_output,
                    snapshot_path=result.snapshot_path,
                    status="success",
                )
                self.respond_html(
                    render_home(
                        config_path=config_path,
                        notice=(
                            f"Built {escape(gui_request.roster_name)} in "
                            f"{result.build_timing.total_seconds:.2f}s. "
                            f"Report: {report_link(result.html_output, 'Open roster')}"
                        ),
                        selected_record_id=record["id"],
                        selected_preset=gui_request.preset_name,
                    )
                )
            except Exception as exc:
                self.respond_html(
                    render_home(
                        config_path=config_path,
                        error=escape(f"{type(exc).__name__}: {exc}"),
                    ),
                    HTTPStatus.BAD_REQUEST,
                )

        def handle_preset_build(
            self,
            form: dict[str, list[str]] | None,
            config_path: str,
        ) -> None:
            form = form or self.read_form()
            preset_name = text_value(form, "preset_name")
            if not preset_name:
                self.respond_text("Not found", HTTPStatus.NOT_FOUND)
                return

            try:
                cfg = load_config(config_path)
                records = load_build_records()
                preset_cfg = cfg.get("tournament_presets", {}).get(preset_name, {})
                metadata = resolve_preset_build_metadata(
                    preset_name=preset_name,
                    preset_cfg=preset_cfg,
                    records=records,
                )
                build_number = metadata.get("build_number") or next_build_number(records)
                build_type = metadata.get("build_type") or infer_build_type_from_base_profile(
                    preset_cfg.get("base_profile")
                )
                roster_name = metadata.get("roster_name") or build_auto_roster_name(
                    build_type=build_type,
                    base_profile=preset_cfg.get("base_profile") or BUILD_TYPES[build_type][1],
                    build_number=build_number,
                    preset_name=preset_name,
                    overrides={},
                )
                html_output = metadata.get("html_output") or preset_roster_output_path(preset_name)
                gui_request = GuiBuildRequest(
                    roster_name=roster_name,
                    build_type=build_type,
                    build_number=build_number,
                    preset_name=preset_name,
                    roster_request=RosterBuildRequest(
                        config_path=config_path,
                        preset=preset_name,
                        html_output=html_output,
                    ),
                )
                result = build_roster(gui_request.roster_request)
                record = append_build_record(
                    build_number=gui_request.build_number,
                    roster_name=gui_request.roster_name,
                    build_type=gui_request.build_type,
                    preset_name=gui_request.preset_name,
                    base_profile=gui_request.roster_request.base_profile,
                    overrides=gui_request.roster_request.overrides,
                    html_output=result.html_output,
                    snapshot_path=result.snapshot_path,
                    status="success",
                )
                self.respond_html(
                    render_home(
                        config_path=config_path,
                        notice=(
                            f"Built {escape(gui_request.roster_name)} in "
                            f"{result.build_timing.total_seconds:.2f}s. "
                            f"Report: {report_link(result.html_output, 'Open roster')}"
                        ),
                        selected_record_id=record["id"],
                        selected_preset=preset_name,
                    )
                )
            except Exception as exc:
                self.respond_html(
                    render_home(
                        config_path=config_path,
                        error=escape(f"{type(exc).__name__}: {exc}"),
                        selected_preset=preset_name,
                    ),
                    HTTPStatus.BAD_REQUEST,
                )

        def handle_preset_upgrades(
            self,
            form: dict[str, list[str]] | None,
            config_path: str,
        ) -> None:
            form = form or self.read_form()
            preset_name = text_value(form, "preset_name")
            if not preset_name:
                self.respond_text("Not found", HTTPStatus.NOT_FOUND)
                return

            try:
                result = find_store_upgrades(
                    StoreUpgradeRequest(
                        config_path=config_path,
                        preset=preset_name,
                        min_gain=float_value(form, "min_gain") or 5.0,
                        html_output=preset_upgrade_output_path(preset_name),
                    )
                )
                self.respond_html(
                    render_home(
                        config_path=config_path,
                        notice=(
                            f"Built store upgrades for {escape(preset_name)}. "
                            f"Report: {report_link(result.html_output, 'Open upgrades')}"
                        ),
                        selected_preset=preset_name,
                    )
                )
            except Exception as exc:
                self.respond_html(
                    render_home(
                        config_path=config_path,
                        error=escape(f"{type(exc).__name__}: {exc}"),
                        selected_preset=preset_name,
                    ),
                    HTTPStatus.BAD_REQUEST,
                )

        def handle_history_save_preset(
            self,
            form: dict[str, list[str]] | None,
            config_path: str,
        ) -> None:
            form = form or self.read_form()
            record_id = text_value(form, "record_id")
            records = load_build_records()
            record = find_record(records, record_id)
            if record is None:
                self.respond_text("History record not found", HTTPStatus.NOT_FOUND)
                return

            try:
                preset_name = text_value(form, "preset_name") or preset_name_from_record(record)
                append_history_record_as_preset(
                    config_path=Path(config_path),
                    record=record,
                    preset_name=preset_name,
                )
                self.respond_html(
                    render_home(
                        config_path=config_path,
                        notice=(
                            f"Saved {escape(record.get('roster_name', 'history build'))} "
                            f"as preset {escape(preset_name)}."
                        ),
                        selected_preset=preset_name,
                    )
                )
            except Exception as exc:
                self.respond_html(
                    render_home(
                        config_path=config_path,
                        error=escape(f"{type(exc).__name__}: {exc}"),
                    ),
                    HTTPStatus.BAD_REQUEST,
                )

        def handle_preset_delete(
            self,
            form: dict[str, list[str]] | None,
            config_path: str,
        ) -> None:
            form = form or self.read_form()
            preset_name = text_value(form, "preset_name")
            if not preset_name:
                self.respond_text("Preset not found", HTTPStatus.NOT_FOUND)
                return

            try:
                deleted_files = delete_preset(Path(config_path), preset_name)
                cleanup_suffix = (
                    f" Removed {len(deleted_files)} output file(s)." if deleted_files else ""
                )
                self.respond_html(
                    render_home(
                        config_path=config_path,
                        notice=f"Deleted preset {escape(preset_name)}.{cleanup_suffix}",
                    )
                )
            except Exception as exc:
                self.respond_html(
                    render_home(
                        config_path=config_path,
                        error=escape(f"{type(exc).__name__}: {exc}"),
                        selected_preset=preset_name,
                    ),
                    HTTPStatus.BAD_REQUEST,
                )

        def handle_preset_notes(
            self,
            form: dict[str, list[str]] | None,
            config_path: str,
        ) -> None:
            form = form or self.read_form()
            preset_name = text_value(form, "preset_name")
            if not preset_name:
                self.respond_text("Preset not found", HTTPStatus.NOT_FOUND)
                return

            try:
                update_preset_notes(
                    config_path=Path(config_path),
                    preset_name=preset_name,
                    title=text_value(form, "title"),
                    note=text_value(form, "note"),
                )
                self.respond_html(
                    render_home(
                        config_path=config_path,
                        notice=f"Saved notes for {escape(preset_name)}.",
                        selected_preset=preset_name,
                    )
                )
            except Exception as exc:
                self.respond_html(
                    render_home(
                        config_path=config_path,
                        error=escape(f"{type(exc).__name__}: {exc}"),
                        selected_preset=preset_name,
                    ),
                    HTTPStatus.BAD_REQUEST,
                )

        def respond_report(self, encoded_name: str) -> None:
            report_name = unquote(encoded_name)
            report_path = Path("outputs") / Path(report_name).name
            if not report_path.exists():
                self.respond_text("Report not found", HTTPStatus.NOT_FOUND)
                return

            content = report_path.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        def respond_html(
            self,
            body: str,
            status: HTTPStatus = HTTPStatus.OK,
        ) -> None:
            encoded = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def respond_text(
            self,
            body: str,
            status: HTTPStatus = HTTPStatus.OK,
        ) -> None:
            encoded = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, format: str, *args) -> None:
            return

    return OotpPlannerHandler


def build_gui_request(
    form: dict[str, list[str]],
    config_path: str = "config.toml",
    build_number: int = 1,
) -> GuiBuildRequest:
    build_type = text_value(form, "build_type") or "pt_standard"
    if build_type not in BUILD_TYPES:
        raise ValueError(f"Unknown build type: {build_type}")

    preset_name = text_value(form, "preset_name")
    base_profile = text_value(form, "base_profile") or BUILD_TYPES[build_type][1]
    overrides = build_overrides_from_form(form, include_tournament=build_type == "pt_tournament")
    roster_name = text_value(form, "roster_name") or build_auto_roster_name(
        build_type=build_type,
        base_profile=base_profile,
        build_number=build_number,
        preset_name=preset_name,
        overrides=overrides,
    )
    html_output = build_html_output_path(roster_name)

    return GuiBuildRequest(
        roster_name=roster_name,
        build_type=build_type,
        build_number=build_number,
        preset_name=preset_name,
        roster_request=RosterBuildRequest(
            config_path=config_path,
            base_profile=None if preset_name else base_profile,
            preset=preset_name,
            overrides=overrides,
            html_output=html_output,
            debug=False,
        ),
    )


def build_overrides_from_form(
    form: dict[str, list[str]],
    include_tournament: bool,
) -> dict[str, Any]:
    overrides: dict[str, Any] = {}

    dh_enabled = text_value(form, "dh_enabled")
    if dh_enabled in {"true", "false"}:
        overrides["dh_enabled"] = dh_enabled == "true"

    for key in ["simulation_year", "ballpark_year"]:
        value = int_value(form, key)
        if value is not None:
            overrides[key] = value

    ballpark = text_value(form, "ballpark")
    if ballpark:
        overrides["ballpark"] = ballpark

    custom_park_factors = {
        key: value
        for key in [
            "ba_lh",
            "ba_rh",
            "hr_lh",
            "hr_rh",
            "doubles_overall",
            "triples_overall",
        ]
        if (value := float_value(form, key)) is not None
    }
    if custom_park_factors:
        overrides["custom_park_factors"] = custom_park_factors

    scoring_environment = text_value(form, "scoring_environment")
    if scoring_environment:
        overrides["scoring_environment"] = scoring_environment

    if not include_tournament:
        return overrides

    for key in ["tier_min", "tier_max", "live_mode"]:
        value = text_value(form, key)
        if value:
            overrides[key] = value

    allowed_card_types = list_values(form, "allowed_card_types")
    if allowed_card_types:
        overrides["allowed_card_types"] = allowed_card_types

    for key in [
        "card_value_min",
        "card_value_max",
        "card_year_min",
        "card_year_max",
        "point_cap_total",
        "variant_limit",
    ]:
        value = int_value(form, key)
        if value is not None:
            overrides[key] = value

    tier_slots = {
        tier: value
        for tier in TIER_SLOT_KEYS
        if (value := int_value(form, f"slot_{tier}")) is not None
    }
    if tier_slots:
        overrides["tier_slots"] = tier_slots

    return overrides


def render_home(
    config_path: str,
    notice: str | None = None,
    error: str | None = None,
    selected_record_id: str | None = None,
    selected_preset: str | None = None,
) -> str:
    cfg = load_config(config_path)
    presets = sorted(cfg.get("tournament_presets", {}).keys())
    selected_preset = selected_preset if selected_preset in presets else first_or_none(presets)
    records = load_build_records()

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>OOTP Planner</title>
  <style>{CSS}</style>
</head>
<body>
  <header class="topbar">
    <div>
      <h1>OOTP Planner</h1>
      <p>Build Perfect Team rosters from local exports.</p>
    </div>
  </header>

  <main>
    {render_alert("success", notice) if notice else ""}
    {render_alert("error", error) if error else ""}

    {render_presets_panel(cfg, presets, selected_preset)}

    <section class="workspace">
      <form method="post" action="/build" class="build-form">
        <div class="section-heading">
          <h2>Roster Build</h2>
          <button type="submit">Build Roster</button>
        </div>

        <div class="grid two">
          {field_text("OOTP roster name", "roster_name", placeholder="Blank = auto-name, max 30 chars", maxlength=MAX_OOTP_ROSTER_NAME_LENGTH)}
          {field_select("Build type", "build_type", [(key, label) for key, (label, _) in BUILD_TYPES.items()], "pt_standard")}
          {field_select("Base shape", "base_profile", [("standard_pt", "Regular PT"), ("playoff_pt", "Playoff/Tournament")], "standard_pt")}
          {field_select("Start from preset", "preset_name", [("", "No preset")] + [(preset, preset) for preset in presets], "")}
        </div>

        <div class="section-heading small">
          <h3>Scoring Environment</h3>
        </div>
        <div class="grid three">
          {field_select("Scoring tier", "scoring_environment", [(env, env.title()) for env in SCORING_ENVIRONMENTS], "auto")}
          {field_number("Simulation year", "simulation_year")}
          {field_text("Ballpark", "ballpark", placeholder="Fenway Park")}
          {field_number("Ballpark year", "ballpark_year")}
        </div>
        <details>
          <summary>Custom park factors</summary>
          <div class="grid six">
            {field_number("BA L", "ba_lh", step="0.001")}
            {field_number("BA R", "ba_rh", step="0.001")}
            {field_number("HR L", "hr_lh", step="0.001")}
            {field_number("HR R", "hr_rh", step="0.001")}
            {field_number("2B", "doubles_overall", step="0.001")}
            {field_number("3B", "triples_overall", step="0.001")}
          </div>
        </details>

        <div class="section-heading small">
          <h3>Tournament Requirements</h3>
        </div>
        <div class="grid four">
          {field_select("DH", "dh_enabled", [("", "Default"), ("true", "Yes"), ("false", "No")], "")}
          {field_select("Tier min", "tier_min", [("", "None")] + [(tier, tier.title()) for tier in TIERS], "")}
          {field_select("Tier max", "tier_max", [("", "None")] + [(tier, tier.title()) for tier in TIERS], "")}
          {field_select("Live mode", "live_mode", [("", "Default"), ("all", "All"), ("live", "Live only"), ("non_live", "Non-live")], "")}
          {field_number("Card value min", "card_value_min")}
          {field_number("Card value max", "card_value_max")}
          {field_number("Card year min", "card_year_min")}
          {field_number("Card year max", "card_year_max")}
          {field_number("Point cap", "point_cap_total")}
          {field_number("Variant limit", "variant_limit", placeholder="blank = no limit, 0 = none")}
        </div>

        <fieldset>
          <legend>Allowed card types</legend>
          <div class="checks">
            {"".join(render_checkbox(card_type) for card_type in CARD_TYPES)}
          </div>
        </fieldset>

        <fieldset>
          <legend>Tier slots</legend>
          <div class="grid six">
            {"".join(field_number(slot, f"slot_{slot}") for slot in TIER_SLOT_KEYS)}
          </div>
        </fieldset>
      </form>

      <aside class="history">
        <div class="section-heading">
          <h2>Build History</h2>
        </div>
        {render_history(records, selected_record_id)}
      </aside>
    </section>
  </main>
</body>
</html>"""


def render_presets_panel(
    cfg: dict[str, Any],
    presets: list[str],
    selected_preset: str | None,
) -> str:
    if not presets:
        return ""

    preset_links = "\n".join(
        render_preset_link(
            preset_name=preset_name,
            preset_cfg=cfg["tournament_presets"][preset_name],
            selected=preset_name == selected_preset,
        )
        for preset_name in presets
    )
    detail = render_preset_detail(
        selected_preset,
        cfg["tournament_presets"].get(selected_preset, {}) if selected_preset else {},
    )

    return f"""
<section class="preset-panel">
  <div class="section-heading">
    <h2>Presets</h2>
  </div>
  <div class="preset-layout">
    <nav class="preset-list">{preset_links}</nav>
    {detail}
  </div>
</section>
"""


def render_preset_link(
    preset_name: str,
    preset_cfg: dict[str, Any],
    selected: bool,
) -> str:
    selected_class = " selected" if selected else ""
    title = preset_display_title(preset_name, preset_cfg)
    id_line = f"{preset_name} | {format_preset_badges(preset_cfg)}"
    return f"""
<a class="preset-link{selected_class}" href="/?preset={escape(preset_name)}">
  <span>{escape(title)}</span>
  <small>{escape(id_line)}</small>
</a>
"""


def render_preset_detail(preset_name: str | None, preset_cfg: dict[str, Any]) -> str:
    if not preset_name:
        return '<div class="preset-detail"><p class="muted">No preset selected.</p></div>'

    roster_output = preset_roster_output_path(preset_name)
    upgrade_output = preset_upgrade_output_path(preset_name)
    title = preset_display_title(preset_name, preset_cfg)
    note = str(preset_cfg.get("_gui_note") or "")
    note_html = f'<p class="preset-note">{escape(note)}</p>' if note else ""

    return f"""
<div class="preset-detail">
  <div class="section-heading">
    <div>
      <h3>{escape(title)}</h3>
      <p class="muted">ID: {escape(preset_name)} | {escape(format_preset_badges(preset_cfg))}</p>
    </div>
  </div>
  {note_html}
  <dl class="preset-fields">
    {render_preset_fields(preset_cfg)}
  </dl>
  <form method="post" action="/preset-notes" class="preset-note-form">
    <input type="hidden" name="preset_name" value="{escape(preset_name)}">
    <label><span>Display title</span><input type="text" name="title" value="{escape(str(preset_cfg.get("_gui_title") or ""))}" placeholder="{escape(preset_name)}"></label>
    <label><span>Tournament note</span><textarea name="note" rows="3" placeholder="Tournament name, server slot, or reminder">{escape(note)}</textarea></label>
    <button type="submit">Save Notes</button>
  </form>
  <div class="preset-actions">
    <form method="post" action="/preset-build">
      <input type="hidden" name="preset_name" value="{escape(preset_name)}">
      <button type="submit">Build Roster</button>
    </form>
    <form method="post" action="/preset-upgrades">
      <input type="hidden" name="preset_name" value="{escape(preset_name)}">
      <label class="inline-field"><span>Min gain</span><input type="number" step="0.1" name="min_gain" value="5"></label>
      <button type="submit">Find Upgrades</button>
    </form>
    <form method="post" action="/preset-delete">
      <input type="hidden" name="preset_name" value="{escape(preset_name)}">
      <button type="submit" class="danger">Delete Preset</button>
    </form>
    <div class="preset-report-links">
      {report_link(roster_output, "Open roster") if Path(roster_output).exists() else '<span class="muted">No roster report yet</span>'}
      {report_link(upgrade_output, "Open upgrades") if Path(upgrade_output).exists() else '<span class="muted">No upgrade report yet</span>'}
    </div>
  </div>
</div>
"""


def preset_display_title(preset_name: str, preset_cfg: dict[str, Any]) -> str:
    return str(preset_cfg.get("_gui_title") or preset_name)


def render_preset_fields(preset_cfg: dict[str, Any]) -> str:
    rows = []
    for key, value in flatten_preset_summary(preset_cfg):
        rows.append(f"<dt>{escape(key)}</dt><dd>{escape(format_preset_value(value))}</dd>")
    return "\n".join(rows)


def flatten_preset_summary(preset_cfg: dict[str, Any]) -> list[tuple[str, Any]]:
    ordered_keys = [
        "base_profile",
        "dh_enabled",
        "tier_min",
        "tier_max",
        "card_value_min",
        "card_value_max",
        "live_mode",
        "allowed_card_types",
        "card_year_min",
        "card_year_max",
        "simulation_year",
        "scoring_environment",
        "ballpark",
        "ballpark_year",
        "point_cap_total",
        "variant_limit",
        "tier_slots",
        "custom_park_factors",
    ]
    return [(key, preset_cfg[key]) for key in ordered_keys if key in preset_cfg]


def format_preset_badges(preset_cfg: dict[str, Any]) -> str:
    badges = []
    if preset_cfg.get("base_profile"):
        badges.append(str(preset_cfg["base_profile"]))
    if preset_cfg.get("tier_min") or preset_cfg.get("tier_max"):
        badges.append(format_range_badge(preset_cfg.get("tier_min"), preset_cfg.get("tier_max")))
    if preset_cfg.get("card_value_min") or preset_cfg.get("card_value_max"):
        badges.append(
            format_range_badge(
                preset_cfg.get("card_value_min"),
                preset_cfg.get("card_value_max"),
                prefix="v",
            )
        )
    if preset_cfg.get("live_mode") and preset_cfg.get("live_mode") != "all":
        badges.append(str(preset_cfg["live_mode"]))
    if preset_cfg.get("simulation_year"):
        badges.append(f"Y{preset_cfg['simulation_year']}")
    if preset_cfg.get("scoring_environment"):
        badges.append(f"score {preset_cfg['scoring_environment']}")
    if "dh_enabled" in preset_cfg:
        badges.append("DH" if preset_cfg["dh_enabled"] else "NoDH")
    if preset_cfg.get("point_cap_total"):
        badges.append(f"cap {preset_cfg['point_cap_total']}")
    if preset_cfg.get("variant_limit") is not None:
        badges.append(f"var {preset_cfg['variant_limit']}")
    if preset_cfg.get("tier_slots"):
        badges.append("slots")
    return " | ".join(badges) or "Preset"


def format_range_badge(value_min: Any, value_max: Any, prefix: str = "") -> str:
    if value_min and value_max:
        return f"{prefix}{value_min}-{value_max}"
    if value_max:
        return f"{prefix}<={value_max}"
    return f"{prefix}>={value_min}"


def format_preset_value(value: Any) -> str:
    if isinstance(value, dict):
        return ", ".join(f"{key}: {item}" for key, item in value.items())
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    return str(value)


def render_history(records: list[dict[str, Any]], selected_record_id: str | None) -> str:
    if not records:
        return '<p class="muted">No GUI builds yet.</p>'

    rows = []
    for record in records[:20]:
        selected = " selected" if record.get("id") == selected_record_id else ""
        report = report_link(record["html_output"], "Open HTML")
        rows.append(
            f"""<article class="history-item{selected}">
  <div class="history-title">{escape(record["roster_name"])}</div>
  <div class="history-meta">#{format_build_number(record.get("build_number"))} - {escape(record["build_type"])} - {escape(record["created_at"])}</div>
  <div class="history-actions">
    {report}
    {render_save_history_preset_form(record)}
  </div>
</article>"""
        )
    return "\n".join(rows)


def render_save_history_preset_form(record: dict[str, Any]) -> str:
    if record.get("preset_name"):
        return '<span class="muted">Preset build</span>'

    suggested = preset_name_from_record(record)
    return f"""
<form method="post" action="/history-save-preset" class="inline-action">
  <input type="hidden" name="record_id" value="{escape(record.get('id', ''))}">
  <input type="text" name="preset_name" value="{escape(suggested)}" aria-label="Preset name">
  <button type="submit">Save as Preset</button>
</form>
"""


def build_html_output_path(roster_name: str) -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return str(Path("outputs") / f"gui_{slugify(roster_name)}_{timestamp}.html")


def build_auto_roster_name(
    build_type: str,
    base_profile: str,
    build_number: int,
    preset_name: str | None,
    overrides: dict[str, Any],
) -> str:
    prefix = build_type_prefix(build_type, base_profile)
    number = format_build_number(build_number)

    if preset_name:
        return fit_roster_name([prefix, number, shorten_preset_name(preset_name)])

    parts = [prefix, number]

    if overrides.get("tier_min") or overrides.get("tier_max"):
        parts.append(tier_range_token(overrides.get("tier_min"), overrides.get("tier_max")))

    if overrides.get("card_value_min") is not None or overrides.get("card_value_max") is not None:
        parts.append(value_range_token(overrides.get("card_value_min"), overrides.get("card_value_max")))

    if overrides.get("live_mode") == "non_live":
        parts.append("NL")
    elif overrides.get("live_mode") == "live":
        parts.append("Live")

    if overrides.get("simulation_year") is not None:
        parts.append(f"Y{overrides['simulation_year']}")

    if overrides.get("scoring_environment") not in (None, "auto"):
        parts.append(f"Sc{tier_abbrev(overrides['scoring_environment'])}")

    if overrides.get("dh_enabled") is False:
        parts.append("NoDH")
    elif overrides.get("dh_enabled") is True and build_type == "pt_tournament":
        parts.append("DH")

    if overrides.get("card_year_min") is not None or overrides.get("card_year_max") is not None:
        parts.append(year_range_token(overrides.get("card_year_min"), overrides.get("card_year_max")))

    if overrides.get("point_cap_total") is not None:
        parts.append(f"C{overrides['point_cap_total']}")

    if overrides.get("tier_slots"):
        parts.append("Slots")

    if overrides.get("allowed_card_types"):
        parts.append("+".join(str(item) for item in overrides["allowed_card_types"]))

    return fit_roster_name(parts)


def build_type_prefix(build_type: str, base_profile: str) -> str:
    if build_type == "pt_standard":
        return "PT"
    if build_type == "pt_playoffs":
        return "PTPO"
    if build_type == "pt_tournament":
        return "T"
    return base_profile[:6].upper()


def tier_range_token(tier_min: Any, tier_max: Any) -> str:
    min_token = tier_abbrev(tier_min) if tier_min else ""
    max_token = tier_abbrev(tier_max) if tier_max else ""
    if min_token and max_token:
        return f"{min_token}-{max_token}"
    if max_token:
        return f"{max_token}max"
    return f"{min_token}+"


def value_range_token(value_min: Any, value_max: Any) -> str:
    if value_min is not None and value_max is not None:
        return f"{value_min}-{value_max}"
    if value_max is not None:
        return f"v{value_max}"
    return f"v{value_min}+"


def year_range_token(year_min: Any, year_max: Any) -> str:
    if year_min is not None and year_max is not None:
        return f"{year_min}-{year_max}"
    if year_max is not None:
        return f"<={year_max}"
    return f">={year_min}"


def tier_abbrev(value: Any) -> str:
    return {
        "iron": "I",
        "bronze": "B",
        "silver": "S",
        "gold": "G",
        "diamond": "D",
        "perfect": "P",
    }.get(str(value).lower(), str(value)[:1].upper())


def shorten_preset_name(preset_name: str) -> str:
    text = preset_name.replace("tournament", "tourn")
    text = text.replace("diamond", "D")
    text = text.replace("perfect", "P")
    text = text.replace("bronze", "B")
    text = text.replace("silver", "S")
    text = text.replace("gold", "G")
    text = text.replace("iron", "I")
    words = [word for word in re.split(r"[_\s]+", text) if word]
    return "-".join(words)


def trim_roster_name(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", value).strip(" -_")
    return cleaned[:MAX_OOTP_ROSTER_NAME_LENGTH].rstrip(" -_") or "Roster"


def fit_roster_name(parts: list[str]) -> str:
    fitted: list[str] = []
    for part in parts:
        candidate = "-".join([*fitted, part]) if fitted else part
        if len(candidate) <= MAX_OOTP_ROSTER_NAME_LENGTH:
            fitted.append(part)

    if fitted:
        return "-".join(fitted)

    return trim_roster_name(parts[0] if parts else "Roster")


def text_value(form: dict[str, list[str]], key: str) -> str | None:
    value = form.get(key, [""])[0].strip()
    return value or None


def list_values(form: dict[str, list[str]], key: str) -> list[str]:
    return [value.strip() for value in form.get(key, []) if value.strip()]


def int_value(form: dict[str, list[str]], key: str) -> int | None:
    value = text_value(form, key)
    if value is None:
        return None
    return int(value)


def float_value(form: dict[str, list[str]], key: str) -> float | None:
    value = text_value(form, key)
    if value is None:
        return None
    return float(value)


def field_text(
    label: str,
    name: str,
    value: str = "",
    placeholder: str = "",
    maxlength: int | None = None,
) -> str:
    maxlength_attr = f' maxlength="{maxlength}"' if maxlength is not None else ""
    return f"""<label><span>{escape(label)}</span><input type="text" name="{escape(name)}" value="{escape(value)}" placeholder="{escape(placeholder)}"{maxlength_attr}></label>"""


def field_number(
    label: str,
    name: str,
    value: str = "",
    placeholder: str = "",
    step: str = "1",
) -> str:
    return f"""<label><span>{escape(label)}</span><input type="number" step="{escape(step)}" name="{escape(name)}" value="{escape(value)}" placeholder="{escape(placeholder)}"></label>"""


def field_select(
    label: str,
    name: str,
    options: list[tuple[str, str]],
    selected: str,
) -> str:
    option_html = "".join(
        f"""<option value="{escape(value)}"{" selected" if value == selected else ""}>{escape(text)}</option>"""
        for value, text in options
    )
    return f"""<label><span>{escape(label)}</span><select name="{escape(name)}">{option_html}</select></label>"""


def render_checkbox(card_type: str) -> str:
    return f"""<label class="check"><input type="checkbox" name="allowed_card_types" value="{escape(card_type)}"><span>{escape(card_type)}</span></label>"""


def render_alert(kind: str, message: str) -> str:
    return f"""<div class="alert {escape(kind)}">{message}</div>"""


def report_link(html_output: str, label: str = "Open HTML") -> str:
    name = Path(html_output).name
    return f"""<a href="/reports/{escape(name)}" target="_blank" rel="noreferrer">{escape(label)}</a>"""


def escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def first_or_none(items: list[str]) -> str | None:
    return items[0] if items else None


CSS = """
:root {
  color-scheme: light;
  --bg: #f5f7f9;
  --panel: #ffffff;
  --line: #d9e0e7;
  --text: #17202a;
  --muted: #5b6875;
  --accent: #1f6feb;
  --accent-dark: #174ea6;
  --error: #b42318;
  --success: #16794c;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  font-family: Segoe UI, Arial, sans-serif;
  background: var(--bg);
  color: var(--text);
}
.topbar {
  background: #142033;
  color: #fff;
  padding: 18px 28px;
}
h1, h2, h3, p { margin: 0; }
.topbar p { color: #c9d4df; margin-top: 4px; }
main { padding: 22px; }
.workspace {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 340px;
  gap: 18px;
  align-items: start;
}
.build-form, .history, .preset-panel {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 18px;
}
.preset-panel {
  margin-bottom: 18px;
}
.preset-layout {
  display: grid;
  grid-template-columns: 360px minmax(0, 1fr);
  gap: 14px;
}
.preset-list {
  display: grid;
  gap: 8px;
  max-height: 520px;
  overflow: auto;
  padding-right: 4px;
}
.preset-link {
  display: grid;
  gap: 3px;
  padding: 10px;
  border: 1px solid var(--line);
  border-radius: 8px;
  text-decoration: none;
  color: var(--text);
  background: #fbfcfd;
}
.preset-link:hover, .preset-link.selected {
  border-color: var(--accent);
  background: #eef5ff;
}
.preset-link span {
  font-weight: 700;
}
.preset-link small {
  color: var(--muted);
}
.preset-detail {
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 14px;
  min-height: 260px;
}
.preset-fields {
  display: grid;
  grid-template-columns: 160px minmax(0, 1fr);
  gap: 6px 10px;
  margin: 0 0 14px;
}
.preset-fields dt {
  color: var(--muted);
  font-weight: 700;
}
.preset-fields dd {
  margin: 0;
}
.preset-actions {
  display: flex;
  align-items: end;
  flex-wrap: wrap;
  gap: 10px;
}
.preset-note {
  margin-bottom: 14px;
  padding: 10px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: #fbfcfd;
}
.preset-note-form {
  display: grid;
  gap: 10px;
  margin-bottom: 14px;
}
.preset-actions form {
  display: flex;
  align-items: end;
  gap: 8px;
}
.preset-report-links {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}
.inline-field {
  width: 120px;
}
.section-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
}
.section-heading.small {
  margin-top: 22px;
  margin-bottom: 10px;
}
.grid {
  display: grid;
  gap: 12px;
}
.grid.two { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.grid.three { grid-template-columns: repeat(3, minmax(0, 1fr)); }
.grid.four { grid-template-columns: repeat(4, minmax(0, 1fr)); }
.grid.six { grid-template-columns: repeat(6, minmax(0, 1fr)); }
label span, legend {
  display: block;
  margin-bottom: 5px;
  color: var(--muted);
  font-size: 13px;
  font-weight: 600;
}
input, select, textarea {
  width: 100%;
  min-height: 36px;
  border: 1px solid #b9c3cf;
  border-radius: 6px;
  padding: 7px 9px;
  font: inherit;
  color: var(--text);
  background: #fff;
}
textarea {
  min-height: 82px;
  resize: vertical;
}
button {
  border: 0;
  border-radius: 6px;
  padding: 10px 14px;
  background: var(--accent);
  color: #fff;
  font-weight: 700;
  cursor: pointer;
}
button:hover { background: var(--accent-dark); }
button.danger { background: #b42318; }
button.danger:hover { background: #8f1c14; }
details, fieldset {
  margin-top: 14px;
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 12px;
}
summary {
  cursor: pointer;
  color: var(--muted);
  font-weight: 700;
}
.checks {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 8px;
}
.check {
  display: flex;
  align-items: center;
  gap: 7px;
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: 8px;
}
.check input { width: auto; min-height: auto; }
.check span { margin: 0; color: var(--text); }
.history-item {
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 10px;
  margin-bottom: 10px;
}
.history-item.selected { border-color: var(--success); }
.history-title { font-weight: 700; }
.history-meta {
  color: var(--muted);
  font-size: 12px;
  margin: 4px 0 8px;
}
.history-actions {
  display: grid;
  gap: 8px;
}
.inline-action {
  display: flex;
  gap: 8px;
  align-items: center;
}
.inline-action input {
  min-width: 0;
}
.alert {
  border-radius: 8px;
  padding: 12px 14px;
  margin-bottom: 14px;
  background: var(--panel);
  border: 1px solid var(--line);
}
.alert.success { border-color: var(--success); color: var(--success); }
.alert.error { border-color: var(--error); color: var(--error); }
a { color: var(--accent); font-weight: 700; }
.muted { color: var(--muted); }
@media (max-width: 960px) {
  .workspace, .preset-layout { grid-template-columns: 1fr; }
  .grid.two, .grid.three, .grid.four, .grid.six, .checks {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
@media (max-width: 560px) {
  main { padding: 12px; }
  .grid.two, .grid.three, .grid.four, .grid.six, .checks {
    grid-template-columns: 1fr;
  }
}
"""


if __name__ == "__main__":
    main()
