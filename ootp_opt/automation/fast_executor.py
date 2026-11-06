from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable

from ootp_opt.automation import windows_drag


FAST_BATCH_SCHEMA_VERSION = 1
FAST_BATCH_SECTIONS = ("sync", "pitching", "vs_rhp", "vs_lhp", "save")
MAX_ACTIONS = 50
MAX_BATCH_ITEMS = 30
MAX_WAIT_MS = 5_000
MAX_FOREGROUND_WAIT_SECONDS = 5


def load_fast_batch(path: str | Path) -> dict[str, Any]:
    with Path(path).open(encoding="utf-8") as handle:
        plan = json.load(handle)
    validate_fast_batch(plan)
    return plan


def validate_fast_batch(
    plan: dict[str, Any],
    *,
    manifest_id: str | None = None,
    section: str | None = None,
) -> None:
    if plan.get("schema_version") != FAST_BATCH_SCHEMA_VERSION:
        raise ValueError(
            f"Fast batch schema must be {FAST_BATCH_SCHEMA_VERSION}."
        )
    if not isinstance(plan.get("manifest_id"), str) or not plan["manifest_id"]:
        raise ValueError("Fast batch requires a manifest_id.")
    if manifest_id is not None and plan["manifest_id"] != manifest_id:
        raise ValueError("Fast batch manifest_id does not match the manifest.")

    observed_section = plan.get("section")
    if observed_section not in FAST_BATCH_SECTIONS:
        raise ValueError(f"Unknown fast batch section: {observed_section}")
    if section is not None and observed_section != section:
        raise ValueError("Fast batch section does not match the requested section.")

    geometry = plan.get("client_geometry")
    if not _is_int_list(geometry, 4):
        raise ValueError("client_geometry must be [left, top, width, height].")
    _, _, width, height = geometry
    if width <= 0 or height <= 0:
        raise ValueError("Fast batch client dimensions must be positive.")

    actions = plan.get("actions")
    if not isinstance(actions, list) or not actions:
        raise ValueError("Fast batch requires at least one action.")
    if len(actions) > MAX_ACTIONS:
        raise ValueError(f"Fast batch supports at most {MAX_ACTIONS} actions.")
    for index, action in enumerate(actions, start=1):
        _validate_action(action, width=width, height=height, index=index)


def execute_fast_batch(
    hwnd: int,
    plan: dict[str, Any],
    *,
    capture_after: str | Path | None = None,
    geometry_reader: Callable[[int], tuple[int, int, int, int]] | None = None,
) -> dict[str, Any]:
    validate_fast_batch(plan)
    expected_geometry = tuple(plan["client_geometry"])
    read_geometry = geometry_reader or windows_drag.client_geometry
    _require_geometry(hwnd, expected_geometry, read_geometry)

    completed = 0
    for action in plan["actions"]:
        _require_geometry(hwnd, expected_geometry, read_geometry)
        _execute_action(hwnd, action)
        completed += 1

    capture_path = None
    if capture_after is not None:
        _require_geometry(hwnd, expected_geometry, read_geometry)
        capture_path = str(Path(capture_after).resolve())
        windows_drag.capture_client(hwnd, Path(capture_after))
    return {
        "manifest_id": plan["manifest_id"],
        "section": plan["section"],
        "actions_completed": completed,
        "capture": capture_path,
    }


