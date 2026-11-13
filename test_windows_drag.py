from __future__ import annotations

import argparse
import sys
from pathlib import Path

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


def test_held_drag_presses_once_moves_with_button_held_then_releases(monkeypatch):
    events = []
    monkeypatch.setattr(windows_drag, "client_geometry", lambda _: (696, 57, 1848, 1061))
    monkeypatch.setattr(windows_drag, "raise_window_for_input", lambda *_: None)
    monkeypatch.setattr(windows_drag.user32, "GetForegroundWindow", lambda: 123)
    monkeypatch.setattr(windows_drag.time, "sleep", lambda _: None)
    monkeypatch.setattr(windows_drag, "_send_mouse", lambda x, y, flags: events.append((x, y, flags)))
    windows_drag.held_drag_batch(123, [((160, 363), (150, 800))], steps=30)
    down = [i for i, (_, _, flags) in enumerate(events) if flags & windows_drag.MOUSEEVENTF_LEFTDOWN]
    up = [i for i, (_, _, flags) in enumerate(events) if flags & windows_drag.MOUSEEVENTF_LEFTUP]
    assert down == [1]
    assert up == [len(events) - 1]
    assert events[1][:2] == (856, 420)
    assert events[-1][:2] == (846, 857)
    assert len(events[2:-1]) == 30
    assert all(flags == windows_drag.MOUSEEVENTF_MOVE for _, _, flags in events[2:-1])


@pytest.mark.parametrize("failure", ["move", "focus"])
def test_interrupted_held_drag_releases_button_and_stops_batch(monkeypatch, failure):
    events = []
    monkeypatch.setattr(windows_drag, "client_geometry", lambda _: (0, 0, 800, 600))
    monkeypatch.setattr(windows_drag, "raise_window_for_input", lambda *_: None)
    monkeypatch.setattr(windows_drag.time, "sleep", lambda _: None)
    def foreground():
        return 0 if failure == "focus" and any(flags & windows_drag.MOUSEEVENTF_LEFTDOWN
                                                for _, _, flags in events) else 123
    def send(x, y, flags):
        if failure == "move" and len(events) == 2 and flags == windows_drag.MOUSEEVENTF_MOVE:
            raise RuntimeError("interrupted movement")
        events.append((x, y, flags))
    monkeypatch.setattr(windows_drag.user32, "GetForegroundWindow", foreground)
    monkeypatch.setattr(windows_drag, "_send_mouse", send)
    with pytest.raises(RuntimeError):
        windows_drag.held_drag_batch(123, [((100, 100), (500, 500)), ((200, 200), (600, 500))])
    assert sum(bool(flags & windows_drag.MOUSEEVENTF_LEFTDOWN) for _, _, flags in events) == 1
    assert events[-1][2] & windows_drag.MOUSEEVENTF_LEFTUP


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


def test_filter_activate_batch_confirms_each_activation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actions: list[object] = []
    monkeypatch.setattr(windows_drag, "client_geometry", lambda _hwnd: (10, 20, 800, 600))
    monkeypatch.setattr(
        windows_drag, "raise_window_for_input", lambda _hwnd, _wait: None
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
        ["87160", "84808"],
        confirm_point=(500, 500),
    )

    assert actions == [
        ("click", (110, 220)),
        "select",
        ("text", "87160"),
        ("click", (310, 420)),
        ("click", (510, 520)),
        ("click", (110, 220)),
        "select",
        ("text", "84808"),
        ("click", (310, 420)),
        ("click", (510, 520)),
    ]


