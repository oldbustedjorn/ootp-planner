from __future__ import annotations

from pathlib import Path

import pytest

from ootp_opt.automation import fast_executor


def sample_plan() -> dict:
    return {
        "schema_version": 1,
        "manifest_id": "manifest-123",
        "section": "vs_rhp",
        "client_geometry": [10, 20, 1200, 900],
        "actions": [
            {
                "op": "drag_batch",
                "moves": [
                    [[100, 200], [600, 300]],
                    [[100, 240], [600, 340]],
                ],
            },
            {
                "op": "click_batch",
                "points": [[700, 300], [720, 360]],
            },
            {
                "op": "type_text",
                "at": [300, 100],
                "text": "87312",
            },
            {
                "op": "filter_batch",
                "field": [300, 100],
                "activate": [900, 300],
                "confirm": [650, 500],
                "values": ["87312", "87350"],
            },
            {"op": "wait", "ms": 800},
        ],
    }


def test_validate_fast_batch_is_manifest_and_section_bound() -> None:
    plan = sample_plan()

    fast_executor.validate_fast_batch(
        plan,
        manifest_id="manifest-123",
        section="vs_rhp",
    )

    with pytest.raises(ValueError, match="manifest_id does not match"):
        fast_executor.validate_fast_batch(plan, manifest_id="other")
    with pytest.raises(ValueError, match="section does not match"):
        fast_executor.validate_fast_batch(plan, section="vs_lhp")


def test_validate_fast_batch_rejects_unsafe_coordinates() -> None:
    plan = sample_plan()
    plan["actions"][0]["moves"][0][1] = [1200, 300]

    with pytest.raises(ValueError, match="outside the 1200x900 client area"):
        fast_executor.validate_fast_batch(plan)


def test_validate_fast_batch_rejects_unbounded_waits() -> None:
    plan = sample_plan()
    plan["actions"][0]["post_drop_ms"] = 50_000

    with pytest.raises(ValueError, match="post_drop_ms must be 0-5000"):
        fast_executor.validate_fast_batch(plan)


def test_singleton_batches_accept_powershell_flattened_shapes() -> None:
    plan = sample_plan()
    plan["actions"] = [
        {
            "op": "drag_batch",
            "moves": [[150, 467], [155, 800]],
        },
        {
            "op": "click_batch",
            "points": [700, 300],
        },
        {
            "op": "filter_batch",
            "field": [300, 100],
            "activate": [900, 300],
            "open": [402, 250],
            "values": "87312",
        },
    ]

    fast_executor.validate_fast_batch(plan)


def test_execute_fast_batch_runs_all_actions_and_captures(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    actions: list[tuple] = []
    monkeypatch.setattr(
        fast_executor.windows_drag,
        "held_drag_batch",
        lambda hwnd, moves, **kwargs: actions.append(("drag", hwnd, moves, kwargs)),
    )
    monkeypatch.setattr(
        fast_executor.windows_drag,
        "click_batch",
        lambda hwnd, points, **kwargs: actions.append(
            ("click", hwnd, points, kwargs)
        ),
    )
    monkeypatch.setattr(
        fast_executor.windows_drag,
        "type_text",
        lambda hwnd, point, text, **kwargs: actions.append(
            ("type", hwnd, point, text, kwargs)
        ),
    )
    monkeypatch.setattr(
        fast_executor.windows_drag,
        "filter_activate_batch",
        lambda hwnd, field, activate, values, **kwargs: actions.append(
            ("filter", hwnd, field, activate, values, kwargs)
        ),
    )
    monkeypatch.setattr(
        fast_executor.windows_drag,
        "capture_client",
        lambda hwnd, path: actions.append(("capture", hwnd, path)) or (1200, 900),
    )
    monkeypatch.setattr(
        fast_executor.time,
        "sleep",
        lambda seconds: actions.append(("wait", seconds)),
    )

    capture = tmp_path / "verified.bmp"
    result = fast_executor.execute_fast_batch(
        321,
        sample_plan(),
        capture_after=capture,
        geometry_reader=lambda _hwnd: (10, 20, 1200, 900),
    )

    assert [action[0] for action in actions] == [
        "drag",
        "click",
        "type",
        "filter",
        "wait",
        "capture",
    ]
    assert result == {
        "manifest_id": "manifest-123",
        "section": "vs_rhp",
        "actions_completed": 5,
        "capture": str(capture.resolve()),
    }


def test_execute_fast_batch_stops_when_geometry_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0
    executed: list[str] = []

    def geometry(_hwnd: int) -> tuple[int, int, int, int]:
        nonlocal calls
        calls += 1
        return (10, 20, 1200, 900) if calls < 3 else (11, 20, 1200, 900)

    monkeypatch.setattr(
        fast_executor.windows_drag,
        "held_drag_batch",
        lambda *_args, **_kwargs: executed.append("drag"),
    )
    plan = sample_plan()
    plan["actions"] = plan["actions"][:2]

    with pytest.raises(RuntimeError, match="OOTP client geometry changed"):
        fast_executor.execute_fast_batch(321, plan, geometry_reader=geometry)

    assert executed == ["drag"]
