"""Tests for the lightweight font-family selector and picker."""

import os
import sys

import pytest

tk = pytest.importorskip("tkinter")

if sys.platform == "darwin" and os.environ.get("CI"):
    pytest.skip("Tk GUI tests are unstable on macOS CI", allow_module_level=True)

from image_manipulator import font_selector, i18n  # noqa: E402


@pytest.fixture
def root():
    try:
        window = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk is unavailable: {exc}")
    window.withdraw()
    try:
        yield window
    finally:
        window.destroy()


def _widgets(widget):
    yield widget
    for child in widget.winfo_children():
        yield from _widgets(child)


def _dialog(root):
    return next(
        widget for widget in root.winfo_children() if isinstance(widget, tk.Toplevel)
    )


def _listbox(window):
    return next(widget for widget in _widgets(window) if isinstance(widget, tk.Listbox))


def _button(window, text):
    return next(
        widget
        for widget in _widgets(window)
        if isinstance(widget, tk.Button) and widget.cget("text") == text
    )


class TestSelector:
    def test_state_values_and_choose(self, root, monkeypatch):
        variable = tk.StringVar(master=root, value="Arial")
        selector = font_selector.FontFamilySelector(
            root, variable, lambda: ["Arial", "DejaVu Sans"]
        )

        assert selector.cget("state") == "normal"
        selector.config(state="disabled")
        assert selector.cget("state") == "disabled"
        selector.config(state="normal", padx=2)
        assert selector.cget("state") == "normal"

        selector["values"] = ("Arial", "DejaVu Sans")
        assert selector["values"] == ("Arial", "DejaVu Sans")
        selector["width"] = 10
        assert int(selector.cget("width")) == 10
        assert int(selector["width"]) == 10
        selector.config(padx=4)

        monkeypatch.setattr(
            font_selector, "choose_font_family", lambda *args: "DejaVu Sans"
        )
        selector._choose()
        assert variable.get() == "DejaVu Sans"

    def test_cancelled_picker_keeps_the_value(self, root, monkeypatch):
        variable = tk.StringVar(master=root, value="Arial")
        selector = font_selector.FontFamilySelector(root, variable, lambda: [])
        monkeypatch.setattr(font_selector, "choose_font_family", lambda *args: None)

        selector._choose()

        assert variable.get() == "Arial"


class TestPicker:
    def test_accepts_a_selection(self, root):
        families = ["Arial", "DejaVu Sans"]

        def pick():
            window = _dialog(root)
            listbox = _listbox(window)
            listbox.selection_clear(0, tk.END)
            listbox.selection_set(1)
            _button(window, i18n.tr("dialog.ok")).invoke()

        root.after(50, pick)

        assert (
            font_selector.choose_font_family(root, "Arial", families) == "DejaVu Sans"
        )

    def test_current_family_is_preselected_and_missing_family_is_ignored(self, root):
        families = ["Arial", "DejaVu Sans"]

        def pick():
            window = _dialog(root)
            listbox = _listbox(window)
            listbox.selection_clear(0, tk.END)
            listbox.selection_set(0)
            _button(window, i18n.tr("dialog.ok")).invoke()

        root.after(50, pick)

        assert font_selector.choose_font_family(root, "Missing", families) == "Arial"

    def test_accept_without_selection_returns_none(self, root):
        def pick():
            window = _dialog(root)
            _button(window, i18n.tr("dialog.ok")).invoke()

        root.after(50, pick)

        assert font_selector.choose_font_family(root, "", []) is None

    def test_close_button_returns_none(self, root):
        def pick():
            window = _dialog(root)
            _button(window, i18n.tr("about.close")).invoke()

        root.after(50, pick)

        assert font_selector.choose_font_family(root, "", ["Arial"]) is None
