from __future__ import annotations

import argparse
import ctypes
import struct
import time
from ctypes import wintypes
from pathlib import Path


user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)


class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class INPUT_UNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("value",)
    _fields_ = [("type", wintypes.DWORD), ("value", INPUT_UNION)]


INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_VIRTUALDESK = 0x4000
SRCCOPY = 0x00CC0020
DIB_RGB_COLORS = 0
BI_RGB = 0
SW_RESTORE = 9
VK_MENU = 0x12
VK_TAB = 0x09
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
VK_CONTROL = 0x11
VK_A = 0x41


def _windows_matching(title_fragment: str) -> list[tuple[int, str]]:
    matches: list[tuple[int, str]] = []
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    @callback_type
    def callback(hwnd: int, _lparam: int) -> bool:
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, len(buffer))
        title = buffer.value
        if title_fragment.casefold() in title.casefold():
            matches.append((hwnd, title))
        return True

    if not user32.EnumWindows(callback, 0):
        raise ctypes.WinError(ctypes.get_last_error())
    return matches


def find_unique_window(title_fragment: str) -> tuple[int, str]:
    matches = _windows_matching(title_fragment)
    if len(matches) != 1:
        titles = ", ".join(repr(title) for _, title in matches) or "none"
        raise RuntimeError(
            f"Expected exactly one visible window matching {title_fragment!r}; "
            f"found {len(matches)}: {titles}"
        )
    return matches[0]


def client_geometry(hwnd: int) -> tuple[int, int, int, int]:
    rect = RECT()
    if not user32.GetClientRect(hwnd, ctypes.byref(rect)):
        raise ctypes.WinError(ctypes.get_last_error())
    origin = POINT(0, 0)
    if not user32.ClientToScreen(hwnd, ctypes.byref(origin)):
        raise ctypes.WinError(ctypes.get_last_error())
    return origin.x, origin.y, rect.right - rect.left, rect.bottom - rect.top


def capture_client(hwnd: int, output: Path) -> tuple[int, int]:
    _left, _top, width, height = client_geometry(hwnd)
    source_dc = user32.GetDC(hwnd)
    memory_dc = gdi32.CreateCompatibleDC(source_dc)
    bitmap = gdi32.CreateCompatibleBitmap(source_dc, width, height)
    previous = gdi32.SelectObject(memory_dc, bitmap)
    try:
        if not gdi32.BitBlt(memory_dc, 0, 0, width, height, source_dc, 0, 0, SRCCOPY):
            raise ctypes.WinError(ctypes.get_last_error())
        row_bytes = ((width * 3 + 3) // 4) * 4
        pixels = ctypes.create_string_buffer(row_bytes * height)
        bitmap_info = struct.pack(
            "<IiiHHIIiiII",
            40,
            width,
            height,
            1,
            24,
            BI_RGB,
            len(pixels),
            0,
            0,
            0,
            0,
        )
        info_buffer = ctypes.create_string_buffer(bitmap_info)
        if not gdi32.GetDIBits(
            memory_dc,
            bitmap,
            0,
            height,
            pixels,
            info_buffer,
            DIB_RGB_COLORS,
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        pixel_offset = 14 + len(bitmap_info)
        file_size = pixel_offset + len(pixels)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(
            struct.pack("<2sIHHI", b"BM", file_size, 0, 0, pixel_offset)
            + bitmap_info
            + pixels.raw
        )
    finally:
        gdi32.SelectObject(memory_dc, previous)
        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(memory_dc)
        user32.ReleaseDC(hwnd, source_dc)
    return width, height


def _absolute_point(screen_x: int, screen_y: int) -> tuple[int, int]:
    virtual_left = user32.GetSystemMetrics(76)
    virtual_top = user32.GetSystemMetrics(77)
    virtual_width = user32.GetSystemMetrics(78)
    virtual_height = user32.GetSystemMetrics(79)
    absolute_x = round((screen_x - virtual_left) * 65535 / max(1, virtual_width - 1))
    absolute_y = round((screen_y - virtual_top) * 65535 / max(1, virtual_height - 1))
    return absolute_x, absolute_y


def _send_mouse(screen_x: int, screen_y: int, flags: int) -> None:
    absolute_x, absolute_y = _absolute_point(screen_x, screen_y)
    event = INPUT(
        type=INPUT_MOUSE,
        mi=MOUSEINPUT(
            absolute_x,
            absolute_y,
            0,
            flags | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK,
            0,
            None,
        ),
    )
    if user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(INPUT)) != 1:
        raise ctypes.WinError(ctypes.get_last_error())


def _send_keyboard(*, virtual_key: int = 0, scan_code: int = 0, flags: int = 0) -> None:
    event = INPUT(
        type=INPUT_KEYBOARD,
        ki=KEYBDINPUT(virtual_key, scan_code, flags, 0, None),
    )
    if user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(INPUT)) != 1:
        raise ctypes.WinError(ctypes.get_last_error())


