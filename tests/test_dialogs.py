"""Regression tests for Tk dialogs.

These tests need a display, so they skip wherever Tk cannot start (headless CI).
The rest of the suite stays display-free.
"""

import os
import sys

import gc
import logging

import pytest

tk = pytest.importorskip("tkinter")

if sys.platform == "darwin" and os.environ.get("CI"):
    pytest.skip("Tk GUI tests are unstable on macOS CI", allow_module_level=True)

from image_manipulator import dialogs, i18n  # noqa: E402
from image_manipulator.update_checker import UpdateInfo  # noqa: E402


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


def test_update_dialog_opens_the_direct_download(root, monkeypatch):
    i18n.set_language("en")
    opened = []
    monkeypatch.setattr(
        dialogs.webbrowser, "open", lambda url: opened.append(url) or True
    )
    info = UpdateInfo(
        version="9.0.0",
        download_url="https://example.com/ImageManipulator-linux",
        release_url="https://example.com/release",
    )

    dialog = dialogs.UpdateDialog(root, info)
    root.update_idletasks()

    assert dialog.download_button.cget("text") == "Download"
    dialog._download()

    assert opened == ["https://example.com/ImageManipulator-linux"]


def test_message_dialog_survives_a_window_deleted_while_waiting(
    root, monkeypatch
):
    # The user closes the dialog while wait_visibility() is pending. The
    # constructor must not let TclError escape: it used to propagate out of
    # the polling callback and kill event processing forever, which froze
    # the status bar and left the Process All button disabled after a run.
    def raise_deleted(self, *args, **kwargs):
        raise tk.TclError(
            'window ".!toplevel" was deleted before its visibility changed'
        )

    monkeypatch.setattr(tk.Misc, "winfo_ismapped", lambda self: False)
    monkeypatch.setattr(tk.Misc, "wait_visibility", raise_deleted)

    dialogs.ErrorDialog.show_info("Finished", "All done", parent=root)


def test_about_icon_failure_is_logged(root, monkeypatch, caplog):
    def broken_icon(size=None):
        raise FileNotFoundError("icon.png is missing")

    monkeypatch.setattr(dialogs, "load_icon_image", broken_icon)

    with caplog.at_level(logging.WARNING, logger=dialogs.logger.name):
        _open_about(root)

    assert "Could not load the About dialog icon" in caplog.text
    assert _image_labels(root) == []


def test_update_dialog_insecure_url_and_failed_open(root, monkeypatch, caplog):
    opened = []
    monkeypatch.setattr(dialogs.webbrowser, "open", lambda url: opened.append(url) or False)
    info = UpdateInfo(version="9.0.0", download_url="http://insecure/x", release_url="https://example/release")
    dialog = dialogs.UpdateDialog(root, info)
    with caplog.at_level(logging.WARNING, logger=dialogs.logger.name):
        dialog._download()
    assert opened == ["https://example/release"]
    assert "Could not open the download page" in caplog.text


def test_message_dialogs_mapped_error_and_warning(root, monkeypatch):
    monkeypatch.setattr(tk.Misc, "winfo_ismapped", lambda self: True)
    dialogs.ErrorDialog.show_warning("Warning", "Careful", parent=root)
    dialogs.ErrorDialog.show_error("Error", "Broken", parent=root)