def _execute_action(hwnd: int, action: dict[str, Any]) -> None:
    operation = action["op"]
    if operation == "click_batch":
        windows_drag.click_batch(
            hwnd,
            [_point(value) for value in _point_items(action["points"])],
            click_ms=action.get("click_ms", 80),
            post_click_ms=action.get("post_click_ms", 250),
            wait_foreground_seconds=action.get("wait_foreground_seconds", 0),
        )
        return
    if operation == "drag_batch":
        windows_drag.held_drag_batch(
            hwnd,
            [
                (_point(move[0]), _point(move[1]))
                for move in _move_items(action["moves"])
            ],
            hold_ms=action.get("hold_ms", 400),
            move_ms=action.get("move_ms", 1_000),
            settle_ms=action.get("settle_ms", 300),
            steps=action.get("steps", 30),
            post_drop_ms=action.get("post_drop_ms", 450),
            wait_foreground_seconds=action.get("wait_foreground_seconds", 0),
        )
        return
    if operation == "type_text":
        windows_drag.type_text(
            hwnd,
            _point(action["at"]),
            action["text"],
            select_all=action.get("select_all", True),
            click_ms=action.get("click_ms", 80),
            char_delay_ms=action.get("char_delay_ms", 10),
            post_input_ms=action.get("post_input_ms", 250),
            wait_foreground_seconds=action.get("wait_foreground_seconds", 0),
        )
        return
    if operation == "filter_batch":
        windows_drag.filter_activate_batch(
            hwnd,
            _point(action["field"]),
            _point(action["activate"]),
            _value_items(action["values"]),
            open_points=[
                _point(value) for value in _point_items(action.get("open", []))
            ],
            apply_point=_optional_point(action.get("apply")),
            confirm_point=_optional_point(action.get("confirm")),
            filter_wait_ms=action.get("filter_wait_ms", 500),
            post_activate_ms=action.get("post_activate_ms", 300),
            confirm_wait_ms=action.get("confirm_wait_ms", 300),
            post_confirm_ms=action.get("post_confirm_ms", 500),
            char_delay_ms=action.get("char_delay_ms", 10),
            wait_foreground_seconds=action.get("wait_foreground_seconds", 0),
        )
        return
    time.sleep(action["ms"] / 1_000)


def _validate_action(
    action: object,
    *,
    width: int,
    height: int,
    index: int,
) -> None:
    if not isinstance(action, dict):
        raise ValueError(f"Fast batch action {index} must be an object.")
    operation = action.get("op")
    if operation == "click_batch":
        _validate_points(
            _point_items(action.get("points")), width, height, index, "points"
        )
        _validate_milliseconds(action, index, "click_ms", 80)
        _validate_milliseconds(action, index, "post_click_ms", 250)
    elif operation == "drag_batch":
        moves = _move_items(action.get("moves"))
        if not isinstance(moves, list) or not moves or len(moves) > MAX_BATCH_ITEMS:
            raise ValueError(
                f"Fast batch action {index} moves must contain 1-{MAX_BATCH_ITEMS} items."
            )
        for move_index, move in enumerate(moves, start=1):
            if not isinstance(move, list) or len(move) != 2:
                raise ValueError(
                    f"Fast batch action {index} move {move_index} must be [from, to]."
                )
            _validate_point(move[0], width, height, index, f"move {move_index} from")
            _validate_point(move[1], width, height, index, f"move {move_index} to")
        for name, default in (
            ("hold_ms", 400),
            ("move_ms", 1_000),
            ("settle_ms", 300),
            ("post_drop_ms", 450),
        ):
            _validate_milliseconds(action, index, name, default)
        steps = action.get("steps", 30)
        if not isinstance(steps, int) or isinstance(steps, bool) or not 1 <= steps <= 100:
            raise ValueError(f"Fast batch action {index} steps must be 1-100.")
    elif operation == "type_text":
        _validate_point(action.get("at"), width, height, index, "at")
        text = action.get("text")
        if not isinstance(text, str) or not text or len(text) > 200:
            raise ValueError(f"Fast batch action {index} requires 1-200 text characters.")
        for name, default in (
            ("click_ms", 80),
            ("char_delay_ms", 10),
            ("post_input_ms", 250),
        ):
            _validate_milliseconds(action, index, name, default)
    elif operation == "filter_batch":
        _validate_point(action.get("field"), width, height, index, "field")
        _validate_point(action.get("activate"), width, height, index, "activate")
        for label in ("apply", "confirm"):
            if action.get(label) is not None:
                _validate_point(action[label], width, height, index, label)
        if action.get("open"):
            _validate_points(
                _point_items(action["open"]), width, height, index, "open"
            )
        values = _value_items(action.get("values"))
        if not isinstance(values, list) or not values or len(values) > MAX_BATCH_ITEMS:
            raise ValueError(
                f"Fast batch action {index} values must contain 1-{MAX_BATCH_ITEMS} items."
            )
        if any(not isinstance(value, str) or not value or len(value) > 50 for value in values):
            raise ValueError(f"Fast batch action {index} has an invalid filter value.")
        for name, default in (
            ("filter_wait_ms", 500),
            ("post_activate_ms", 300),
            ("confirm_wait_ms", 300),
            ("post_confirm_ms", 500),
            ("char_delay_ms", 10),
        ):
            _validate_milliseconds(action, index, name, default)
    elif operation == "wait":
        milliseconds = action.get("ms")
        if not isinstance(milliseconds, int) or not 0 <= milliseconds <= MAX_WAIT_MS:
            raise ValueError(
                f"Fast batch action {index} wait must be 0-{MAX_WAIT_MS} ms."
            )
    else:
        raise ValueError(f"Fast batch action {index} has unknown op: {operation}")
    foreground_wait = action.get("wait_foreground_seconds", 0)
    if (
        not isinstance(foreground_wait, (int, float))
        or isinstance(foreground_wait, bool)
        or not 0 <= foreground_wait <= MAX_FOREGROUND_WAIT_SECONDS
    ):
        raise ValueError(
            f"Fast batch action {index} wait_foreground_seconds must be "
            f"0-{MAX_FOREGROUND_WAIT_SECONDS}."
        )


