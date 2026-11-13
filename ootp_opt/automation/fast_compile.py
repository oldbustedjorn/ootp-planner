from __future__ import annotations

from typing import Any

from ootp_opt.automation.ui_plan import build_ui_plan


ASSIGNMENT_DRAG_SECTIONS = ("pitching", "vs_rhp", "vs_lhp")
ASSIGNMENT_DRAG_FAMILIES = (
    "rotation",
    "starters",
    "depth",
    "pinch_hitters",
    "pinch_runners",
)


def compile_assignment_moves(
    manifest: dict[str, Any],
    section: str,
    family: str,
    *,
    sources: dict[str, tuple[int, int]],
    targets: dict[str, tuple[int, int]],
) -> list[dict[str, Any]]:
    if section not in ASSIGNMENT_DRAG_SECTIONS:
        raise ValueError(f"Unknown assignment drag section: {section}")
    if family not in ASSIGNMENT_DRAG_FAMILIES:
        raise ValueError(f"Unknown assignment drag family: {family}")
    if section == "pitching" and family != "rotation":
        raise ValueError("Pitching drag compilation supports only rotation.")
    if section != "pitching" and family == "rotation":
        raise ValueError("Rotation drag compilation requires the pitching section.")

    plan = build_ui_plan(manifest, section)
    entries = _family_entries(plan, family)
    if not entries:
        return []

    moves: list[dict[str, Any]] = []
    for entry in entries:
        cid, name, target_key = _entry_identity(entry, family)
        if cid not in sources:
            raise ValueError(f"Missing source coordinate for CID {cid} ({name}).")
        if target_key not in targets:
            raise ValueError(
                f"Missing {family} target coordinate for {target_key} ({name})."
            )
        moves.append(
            {
                "cid": cid,
                "name": name,
                "target": target_key,
                "from": list(sources[cid]),
                "to": list(targets[target_key]),
            }
        )
    return moves


def select_assignment_moves(
    moves: list[dict[str, Any]],
    *,
    first_only: bool = False,
    skip_first: int = 0,
) -> list[dict[str, Any]]:
    if first_only and skip_first:
        raise ValueError("--first-only and --skip-first cannot be combined.")
    if skip_first < 0:
        raise ValueError("--skip-first cannot be negative.")
    selected = moves[:1] if first_only else moves[skip_first:]
    if not selected:
        raise ValueError("No assignment moves remain for this selection.")
    return selected


def compile_journal_assignment_moves(
    actions: list[dict[str, Any]], section: str, family: str, *,
    sources: dict[str, tuple[int, int]], targets: dict[str, tuple[int, int]],
) -> list[dict[str, Any]]:
    if section not in ASSIGNMENT_DRAG_SECTIONS or family not in ASSIGNMENT_DRAG_FAMILIES:
        raise ValueError("Unknown journal assignment section or family")
    if (section == "pitching") != (family == "rotation"):
        raise ValueError("Pitching drag compilation supports only rotation")
    if not actions:
        raise ValueError("No assignment actions remain; inspect checkpoint status")
    moves = []
    prefix = f"{section}/{family}/"
    for action in actions:
        if action["operation"] != "set" or not action["target"].startswith(prefix):
            raise ValueError("Requested drag family is not the next journal action family")
        card = action["value"]["card"] if family == "depth" else action["value"]
        cid = card["cid"]
        target = action["target"][len(prefix):].replace("/", ":")
        if cid not in sources or target not in targets:
            raise ValueError(f"Missing source or target coordinate for CID {cid}, target {target}")
        moves.append({"action_id": action["id"], "cid": cid, "target": target,
                      "from": list(sources[cid]), "to": list(targets[target])})
    return moves


def _family_entries(plan: dict[str, Any], family: str) -> list[list[Any]]:
    key = "starter_sequence" if family == "starters" else family
    return plan[key]


def _entry_identity(entry: list[Any], family: str) -> tuple[str, str, str]:
    if family == "rotation":
        order, cid, name = entry
        return str(cid), str(name), str(order)
    if family == "starters":
        _batting_order, position, cid, name = entry
        return str(cid), str(name), str(position)
    if family == "depth":
        position, order, cid, name, _condition = entry
        return str(cid), str(name), f"{position}:{order}"
    order, cid, name = entry
    return str(cid), str(name), str(order)