def _select_all() -> None:
    _send_keyboard(virtual_key=VK_CONTROL)
    time.sleep(0.08)
    _send_keyboard(virtual_key=VK_A)
    time.sleep(0.08)
    _send_keyboard(virtual_key=VK_A, flags=KEYEVENTF_KEYUP)
    time.sleep(0.08)
    _send_keyboard(virtual_key=VK_CONTROL, flags=KEYEVENTF_KEYUP)
    time.sleep(0.08)


def _send_unicode_text(text: str, char_delay_ms: int) -> None:
    utf16 = text.encode("utf-16-le")
    code_units = struct.unpack(f"<{len(utf16) // 2}H", utf16) if utf16 else ()
    for code_unit in code_units:
        _send_keyboard(scan_code=code_unit, flags=KEYEVENTF_UNICODE)
        _send_keyboard(
            scan_code=code_unit,
            flags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP,
        )
        time.sleep(char_delay_ms / 1000)


def _click_screen_point(screen_point: tuple[int, int], click_ms: int) -> None:
    _send_mouse(*screen_point, MOUSEEVENTF_MOVE)
    _send_mouse(*screen_point, MOUSEEVENTF_MOVE | MOUSEEVENTF_LEFTDOWN)
    time.sleep(click_ms / 1000)
    _send_mouse(*screen_point, MOUSEEVENTF_MOVE | MOUSEEVENTF_LEFTUP)


def _press_alt_tab() -> None:
    user32.keybd_event(VK_MENU, 0, 0, 0)
    user32.keybd_event(VK_TAB, 0, 0, 0)
    user32.keybd_event(VK_TAB, 0, KEYEVENTF_KEYUP, 0)
    user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)


def raise_window_for_input(hwnd: int, wait_foreground_seconds: float = 0) -> None:
    user32.ShowWindow(hwnd, SW_RESTORE)
    user32.keybd_event(VK_MENU, 0, 0, 0)
    user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)
    foreground = user32.GetForegroundWindow()
    current_thread = kernel32.GetCurrentThreadId()
    foreground_thread = user32.GetWindowThreadProcessId(foreground, None)
    target_thread = user32.GetWindowThreadProcessId(hwnd, None)
    attached_threads: list[int] = []
    try:
        for thread_id in {foreground_thread, target_thread} - {0, current_thread}:
            if user32.AttachThreadInput(current_thread, thread_id, True):
                attached_threads.append(thread_id)
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
        user32.SetFocus(hwnd)
        user32.SwitchToThisWindow(hwnd, True)
    finally:
        for thread_id in attached_threads:
            user32.AttachThreadInput(current_thread, thread_id, False)
    time.sleep(0.25)
    if user32.GetForegroundWindow() != hwnd:
        for _attempt in range(12):
            _press_alt_tab()
            time.sleep(0.2)
            if user32.GetForegroundWindow() == hwnd:
                break
    deadline = time.monotonic() + wait_foreground_seconds
    while user32.GetForegroundWindow() != hwnd and time.monotonic() < deadline:
        time.sleep(0.1)
    if user32.GetForegroundWindow() != hwnd:
        raise RuntimeError("Could not switch to the OOTP window")


def held_drag(
    hwnd: int,
    source: tuple[int, int],
    target: tuple[int, int],
    *,
    hold_ms: int = 350,
    move_ms: int = 900,
    settle_ms: int = 250,
    steps: int = 24,
    post_drop_ms: int = 450,
    wait_foreground_seconds: float = 0,
) -> None:
    held_drag_batch(
        hwnd,
        [(source, target)],
        hold_ms=hold_ms,
        move_ms=move_ms,
        settle_ms=settle_ms,
        steps=steps,
        post_drop_ms=post_drop_ms,
        wait_foreground_seconds=wait_foreground_seconds,
    )


