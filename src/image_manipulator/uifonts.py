"""UI font selection for languages with non-Latin scripts.

Tk does not always fall back across font families, so a language catalog may
name preferred font families. When one is installed it is applied to the Tk
named fonts and used for the dialogs' explicit fonts.
"""

import contextlib
import tkinter as tk
import tkinter.font as tkfont
from collections.abc import Iterable

_DEFAULT_FAMILY = "Arial"

_NAMED_FONTS = (
    "TkDefaultFont",
    "TkTextFont",
    "TkMenuFont",
    "TkHeadingFont",
    "TkCaptionFont",
    "TkSmallCaptionFont",
    "TkIconFont",
    "TkTooltipFont",
)

_active_family = _DEFAULT_FAMILY


def ui_font(
    size: int, weight: str | None = None
) -> tuple[str, int] | tuple[str, int, str]:
    """Build a Tk font tuple in the active UI family."""
    if weight:
        return (_active_family, size, weight)
    return (_active_family, size)


def apply_ui_family(root, candidates: Iterable[str]) -> str | None:
    """Apply the first installed preferred family, if any.

    Args:
        root: Tk root used to enumerate installed families.
        candidates: Preferred font family names, in order of preference.

    Returns:
        The applied family, or None when the default family was kept.
    """
    global _active_family

    ordered = tuple(candidates)
    if not ordered:
        _active_family = _DEFAULT_FAMILY
        return None

    try:
        installed = {name.lower(): name for name in tkfont.families(root=root)}
    except tk.TclError:
        installed = {}

    for candidate in ordered:
        family = installed.get(candidate.lower())
        if not family:
            continue
        _active_family = family
        for name in _NAMED_FONTS:
            with contextlib.suppress(tk.TclError):
                root.tk.call("font", "configure", name, "-family", family)
        return family

    _active_family = _DEFAULT_FAMILY
    return None