def test_drag_cli_supports_capture_after(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    capture_path = tmp_path / "drag.bmp"
    actions: list[object] = []
    monkeypatch.setattr(sys, "argv", [
        "windows_drag.py",
        "drag",
        "--from", "10,20",
        "--to", "30,40",
        "--capture-after", str(capture_path),
    ])
    monkeypatch.setattr(windows_drag, "find_unique_window", lambda _title: (123, "OOTP"))
    monkeypatch.setattr(windows_drag, "client_geometry", lambda _hwnd: (0, 0, 800, 600))
    monkeypatch.setattr(
        windows_drag,
        "held_drag",
        lambda hwnd, source, target, **kwargs: actions.append(
            ("drag", hwnd, source, target, kwargs)
        ),
    )
    monkeypatch.setattr(
        windows_drag,
        "capture_client",
        lambda hwnd, path: actions.append(("capture", hwnd, path)) or (800, 600),
    )

    windows_drag.main()

    assert actions[0][0:4] == ("drag", 123, (10, 20), (30, 40))
    assert actions[1] == ("capture", 123, capture_path)
    assert f"captured={capture_path.resolve()}" in capsys.readouterr().out


@pytest.mark.parametrize("point,geometry,space,origin,expected", [
    ((1100, 360), (0, 31, 1850, 1062), "screen", None, (1100, 329)),
    ((1100, 360), (300, 231, 1850, 1062), "window", (300, 200), (1100, 329)),
    ((1100, 329), (300, 231, 1850, 1062), "client", None, (1100, 329)),
    ((-800, 360), (-1920, 31, 1850, 1062), "screen", None, (1120, 329)),
])
def test_input_coordinates_account_for_title_bar_and_window_origin(
    point, geometry, space, origin, expected,
):
    assert windows_drag.client_point(point, geometry, space, window_origin=origin) == expected


def test_window_title_bar_is_rejected_before_native_input():
    with pytest.raises(ValueError, match="outside client area"):
        windows_drag.client_point((100, 15), (0, 31, 1850, 1062), "window", window_origin=(0, 0))


def test_filter_batch_converts_every_point_before_input():
    args = argparse.Namespace(
        coordinate_space="screen", field=(1100, 360), activate=(1700, 500),
        open_points=[(300, 280), (260, 314)], apply_point=(1142, 844),
        confirm_point=(970, 620),
    )
    windows_drag.normalize_input_coordinates(args, 123, (0, 31, 1850, 1062))
    assert args.field == (1100, 329)
    assert args.activate == (1700, 469)
    assert args.open_points == [(300, 249), (260, 283)]
    assert args.apply_point == (1142, 813)
    assert args.confirm_point == (970, 589)


def test_window_points_use_visible_frame_without_invisible_resize_border(monkeypatch):
    def bounds(hwnd, attribute, rect, size):
        assert attribute == windows_drag.DWMWA_EXTENDED_FRAME_BOUNDS
        rect._obj.left = 679
        rect._obj.top = 22
        return 0
    monkeypatch.setattr(windows_drag.dwmapi, "DwmGetWindowAttribute", bounds)
    args = argparse.Namespace(coordinate_space="window", at=(1100, 360))
    windows_drag.normalize_input_coordinates(args, 123, (680, 53, 1848, 1061))
    assert args.at == (1099, 329)


def test_type_text_cli_reports_converted_point_and_input_receipt(monkeypatch, capsys):
    actions = []
    monkeypatch.setattr(sys, "argv", ["windows_drag.py", "type-text", "--at", "1100,360",
        "--coordinate-space", "screen", "--text", "87326"])
    monkeypatch.setattr(windows_drag, "find_unique_window", lambda _: (123, "OOTP"))
    monkeypatch.setattr(windows_drag, "client_geometry", lambda _: (0, 31, 1850, 1062))
    monkeypatch.setattr(windows_drag, "type_text", lambda hwnd, point, text, **kw:
                        actions.append((hwnd, point, text)))
    windows_drag.main()
    assert actions == [(123, (1100, 329), "87326")]
    output = capsys.readouterr().out
    assert "client_at=(1100, 329)" in output
    assert "field_verification=required" in output


def test_app_container_input_is_rejected_before_window_activation(monkeypatch):
    monkeypatch.setattr(windows_drag, "is_app_container", lambda: True)
    def unexpected(*args):
        pytest.fail("Sandboxed input must stop before activating the host window")
    monkeypatch.setattr(windows_drag.user32, "ShowWindow", unexpected)
    with pytest.raises(RuntimeError, match="host context"):
        windows_drag.raise_window_for_input(123)


def test_host_input_passes_environment_preflight(monkeypatch):
    monkeypatch.setattr(windows_drag, "is_app_container", lambda: False)
    windows_drag.require_host_input()


@pytest.mark.parametrize("query_succeeds", [True, False])
def test_app_container_token_is_closed_even_if_query_fails(monkeypatch, query_succeeds):
    closed = []
    def open_token(process, access, token):
        token._obj.value = 42
        return True
    def query(token, info, value, size, returned):
        assert info == windows_drag.TOKEN_IS_APP_CONTAINER
        value._obj.value = 1
        return query_succeeds
    monkeypatch.setattr(windows_drag.advapi32, "OpenProcessToken", open_token)
    monkeypatch.setattr(windows_drag.advapi32, "GetTokenInformation", query)
    monkeypatch.setattr(windows_drag.kernel32, "CloseHandle", lambda token: closed.append(token.value))
    if query_succeeds:
        assert windows_drag.is_app_container()
    else:
        with pytest.raises(OSError):
            windows_drag.is_app_container()
    assert closed == [42]


def test_context_rejection_has_explicit_no_input_retry_receipt(capsys):
    import json
    def rejected():
        raise windows_drag.NativeInputContextError()
    with pytest.raises(SystemExit) as exited:
        windows_drag.run_cli(rejected)
    assert exited.value.code == 75
    output = capsys.readouterr()
    assert output.out == ""
    receipt = json.loads(output.err)
    assert receipt["input_sent"] is False
    assert receipt["retryable_in_host"] is True
    assert receipt["sandbox_permissions"] == "require_escalated"


def test_cli_does_not_relabel_possible_input_failure_as_safe_to_retry():
    def failed_after_input():
        raise RuntimeError("possible partial input")
    with pytest.raises(RuntimeError, match="possible partial input"):
        windows_drag.run_cli(failed_after_input)
