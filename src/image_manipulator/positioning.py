"""Window positioning helpers shared by the main window and dialogs."""

import tkinter as tk
from typing import Optional


def centered_origin(
    container_size: tuple[int, int], window_size: tuple[int, int]
) -> tuple[int, int]:
    """Compute the origin that centers a window inside a container."""
    x = (container_size[0] - window_size[0]) // 2
    y = (container_size[1] - window_size[1]) // 2
    return x, y


def choose_monitor(
    monitors: list[tuple[int, int, int, int]], pointer: tuple[int, int]
) -> Optional[tuple[int, int, int, int]]:
    """Pick the monitor rectangle that contains the given point."""
    px, py = pointer
    for x, y, width, height in monitors:
        if x <= px < x + width and y <= py < y + height:
            return x, y, width, height
    return None


def detect_monitors() -> list[tuple[int, int, int, int]]:
    """Best-effort monitor detection.

    Returns:
        Monitor rectangles as (x, y, width, height); empty when detection is
        unavailable (screeninfo missing, native Wayland, etc.).
    """
    try:
        from screeninfo import get_monitors

        return [(m.x, m.y, m.width, m.height) for m in get_monitors()]
    except Exception:
        return []


def center_on_screen(
    window: tk.Wm,
    width: int,
    height: int,
    monitors: Optional[list[tuple[int, int, int, int]]] = None,
) -> None:
    """Position and size a window centered inside the monitor with the pointer.

    On multi-monitor setups Tk reports one combined virtual screen, so the
    window is centered on the monitor that currently holds the mouse pointer.
    When detection is unavailable, it falls back to the whole virtual screen.
    """
    if monitors is None:
        monitors = detect_monitors()
    monitor = choose_monitor(
        monitors, (window.winfo_pointerx(), window.winfo_pointery())
    )

    if monitor is not None:
        mx, my, mw, mh = monitor
        dx, dy = centered_origin((mw, mh), (width, height))
        x = mx + max(0, min(dx, max(0, mw - width)))
        y = my + max(0, min(dy, max(0, mh - height)))
    else:
        screen_size = (window.winfo_screenwidth(), window.winfo_screenheight())
        x, y = centered_origin(screen_size, (width, height))
        x = max(0, x)
        y = max(0, y)

    window.geometry(f"{width}x{height}+{x}+{y}")
    _align_client(window, x, y, width, height)


def center_over_parent(
    *,
    window: tk.Wm,
    parent: tk.Wm,
    width: Optional[int] = None,
    height: Optional[int] = None,
) -> None:
    """Position a window centered over its parent window.

    Arguments are keyword-only on purpose: swapping the window and its
    parent moves the main window instead of the dialog.
    """
    window.update_idletasks()
    w = width if width is not None else window.winfo_reqwidth()
    h = height if height is not None else window.winfo_reqheight()
    x, y = centered_origin((parent.winfo_width(), parent.winfo_height()), (w, h))
    x += parent.winfo_rootx()
    y += parent.winfo_rooty()
    window.geometry(f"{w}x{h}+{x}+{y}")
    _align_client(window, x, y, w, h)


def _align_client(window: tk.Wm, x: int, y: int, width: int, height: int) -> None:
    """Correct for window managers that position the frame, not the client."""
    window.update()
    if not window.winfo_ismapped():
        return
    error_x = x - window.winfo_rootx()
    error_y = y - window.winfo_rooty()
    if error_x or error_y:
        window.geometry(f"{width}x{height}+{x + error_x}+{y + error_y}")
        window.update()
