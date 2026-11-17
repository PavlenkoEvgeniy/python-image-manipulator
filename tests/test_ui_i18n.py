"""Tk smoke tests for the interface language (skipped without a display)."""

import time

import pytest

tk = pytest.importorskip("tkinter")

from image_manipulator import ui  # noqa: E402
from image_manipulator.update_checker import UpdateInfo  # noqa: E402


@pytest.fixture
def app(monkeypatch):
    """Build the app in Russian without touching the real settings file."""
    monkeypatch.setattr(ui, "load_settings", lambda: None)
    monkeypatch.setattr(ui, "save_settings", lambda *args, **kwargs: True)
    monkeypatch.setattr(ui, "clear_settings", lambda *args, **kwargs: True)
    monkeypatch.setattr(ui, "detect_system_language", lambda: "ru")

    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk is unavailable: {exc}")
    root.withdraw()

    try:
        yield ui.ManipulatorApp(root), root
    finally:
        root.destroy()
        ui.set_language("en")


def test_widgets_use_the_detected_language(app):
    application, _ = app

    assert application.language_var.get() == "ru"
    assert application.status_var.get() == "Готово"
    assert application.preset_var.get() == "Другой"


def test_snapshot_stores_canonical_enum_tokens(app):
    application, _ = app

    application.position_var.set("нижний правый")
    application.font_style_var.set("Полужирный")

    snapshot = application._get_settings_snapshot()

    assert snapshot["position"] == "bottom right"
    assert snapshot["font_style"] == "Bold"
    assert snapshot["language"] == "ru"


def test_browse_output_starts_in_the_current_folder(app, monkeypatch, tmp_path):
    application, _ = app
    application.output_dir_var.set(str(tmp_path))
    calls = []
    monkeypatch.setattr(
        ui.filedialog,
        "askdirectory",
        lambda **kwargs: calls.append(kwargs) or "",
    )

    application.browse_output_dir()

    assert calls[0]["initialdir"] == str(tmp_path)


def test_browse_output_falls_back_to_the_default_folder(app, monkeypatch):
    application, _ = app
    application.output_dir_var.set("/path/that/does/not/exist")
    calls = []
    monkeypatch.setattr(
        ui.filedialog,
        "askdirectory",
        lambda **kwargs: calls.append(kwargs) or "",
    )

    application.browse_output_dir()

    assert calls[0]["initialdir"] == application._default_output_dir()


def _pump(root, seconds=0.5):
    deadline = time.time() + seconds
    while time.time() < deadline:
        root.update()
        time.sleep(0.02)


def test_reset_does_not_resave_and_announces_restart(app, monkeypatch):
    application, root = app
    saved, cleared, notices = [], [], []
    monkeypatch.setattr(
        ui, "save_settings", lambda *a, **k: saved.append(True) or True
    )
    monkeypatch.setattr(
        ui, "clear_settings", lambda *a, **k: cleared.append(True) or True
    )
    monkeypatch.setattr(ui.messagebox, "askyesno", lambda *a, **k: True)
    monkeypatch.setattr(ui, "detect_system_language", lambda: "en")
    monkeypatch.setattr(
        ui.ErrorDialog,
        "show_info",
        staticmethod(lambda *a, **k: notices.append(a)),
    )

    application.reset_settings()
    _pump(root)

    assert cleared == [True]
    assert saved == []
    assert application._save_after_id is None
    assert notices


def test_update_result_opens_the_update_dialog(app, monkeypatch):
    application, _ = app
    captured = []
    monkeypatch.setattr(
        ui, "UpdateDialog", lambda parent, info: captured.append(info)
    )
    info = UpdateInfo(
        version="9.0.0",
        download_url="https://example.com/linux",
        release_url="https://example.com/release",
    )

    application._on_update_result(False, info, None)

    assert captured == [info]
    assert application._update_check_running is False
