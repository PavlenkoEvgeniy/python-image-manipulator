"""Tests for the UI font family selection helpers."""

import tkinter as tk

import pytest

from image_manipulator import uifonts


class _FakeRoot:
    """Minimal root exposing the ``tk.call`` used to configure named fonts."""

    def __init__(self, fail_call: bool = False) -> None:
        self.tk = self
        self.fail_call = fail_call
        self.calls = []

    def call(self, *args):
        if self.fail_call:
            raise tk.TclError("font configuration failed")
        self.calls.append(args)


@pytest.fixture(autouse=True)
def _restore_active_family():
    yield
    uifonts._active_family = uifonts._DEFAULT_FAMILY


def test_tcl_error_while_listing_fonts_returns_none(monkeypatch):
    def fail_families(root=None):
        raise tk.TclError("font enumeration failed")

    monkeypatch.setattr(uifonts.tkfont, "families", fail_families)

    assert uifonts.apply_ui_family(_FakeRoot(), ["Arial"]) is None


def test_tcl_error_while_configuring_named_fonts_keeps_the_family(monkeypatch):
    monkeypatch.setattr(
        uifonts.tkfont, "families", lambda root=None: ["Arial", "DejaVu Sans"]
    )
    root = _FakeRoot(fail_call=True)

    assert uifonts.apply_ui_family(root, ["DejaVu Sans"]) == "DejaVu Sans"
    assert uifonts._active_family == "DejaVu Sans"


def test_first_installed_preferred_family_is_applied(monkeypatch):
    monkeypatch.setattr(
        uifonts.tkfont, "families", lambda root=None: ["DejaVu Sans", "Noto Sans"]
    )
    root = _FakeRoot()

    assert uifonts.apply_ui_family(root, ["Missing", "Noto Sans", "DejaVu Sans"]) == (
        "Noto Sans"
    )
    assert len(root.calls) == len(uifonts._NAMED_FONTS)
    assert {call[4] for call in root.calls} == {"Noto Sans"}