def _validate_points(
    values: object,
    width: int,
    height: int,
    action_index: int,
    label: str,
) -> None:
    if not isinstance(values, list) or not values or len(values) > MAX_BATCH_ITEMS:
        raise ValueError(
            f"Fast batch action {action_index} {label} must contain "
            f"1-{MAX_BATCH_ITEMS} points."
        )
    for point_index, value in enumerate(values, start=1):
        _validate_point(
            value,
            width,
            height,
            action_index,
            f"{label} {point_index}",
        )


def _validate_point(
    value: object,
    width: int,
    height: int,
    action_index: int,
    label: str,
) -> None:
    if not _is_int_list(value, 2):
        raise ValueError(
            f"Fast batch action {action_index} {label} must be [x, y]."
        )
    x, y = value
    if not (0 <= x < width and 0 <= y < height):
        raise ValueError(
            f"Fast batch action {action_index} {label} {value} is outside "
            f"the {width}x{height} client area."
        )


def _require_geometry(
    hwnd: int,
    expected: tuple[int, int, int, int],
    reader: Callable[[int], tuple[int, int, int, int]],
) -> None:
    observed = reader(hwnd)
    if observed != expected:
        raise RuntimeError(
            f"OOTP client geometry changed: expected {expected}, observed {observed}."
        )


def _validate_milliseconds(
    action: dict[str, Any],
    action_index: int,
    name: str,
    default: int,
) -> None:
    value = action.get(name, default)
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or not 0 <= value <= MAX_WAIT_MS
    ):
        raise ValueError(
            f"Fast batch action {action_index} {name} must be 0-{MAX_WAIT_MS}."
        )


def _point(value: list[int]) -> tuple[int, int]:
    return value[0], value[1]


def _optional_point(value: list[int] | None) -> tuple[int, int] | None:
    return _point(value) if value is not None else None


def _point_items(value: object) -> object:
    if _is_int_list(value, 2):
        return [value]
    return value


def _move_items(value: object) -> object:
    if (
        isinstance(value, list)
        and len(value) == 2
        and _is_int_list(value[0], 2)
        and _is_int_list(value[1], 2)
    ):
        return [value]
    return value


def _value_items(value: object) -> object:
    if isinstance(value, str):
        return [value]
    return value


def _is_int_list(value: object, length: int) -> bool:
    return (
        isinstance(value, list)
        and len(value) == length
        and all(isinstance(item, int) and not isinstance(item, bool) for item in value)
    )