def held_drag_batch(
    hwnd: int,
    moves: list[tuple[tuple[int, int], tuple[int, int]]],
    *,
    hold_ms: int = 350,
    move_ms: int = 900,
    settle_ms: int = 250,
    steps: int = 24,
    post_drop_ms: int = 450,
    wait_foreground_seconds: float = 0,
) -> None:
    if not moves:
        raise ValueError("At least one drag move is required")
    left, top, width, height = client_geometry(hwnd)
    for index, (source, target) in enumerate(moves, start=1):
        for label, (x, y) in (("source", source), ("target", target)):
            if not (0 <= x < width and 0 <= y < height):
                raise ValueError(
                    f"move {index} {label} coordinate {(x, y)} is outside "
                    f"client area {width}x{height}"
                )

    raise_window_for_input(hwnd, wait_foreground_seconds)
    for source, target in moves:
        source_screen = (left + source[0], top + source[1])
        target_screen = (left + target[0], top + target[1])
        mouse_is_down = False
        try:
            if user32.GetForegroundWindow() != hwnd:
                raise RuntimeError("OOTP lost foreground focus during drag batch")
            _send_mouse(*source_screen, MOUSEEVENTF_MOVE)
            time.sleep(0.15)
            _send_mouse(*source_screen, MOUSEEVENTF_MOVE | MOUSEEVENTF_LEFTDOWN)
            mouse_is_down = True
            time.sleep(0.15)
            if user32.GetForegroundWindow() != hwnd:
                raise RuntimeError("OOTP did not receive foreground focus on mouse-down")
            time.sleep(max(0, hold_ms - 150) / 1000)
            for step in range(1, steps + 1):
                fraction = step / steps
                x = round(
                    source_screen[0]
                    + (target_screen[0] - source_screen[0]) * fraction
                )
                y = round(
                    source_screen[1]
                    + (target_screen[1] - source_screen[1]) * fraction
                )
                _send_mouse(x, y, MOUSEEVENTF_MOVE | MOUSEEVENTF_LEFTDOWN)
                time.sleep(move_ms / steps / 1000)
            time.sleep(settle_ms / 1000)
            _send_mouse(*target_screen, MOUSEEVENTF_MOVE | MOUSEEVENTF_LEFTUP)
            mouse_is_down = False
            time.sleep(post_drop_ms / 1000)
        finally:
            if mouse_is_down:
                _send_mouse(*source_screen, MOUSEEVENTF_MOVE | MOUSEEVENTF_LEFTUP)


def click_batch(
    hwnd: int,
    points: list[tuple[int, int]],
    *,
    click_ms: int = 80,
    post_click_ms: int = 250,
    wait_foreground_seconds: float = 0,
) -> None:
    if not points:
        raise ValueError("At least one click point is required")
    left, top, width, height = client_geometry(hwnd)
    for index, (x, y) in enumerate(points, start=1):
        if not (0 <= x < width and 0 <= y < height):
            raise ValueError(
                f"click {index} coordinate {(x, y)} is outside "
                f"client area {width}x{height}"
            )

    raise_window_for_input(hwnd, wait_foreground_seconds)
    for x, y in points:
        if user32.GetForegroundWindow() != hwnd:
            raise RuntimeError("OOTP lost foreground focus during click batch")
        screen_point = (left + x, top + y)
        _click_screen_point(screen_point, click_ms)
        time.sleep(post_click_ms / 1000)


def type_text(
    hwnd: int,
    point: tuple[int, int],
    text: str,
    *,
    select_all: bool = True,
    click_ms: int = 80,
    char_delay_ms: int = 10,
    post_input_ms: int = 250,
    wait_foreground_seconds: float = 0,
) -> None:
    left, top, width, height = client_geometry(hwnd)
    x, y = point
    if not (0 <= x < width and 0 <= y < height):
        raise ValueError(
            f"text coordinate {(x, y)} is outside client area {width}x{height}"
        )
    raise_window_for_input(hwnd, wait_foreground_seconds)
    if user32.GetForegroundWindow() != hwnd:
        raise RuntimeError("OOTP lost foreground focus before text input")
    _click_screen_point((left + x, top + y), click_ms)
    time.sleep(0.15)
    if select_all:
        _select_all()
    _send_unicode_text(text, char_delay_ms)
    time.sleep(post_input_ms / 1000)


