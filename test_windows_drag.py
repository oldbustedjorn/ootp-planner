from __future__ import annotations

import argparse

import pytest

from ootp_opt.automation import windows_drag
from ootp_opt.automation.windows_drag import click_batch, parse_move, parse_point


def test_parse_point_and_move() -> None:
    assert parse_point("164,489") == (164, 489)
    assert parse_move("164,489:541,1279") == ((164, 489), (541, 1279))


@pytest.mark.parametrize("value", ["164", "a,489", "164,489,541"])
def test_parse_point_rejects_invalid_coordinates(value: str) -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        parse_point(value)


def test_parse_move_requires_source_and_target() -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        parse_move("164,489")


def test_click_batch_requires_at_least_one_point() -> None:
    with pytest.raises(ValueError, match="At least one click point"):
        click_batch(123, [])


def test_click_batch_uses_client_relative_points(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: list[tuple[int, int, int]] = []
    monkeypatch.setattr(windows_drag, "client_geometry", lambda _hwnd: (10, 20, 800, 600))
    monkeypatch.setattr(
        windows_drag, "raise_window_for_input", lambda _hwnd, _wait: None
    )
    monkeypatch.setattr(windows_drag.user32, "GetForegroundWindow", lambda: 123)
    monkeypatch.setattr(
        windows_drag, "_send_mouse", lambda x, y, flags: sent.append((x, y, flags))
    )
    monkeypatch.setattr(windows_drag.time, "sleep", lambda _seconds: None)

    click_batch(123, [(100, 200), (300, 400)])

    assert sent == [
        (110, 220, windows_drag.MOUSEEVENTF_MOVE),
        (110, 220, windows_drag.MOUSEEVENTF_MOVE | windows_drag.MOUSEEVENTF_LEFTDOWN),
        (110, 220, windows_drag.MOUSEEVENTF_MOVE | windows_drag.MOUSEEVENTF_LEFTUP),
        (310, 420, windows_drag.MOUSEEVENTF_MOVE),
        (310, 420, windows_drag.MOUSEEVENTF_MOVE | windows_drag.MOUSEEVENTF_LEFTDOWN),
        (310, 420, windows_drag.MOUSEEVENTF_MOVE | windows_drag.MOUSEEVENTF_LEFTUP),
    ]


def test_type_text_focuses_selects_and_types(monkeypatch: pytest.MonkeyPatch) -> None:
    actions: list[object] = []
    monkeypatch.setattr(windows_drag, "client_geometry", lambda _hwnd: (10, 20, 800, 600))
    monkeypatch.setattr(
        windows_drag, "raise_window_for_input", lambda _hwnd, _wait: None
    )
    monkeypatch.setattr(windows_drag.user32, "GetForegroundWindow", lambda: 123)
    monkeypatch.setattr(
        windows_drag,
        "_click_screen_point",
        lambda point, click_ms: actions.append(("click", point, click_ms)),
    )
    monkeypatch.setattr(windows_drag, "_select_all", lambda: actions.append("select"))
    monkeypatch.setattr(
        windows_drag,
        "_send_unicode_text",
        lambda text, delay: actions.append(("text", text, delay)),
    )
    monkeypatch.setattr(windows_drag.time, "sleep", lambda _seconds: None)

    windows_drag.type_text(123, (100, 200), "86461")

    assert actions == [
        ("click", (110, 220), 80),
        "select",
        ("text", "86461", 10),
    ]


def test_filter_activate_batch_requires_values() -> None:
    with pytest.raises(ValueError, match="At least one filter value"):
        windows_drag.filter_activate_batch(123, (1, 1), (2, 2), [])


def test_filter_activate_batch_focuses_window_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actions: list[object] = []
    monkeypatch.setattr(windows_drag, "client_geometry", lambda _hwnd: (10, 20, 800, 600))
    monkeypatch.setattr(
        windows_drag,
        "raise_window_for_input",
        lambda _hwnd, _wait: actions.append("focus"),
    )
    monkeypatch.setattr(windows_drag.user32, "GetForegroundWindow", lambda: 123)
    monkeypatch.setattr(
        windows_drag,
        "_click_screen_point",
        lambda point, _click_ms: actions.append(("click", point)),
    )
    monkeypatch.setattr(windows_drag, "_select_all", lambda: actions.append("select"))
    monkeypatch.setattr(
        windows_drag,
        "_send_unicode_text",
        lambda text, _delay: actions.append(("text", text)),
    )
    monkeypatch.setattr(windows_drag.time, "sleep", lambda _seconds: None)

    windows_drag.filter_activate_batch(
        123,
        (100, 200),
        (300, 400),
        ["86461", "85088"],
    )

    assert actions == [
        "focus",
        ("click", (110, 220)),
        "select",
        ("text", "86461"),
        ("click", (310, 420)),
        ("click", (110, 220)),
        "select",
        ("text", "85088"),
        ("click", (310, 420)),
    ]
