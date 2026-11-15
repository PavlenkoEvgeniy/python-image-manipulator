"""Regression tests for Tk dialogs.

These tests need a display, so they skip wherever Tk cannot start (headless CI).
The rest of the suite stays display-free.
"""

import gc
import logging

import pytest

tk = pytest.importorskip("tkinter")

from image_manipulator import dialogs  # noqa: E402


@pytest.fixture
def root():
    """Provide a withdrawn Tk root, or skip when Tk is unavailable."""
    try:
        window = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk is unavailable: {exc}")
    window.withdraw()
    try:
        yield window
    finally:
        window.destroy()


def _open_about(root):
    """Open the About dialog, skipping when the environment cannot show it."""
    try:
        return dialogs.AboutDialog(root)
    except tk.TclError as exc:
        pytest.skip(f"Tk cannot show a dialog here: {exc}")


def _walk(widget):
    yield widget
    for child in widget.winfo_children():
        yield from _walk(child)


def _image_labels(root):
    """Labels in the dialog widgets that display an image."""
    labels = []
    for toplevel in root.winfo_children():
        for widget in _walk(toplevel):
            if "image" in widget.keys() and widget.cget("image"):
                labels.append(widget)
    return labels


def test_about_icon_survives_dialog_garbage_collection(root):
    # ManipulatorApp.show_about() discards the dialog instance right away.
    dialogs.AboutDialog(root)

    labels = _image_labels(root)
    assert labels, "the About dialog did not create the logo label"
    image_name = labels[0].cget("image")

    gc.collect()
    root.update_idletasks()

    live_images = {str(name) for name in root.tk.call("image", "names")}
    assert image_name in live_images, "the logo image was garbage-collected"


def test_about_icon_failure_is_logged(root, monkeypatch, caplog):
    def broken_icon(size=None):
        raise FileNotFoundError("icon.png is missing")

    monkeypatch.setattr(dialogs, "load_icon_image", broken_icon)

    with caplog.at_level(logging.WARNING, logger=dialogs.logger.name):
        _open_about(root)

    assert "Could not load the About dialog icon" in caplog.text
    assert _image_labels(root) == []