def filter_activate_batch(
    hwnd: int,
    field: tuple[int, int],
    activate: tuple[int, int],
    values: list[str],
    *,
    filter_wait_ms: int = 500,
    post_activate_ms: int = 300,
    char_delay_ms: int = 10,
    wait_foreground_seconds: float = 0,
    open_points: list[tuple[int, int]] | None = None,
    apply_point: tuple[int, int] | None = None,
) -> None:
    if not values:
        raise ValueError("At least one filter value is required")
    left, top, width, height = client_geometry(hwnd)
    for label, (x, y) in [("field", field), ("activate", activate)] + [
        ("open", point) for point in (open_points or [])
    ] + ([("apply", apply_point)] if apply_point is not None else []):
        if not (0 <= x < width and 0 <= y < height):
            raise ValueError(
                f"{label} coordinate {(x, y)} is outside client area {width}x{height}"
            )
    raise_window_for_input(hwnd, wait_foreground_seconds)
    field_screen = (left + field[0], top + field[1])
    activate_screen = (left + activate[0], top + activate[1])
    for value in values:
        if user32.GetForegroundWindow() != hwnd:
            raise RuntimeError("OOTP lost foreground focus during filter batch")
        for x, y in open_points or []:
            _click_screen_point((left + x, top + y), 80)
            time.sleep(0.3)
        _click_screen_point(field_screen, 80)
        time.sleep(0.15)
        _select_all()
        _send_unicode_text(value, char_delay_ms)
        time.sleep(0.15)
        if apply_point is not None:
            _click_screen_point((left + apply_point[0], top + apply_point[1]), 80)
        time.sleep(filter_wait_ms / 1000)
        _click_screen_point(activate_screen, 80)
        time.sleep(post_activate_ms / 1000)


def parse_point(value: str) -> tuple[int, int]:
    try:
        x_text, y_text = value.split(",", 1)
        return int(x_text), int(y_text)
    except (ValueError, TypeError) as exc:
        raise argparse.ArgumentTypeError("expected client coordinates as X,Y") from exc


def parse_move(value: str) -> tuple[tuple[int, int], tuple[int, int]]:
    try:
        source_text, target_text = value.split(":", 1)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "expected drag move as FROM_X,FROM_Y:TO_X,TO_Y"
        ) from exc
    return parse_point(source_text), parse_point(target_text)


