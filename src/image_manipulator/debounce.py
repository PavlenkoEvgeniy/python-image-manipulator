"""A tiny Tk ``after`` debouncer shared by preview and autosave."""

import contextlib
import tkinter as tk
from collections.abc import Callable


class Debouncer:
    """Run a callback once after a quiet period."""

    def __init__(
        self,
        root: tk.Misc,
        delay_ms: int,
        callback: Callable[[], None],
    ) -> None:
        self.root = root
        self.delay_ms = delay_ms
        self.callback = callback
        self._after_id: str | None = None

    @property
    def pending(self) -> bool:
        return self._after_id is not None

    def schedule(self) -> None:
        self.cancel()
        self._after_id = self.root.after(self.delay_ms, self._fire)

    def cancel(self) -> None:
        if self._after_id is None:
            return
        with contextlib.suppress(Exception):
            self.root.after_cancel(self._after_id)
        self._after_id = None

    def _fire(self) -> None:
        self._after_id = None
        self.callback()
