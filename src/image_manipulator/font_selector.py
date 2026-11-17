"""Lightweight font-family selector built from classic Tk widgets."""

import tkinter as tk
from collections.abc import Callable
from typing import Literal

from .i18n import tr
from .positioning import center_over_parent


def choose_font_family(
    parent: tk.Tk | tk.Toplevel, current: str, families: list[str]
) -> str | None:
    """Show a modal family list and return the selected family."""
    window = tk.Toplevel(parent)
    window.title(tr("text.font"))
    window.transient(parent)
    window.resizable(False, False)

    frame = tk.Frame(window, padx=10, pady=10)
    frame.pack(fill=tk.BOTH, expand=True)
    height = min(14, max(4, len(families)))
    listbox = tk.Listbox(frame, height=height, width=38)
    for family in families:
        listbox.insert(tk.END, family)
    if current in families:
        index = families.index(current)
        listbox.selection_set(index)
        listbox.see(index)
    listbox.pack(fill=tk.BOTH, expand=True)

    result: dict[str, str | None] = {"value": None}

    def accept(event=None) -> None:
        selection = listbox.curselection()
        if selection:
            result["value"] = listbox.get(selection[0])
        window.destroy()

    buttons = tk.Frame(frame)
    buttons.pack(pady=(8, 0))
    tk.Button(buttons, text=tr("dialog.ok"), command=accept).pack(side=tk.LEFT, padx=4)
    tk.Button(buttons, text=tr("about.close"), command=window.destroy).pack(
        side=tk.LEFT, padx=4
    )

    listbox.bind("<Double-Button-1>", accept)
    window.bind("<Return>", accept)
    window.bind("<Escape>", lambda event: window.destroy())
    center_over_parent(window=window, parent=parent)
    window.grab_set()
    listbox.focus_set()
    window.wait_window()
    return result["value"]


class FontFamilySelector(tk.Frame):
    """Entry plus a buttons that opens a lightweight family picker."""

    def __init__(
        self,
        parent: tk.Misc,
        textvariable: tk.StringVar,
        families_provider: Callable[[], list[str]],
    ) -> None:
        super().__init__(parent)
        self._provider = families_provider
        self._values: list[str] = []
        self.entry = tk.Entry(self, textvariable=textvariable, width=22)
        self.entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.button = tk.Button(self, text="…", width=3, command=self._choose)
        self.button.pack(side=tk.LEFT)

    def _choose(self) -> None:
        selected = choose_font_family(
            self.winfo_toplevel(), self.entry.get(), self._provider()
        )
        if selected:
            self.entry.delete(0, tk.END)
            self.entry.insert(0, selected)

    def config(  # type: ignore[override]
        self,
        state: Literal["normal", "disabled"] | None = None,
        **kwargs,
    ) -> None:
        if state is not None:
            self.entry.config(state=state)
            self.button.config(state=state)
        super().config(**kwargs)

    def cget(self, key: str):
        if key == "state":
            return self.entry.cget("state")
        return super().cget(key)

    def __setitem__(self, key: str, value) -> None:
        if key == "values":
            self._values = list(value)
        else:
            super().__setitem__(key, value)

    def __getitem__(self, key: str):
        if key == "values":
            return tuple(self._values)
        return super().__getitem__(key)