def main() -> None:
    parser = argparse.ArgumentParser(description="OOTP held-drag diagnostic")
    parser.add_argument("--title", default="Out of the Park Baseball 27")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("inspect")
    capture_parser = subparsers.add_parser("capture")
    capture_parser.add_argument("output", type=Path)
    drag_parser = subparsers.add_parser("drag")
    drag_parser.add_argument("--from", dest="source", type=parse_point, required=True)
    drag_parser.add_argument("--to", dest="target", type=parse_point, required=True)
    drag_parser.add_argument("--hold-ms", type=int, default=350)
    drag_parser.add_argument("--move-ms", type=int, default=900)
    drag_parser.add_argument("--settle-ms", type=int, default=250)
    drag_parser.add_argument("--steps", type=int, default=24)
    drag_parser.add_argument("--post-drop-ms", type=int, default=450)
    drag_parser.add_argument("--wait-foreground-seconds", type=float, default=0)
    batch_parser = subparsers.add_parser("batch")
    batch_parser.add_argument(
        "--move",
        dest="moves",
        type=parse_move,
        action="append",
        required=True,
        help="Repeat for each FROM_X,FROM_Y:TO_X,TO_Y drag in the batch.",
    )
    batch_parser.add_argument("--hold-ms", type=int, default=350)
    batch_parser.add_argument("--move-ms", type=int, default=900)
    batch_parser.add_argument("--settle-ms", type=int, default=250)
    batch_parser.add_argument("--steps", type=int, default=24)
    batch_parser.add_argument("--post-drop-ms", type=int, default=450)
    batch_parser.add_argument("--wait-foreground-seconds", type=float, default=0)
    batch_parser.add_argument("--capture-after", type=Path)
    click_batch_parser = subparsers.add_parser("click-batch")
    click_batch_parser.add_argument(
        "--at",
        dest="points",
        type=parse_point,
        action="append",
        required=True,
        help="Repeat for each client-relative X,Y click in execution order.",
    )
    click_batch_parser.add_argument("--click-ms", type=int, default=80)
    click_batch_parser.add_argument("--post-click-ms", type=int, default=250)
    click_batch_parser.add_argument("--wait-foreground-seconds", type=float, default=0)
    click_batch_parser.add_argument("--capture-after", type=Path)
    type_parser = subparsers.add_parser("type-text")
    type_parser.add_argument("--at", type=parse_point, required=True)
    type_parser.add_argument("--text", required=True)
    type_parser.add_argument("--no-select-all", action="store_true")
    type_parser.add_argument("--click-ms", type=int, default=80)
    type_parser.add_argument("--char-delay-ms", type=int, default=10)
    type_parser.add_argument("--post-input-ms", type=int, default=250)
    type_parser.add_argument("--wait-foreground-seconds", type=float, default=0)
    type_parser.add_argument("--capture-after", type=Path)
    filter_parser = subparsers.add_parser("filter-batch")
    filter_parser.add_argument("--field", type=parse_point, required=True)
    filter_parser.add_argument("--activate", type=parse_point, required=True)
    filter_parser.add_argument("--open", dest="open_points", type=parse_point, action="append")
    filter_parser.add_argument("--apply", dest="apply_point", type=parse_point)
    filter_parser.add_argument("--value", action="append", required=True)
    filter_parser.add_argument("--filter-wait-ms", type=int, default=500)
    filter_parser.add_argument("--post-activate-ms", type=int, default=300)
    filter_parser.add_argument("--char-delay-ms", type=int, default=10)
    filter_parser.add_argument("--wait-foreground-seconds", type=float, default=0)
    filter_parser.add_argument("--capture-after", type=Path)
    args = parser.parse_args()

    hwnd, title = find_unique_window(args.title)
    geometry = client_geometry(hwnd)
    if args.command == "inspect":
        print(f"hwnd={hwnd} title={title!r} client={geometry}")
    elif args.command == "capture":
        size = capture_client(hwnd, args.output)
        print(f"captured={args.output.resolve()} size={size[0]}x{size[1]}")
    elif args.command == "drag":
        held_drag(
            hwnd,
            args.source,
            args.target,
            hold_ms=args.hold_ms,
            move_ms=args.move_ms,
            settle_ms=args.settle_ms,
            steps=args.steps,
            post_drop_ms=args.post_drop_ms,
            wait_foreground_seconds=args.wait_foreground_seconds,
        )
        print(
            f"dragged source={args.source} target={args.target} "
            f"hold_ms={args.hold_ms} move_ms={args.move_ms} "
            f"settle_ms={args.settle_ms} steps={args.steps}"
        )
    elif args.command == "batch":
        held_drag_batch(
            hwnd,
            args.moves,
            hold_ms=args.hold_ms,
            move_ms=args.move_ms,
            settle_ms=args.settle_ms,
            steps=args.steps,
            post_drop_ms=args.post_drop_ms,
            wait_foreground_seconds=args.wait_foreground_seconds,
        )
        capture_note = ""
        if args.capture_after:
            size = capture_client(hwnd, args.capture_after)
            capture_note = f" capture={args.capture_after.resolve()} size={size[0]}x{size[1]}"
        print(
            f"dragged_batch count={len(args.moves)} hold_ms={args.hold_ms} "
            f"move_ms={args.move_ms} settle_ms={args.settle_ms} "
            f"steps={args.steps} post_drop_ms={args.post_drop_ms}{capture_note}"
        )
    elif args.command == "click-batch":
        click_batch(
            hwnd,
            args.points,
            click_ms=args.click_ms,
            post_click_ms=args.post_click_ms,
            wait_foreground_seconds=args.wait_foreground_seconds,
        )
        capture_note = ""
        if args.capture_after:
            size = capture_client(hwnd, args.capture_after)
            capture_note = (
                f" capture={args.capture_after.resolve()} "
                f"size={size[0]}x{size[1]}"
            )
        print(
            f"clicked_batch count={len(args.points)} click_ms={args.click_ms} "
            f"post_click_ms={args.post_click_ms}{capture_note}"
        )
    elif args.command == "type-text":
        type_text(
            hwnd,
            args.at,
            args.text,
            select_all=not args.no_select_all,
            click_ms=args.click_ms,
            char_delay_ms=args.char_delay_ms,
            post_input_ms=args.post_input_ms,
            wait_foreground_seconds=args.wait_foreground_seconds,
        )
        capture_note = ""
        if args.capture_after:
            size = capture_client(hwnd, args.capture_after)
            capture_note = (
                f" capture={args.capture_after.resolve()} "
                f"size={size[0]}x{size[1]}"
            )
        print(f"typed_text length={len(args.text)}{capture_note}")
    else:
        filter_activate_batch(
            hwnd,
            args.field,
            args.activate,
            args.value,
            open_points=args.open_points,
            apply_point=args.apply_point,
            filter_wait_ms=args.filter_wait_ms,
            post_activate_ms=args.post_activate_ms,
            char_delay_ms=args.char_delay_ms,
            wait_foreground_seconds=args.wait_foreground_seconds,
        )
        capture_note = ""
        if args.capture_after:
            size = capture_client(hwnd, args.capture_after)
            capture_note = (
                f" capture={args.capture_after.resolve()} "
                f"size={size[0]}x{size[1]}"
            )
        print(f"filtered_batch count={len(args.value)}{capture_note}")


if __name__ == "__main__":
    main()
