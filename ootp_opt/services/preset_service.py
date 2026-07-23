from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from ootp_opt.config import load_config


def append_build_record(
    *,
    build_number: int,
    roster_name: str,
    build_type: str,
    preset_name: str | None,
    base_profile: str | None,
    overrides: dict[str, Any],
    html_output: str,
    snapshot_path: str,
    status: str,
    build_method: str = "greedy",
) -> dict[str, Any]:
    records = load_build_records()
    created_at = datetime.now().replace(microsecond=0).isoformat()
    record = {
        "id": f"{format_build_number(build_number)}-{slugify(roster_name)}",
        "build_number": build_number,
        "created_at": created_at,
        "roster_name": roster_name,
        "build_type": build_type,
        "preset_name": preset_name,
        "base_profile": base_profile,
        "overrides": overrides,
        "html_output": html_output,
        "snapshot_path": str(snapshot_path),
        "status": status,
        "build_method": build_method,
    }
    records.insert(0, record)
    save_build_records(records)
    return record


def load_build_records() -> list[dict[str, Any]]:
    path = registry_path()
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def save_build_records(records: list[dict[str, Any]]) -> None:
    path = registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(records, indent=2), encoding="utf-8")


def find_record(
    records: list[dict[str, Any]], record_id: str | None
) -> dict[str, Any] | None:
    if not record_id:
        return None
    return next((record for record in records if record.get("id") == record_id), None)


def preset_name_from_record(record: dict[str, Any]) -> str:
    number = format_build_number(record.get("build_number"))
    base = slugify(str(record.get("roster_name") or f"build_{number}"))
    if number != "---" and not base.startswith(number):
        base = f"{number}_{base}"
    return safe_preset_name(base)


def safe_preset_name(value: str) -> str:
    text = slugify(value)
    if not text:
        text = "preset"
    if text[0].isdigit():
        text = f"preset_{text}"
    return text


def append_history_record_as_preset(
    config_path: Path,
    record: dict[str, Any],
    preset_name: str,
) -> None:
    preset_name = safe_preset_name(preset_name)
    cfg = load_config(config_path)
    if preset_name in cfg.get("tournament_presets", {}):
        raise ValueError(f"Preset '{preset_name}' already exists.")

    preset_cfg = preset_config_from_history_record(record, cfg)
    append_preset_block(config_path, preset_name, preset_cfg)


def preset_config_from_history_record(
    record: dict[str, Any],
    cfg: dict[str, Any],
) -> dict[str, Any]:
    if record.get("preset_name"):
        source = cfg.get("tournament_presets", {}).get(record["preset_name"])
        if source:
            return dict(source)

    preset_cfg: dict[str, Any] = {
        "base_profile": record.get("base_profile") or "playoff_pt"
    }
    preset_cfg.update(record.get("overrides") or {})
    preset_cfg["build_method"] = str(record.get("build_method") or "greedy")
    preset_cfg["_gui_title"] = str(record.get("roster_name") or "")
    preset_cfg["_gui_roster_name"] = str(record.get("roster_name") or "")
    preset_cfg["_gui_build_type"] = str(record.get("build_type") or "")
    if str(record.get("build_number", "")).isdigit():
        preset_cfg["_gui_build_number"] = int(record["build_number"])
    if record.get("html_output"):
        preset_cfg["_gui_html_output"] = str(record["html_output"])
    return preset_cfg


def append_preset_block(
    config_path: Path,
    preset_name: str,
    preset_cfg: dict[str, Any],
) -> None:
    lines = ["", f"[tournament_presets.{preset_name}]"]
    nested_tables: list[tuple[str, dict[str, Any]]] = []

    for key, value in preset_cfg.items():
        if isinstance(value, dict):
            nested_tables.append((key, value))
        else:
            lines.append(f"{key} = {toml_value(value)}")

    for key, values in nested_tables:
        lines.extend(["", f"[tournament_presets.{preset_name}.{key}]"])
        for nested_key, nested_value in values.items():
            lines.append(f"{nested_key} = {toml_value(nested_value)}")

    text = config_path.read_text(encoding="utf-8")
    suffix = "\n" if text.endswith("\n") else "\n\n"
    config_path.write_text(
        text + suffix + "\n".join(lines).strip() + "\n", encoding="utf-8"
    )


