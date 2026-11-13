"""Manifest-bound native transactions with local journaling between actions."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ootp_opt.automation import windows_drag
from ootp_opt.automation.execution import execute_action_batch, execution_status
from ootp_opt.automation.fast_executor import MAX_ACTIONS, execute_fast_batch, validate_fast_batch


def validate_execution_batch(plan: dict, manifest_id: str, actions: list[dict]) -> list[dict]:
    transactions = plan.get("transactions")
    if plan.get("schema_version") != 1 or not isinstance(transactions, list) or not transactions:
        raise ValueError("Execution batch requires schema_version 1 and nonempty transactions")
    if len(transactions) > len(actions):
        raise ValueError("Execution batch crosses the next action family boundary")
    expected = actions[:len(transactions)]
    if any(not isinstance(t, dict) for t in transactions) or (
        [t.get("action_id") for t in transactions] != [a["id"] for a in expected]
    ):
        raise ValueError("Execution batch transactions must match the next ordered action IDs")
    if any(a["operation"] in ("verify", "save") for a in expected):
        raise ValueError("Verification and save require the single-action path")
    native_plans = []
    for transaction, action in zip(transactions, expected, strict=True):
        native = {
            "schema_version": plan["schema_version"], "manifest_id": plan.get("manifest_id"),
            "section": plan.get("section"), "client_geometry": plan.get("client_geometry"),
            "actions": transaction.get("actions"),
        }
        validate_fast_batch(native, manifest_id=manifest_id, section=action["section"])
        native_plans.append(native)
    if sum(len(p["actions"]) for p in native_plans) > MAX_ACTIONS:
        raise ValueError(f"Execution batch supports at most {MAX_ACTIONS} native operations")
    return native_plans


def run_execution_batch(
    path: str | Path, manifest_id: str, plan: dict, *, title: str, capture_after: str | Path,
) -> dict[str, Any]:
    windows_drag.require_host_input()
    status = execution_status(path)
    if status["state"] != "ready":
        raise ValueError("Reconcile pending input before executing a native batch")
    native = validate_execution_batch(plan, manifest_id, status["next_batch"])
    hwnd, _ = windows_drag.find_unique_window(title)
    expected_geometry = tuple(plan["client_geometry"])
    if windows_drag.client_geometry(hwnd) != expected_geometry:
        raise RuntimeError("OOTP client geometry changed before the batch; no input was sent")
    transactions = plan["transactions"]
    by_id = {t["action_id"]: p for t, p in zip(transactions, native, strict=True)}
    final_id = transactions[-1]["action_id"]

    def execute(action):
        execute_fast_batch(
            hwnd, by_id[action["id"]],
            capture_after=capture_after if action["id"] == final_id else None,
        )

    result = execute_action_batch(path, list(by_id), execute)
    result["capture"] = str(Path(capture_after).resolve())
    return result