def delete_preset_block(config_path: Path, preset_name: str) -> None:
    cfg = load_config(config_path)
    if preset_name not in cfg.get("tournament_presets", {}):
        raise ValueError(f"Preset '{preset_name}' does not exist.")

    text = config_path.read_text(encoding="utf-8")
    pattern = re.compile(
        rf"^\[tournament_presets\.{re.escape(preset_name)}(?:\.[^\]]+)?\]\n.*?(?=^\[|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    new_text, count = pattern.subn("", text)
    if count == 0:
        raise ValueError(f"Could not find TOML block for preset '{preset_name}'.")

    config_path.write_text(
        re.sub(r"\n{3,}", "\n\n", new_text).rstrip() + "\n", encoding="utf-8"
    )


def delete_preset(config_path: Path, preset_name: str) -> list[Path]:
    cfg = load_config(config_path)
    preset_cfg = dict(cfg.get("tournament_presets", {}).get(preset_name) or {})
    if not preset_cfg:
        raise ValueError(f"Preset '{preset_name}' does not exist.")

    output_paths = preset_owned_output_paths(preset_name, preset_cfg)
    delete_preset_block(config_path, preset_name)
    return delete_existing_files(output_paths)


def preset_owned_output_paths(
    preset_name: str,
    preset_cfg: dict[str, Any],
) -> list[Path]:
    candidates = [
        Path(preset_roster_output_path(preset_name)),
        Path(preset_upgrade_output_path(preset_name)),
    ]
    if preset_cfg.get("_gui_html_output"):
        candidates.append(Path(str(preset_cfg["_gui_html_output"])))

    owned_paths: list[Path] = []
    for path in candidates:
        output_path = safe_output_path(path)
        if output_path is None:
            continue
        owned_paths.append(output_path)
        if output_path.suffix.lower() == ".html":
            owned_paths.append(output_path.with_suffix(".snapshot.json"))

    return unique_paths(owned_paths)


def safe_output_path(path: Path) -> Path | None:
    output_dir = Path("outputs").resolve()
    resolved = path.resolve()
    try:
        resolved.relative_to(output_dir)
    except ValueError:
        return None
    return resolved


def unique_paths(paths: list[Path]) -> list[Path]:
    seen: set[Path] = set()
    unique: list[Path] = []
    for path in paths:
        if path in seen:
            continue
        seen.add(path)
        unique.append(path)
    return unique


def delete_existing_files(paths: list[Path]) -> list[Path]:
    deleted: list[Path] = []
    for path in paths:
        if not path.exists() or not path.is_file():
            continue
        try:
            path.unlink()
        except PermissionError:
            continue
        else:
            deleted.append(path)
    return deleted


def update_preset_notes(
    config_path: Path,
    preset_name: str,
    title: str | None,
    note: str | None,
) -> None:
    cfg = load_config(config_path)
    preset_cfg = dict(cfg.get("tournament_presets", {}).get(preset_name) or {})
    if not preset_cfg:
        raise ValueError(f"Preset '{preset_name}' does not exist.")

    title = (title or "").strip()
    note = (note or "").strip()
    if title:
        preset_cfg["_gui_title"] = title
    else:
        preset_cfg.pop("_gui_title", None)

    if note:
        preset_cfg["_gui_note"] = note
    else:
        preset_cfg.pop("_gui_note", None)

    delete_preset_block(config_path, preset_name)
    append_preset_block(config_path, preset_name, preset_cfg)


def update_preset_build_method(
    config_path: Path,
    preset_name: str,
    build_method: str,
) -> None:
    if build_method not in {"greedy", "optimizer"}:
        raise ValueError(f"Unknown build method: {build_method}")

    cfg = load_config(config_path)
    preset_cfg = dict(cfg.get("tournament_presets", {}).get(preset_name) or {})
    if not preset_cfg:
        raise ValueError(f"Preset '{preset_name}' does not exist.")
    if preset_cfg.get("build_method") == build_method:
        return

    preset_cfg["build_method"] = build_method
    delete_preset_block(config_path, preset_name)
    append_preset_block(config_path, preset_name, preset_cfg)


def resolve_preset_build_metadata(
    preset_name: str,
    preset_cfg: dict[str, Any],
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    explicit = preset_metadata_from_config(preset_cfg)
    if explicit:
        return explicit

    source_record = find_source_record_for_history_preset(preset_name, records)
    if source_record:
        return preset_metadata_from_record(source_record)

    previous_preset_record = next(
        (record for record in records if record.get("preset_name") == preset_name),
        None,
    )
    if previous_preset_record:
        return preset_metadata_from_record(previous_preset_record)

    return {}


def preset_metadata_from_config(preset_cfg: dict[str, Any]) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    if preset_cfg.get("_gui_roster_name"):
        metadata["roster_name"] = str(preset_cfg["_gui_roster_name"])
    if preset_cfg.get("_gui_build_type"):
        metadata["build_type"] = str(preset_cfg["_gui_build_type"])
    if str(preset_cfg.get("_gui_build_number", "")).isdigit():
        metadata["build_number"] = int(preset_cfg["_gui_build_number"])
    if preset_cfg.get("_gui_html_output"):
        metadata["html_output"] = str(preset_cfg["_gui_html_output"])
    return metadata


def find_source_record_for_history_preset(
    preset_name: str,
    records: list[dict[str, Any]],
) -> dict[str, Any] | None:
    match = re.match(r"^preset_(\d{3})_", preset_name)
    if not match:
        return None

    build_number = int(match.group(1))
    return next(
        (record for record in records if record.get("build_number") == build_number),
        None,
    )


def preset_metadata_from_record(record: dict[str, Any]) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    if record.get("roster_name"):
        metadata["roster_name"] = str(record["roster_name"])
    if record.get("build_type"):
        metadata["build_type"] = str(record["build_type"])
    if str(record.get("build_number", "")).isdigit():
        metadata["build_number"] = int(record["build_number"])
    if record.get("html_output"):
        metadata["html_output"] = str(record["html_output"])
    return metadata


def infer_build_type_from_base_profile(base_profile: Any) -> str:
    return "pt_standard" if base_profile == "standard_pt" else "pt_tournament"


def toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        return "[" + ", ".join(toml_value(item) for item in value) + "]"
    return json.dumps(str(value))


def next_build_number(records: list[dict[str, Any]]) -> int:
    numbers = [
        int(record["build_number"])
        for record in records
        if str(record.get("build_number", "")).isdigit()
    ]
    return (max(numbers) + 1) if numbers else 1


def format_build_number(value: object) -> str:
    if str(value or "").isdigit():
        return f"{int(value):03d}"
    return "---"


def registry_path() -> Path:
    return Path("outputs") / "roster_build_registry.json"


def preset_roster_output_path(preset_name: str) -> str:
    return str(Path("outputs") / f"preset_roster_{slugify(preset_name)}.html")


def preset_upgrade_output_path(preset_name: str) -> str:
    return str(Path("outputs") / f"preset_upgrades_{slugify(preset_name)}.html")


def slugify(value: str) -> str:
    text = value.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_") or "roster"
