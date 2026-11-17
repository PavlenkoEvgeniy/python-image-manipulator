"""Tk smoke tests for the main-window actions (skipped without a display)."""

import logging
import threading
from types import SimpleNamespace
from typing import ClassVar

import pytest
from PIL import Image

tk = pytest.importorskip("tkinter")

from image_manipulator import icon, settings_store, ui  # noqa: E402
from image_manipulator.pipeline import ProcessResult  # noqa: E402
from image_manipulator.settings_snapshot import SettingsSnapshot  # noqa: E402
from image_manipulator.ui_events import CompleteEvent, UpdateEvent  # noqa: E402


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setattr(ui, "load_settings", lambda: None)
    monkeypatch.setattr(ui, "save_settings", lambda *args, **kwargs: True)
    monkeypatch.setattr(ui, "clear_settings", lambda *args, **kwargs: True)
    monkeypatch.setattr(ui, "detect_system_language", lambda: "en")
    monkeypatch.setattr(
        ui.tkfont, "families", lambda root=None: ["Arial", "DejaVu Sans"]
    )
    monkeypatch.setattr(ui, "center_on_screen", lambda *args, **kwargs: None)

    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk is unavailable: {exc}")
    root.withdraw()
    application = ui.ManipulatorApp(root)
    try:
        yield application, root
    finally:
        application._preview_debouncer.cancel()
        application._save_debouncer.cancel()
        root.destroy()


def _capture_dialogs(monkeypatch):
    calls = {"info": [], "warning": [], "error": [], "update": []}
    monkeypatch.setattr(
        ui.MessageDialogs,
        "show_info",
        staticmethod(lambda *a, **k: calls["info"].append(a)),
    )
    monkeypatch.setattr(
        ui.MessageDialogs,
        "show_warning",
        staticmethod(lambda *a, **k: calls["warning"].append(a)),
    )
    monkeypatch.setattr(
        ui.MessageDialogs,
        "show_error",
        staticmethod(lambda *a, **k: calls["error"].append(a)),
    )
    monkeypatch.setattr(
        ui,
        "UpdateDialog",
        lambda parent, info: calls["update"].append(info),
    )
    return calls


def _image(path, color="red"):
    Image.new("RGB", (32, 24), color).save(path)
    return str(path)


class TestWindowAndLanguage:
    def test_language_selection_shows_restart_notice(self, app, monkeypatch):
        application, _ = app
        calls = _capture_dialogs(monkeypatch)

        application._on_language_selected()

        assert calls["info"]
        assert application._save_debouncer.pending is True
        application.root.update()

    def test_dnd_success_binds_the_drop_handler(self, app):
        application, _ = app
        calls = []

        class Widget:
            def drop_target_register(self, kind):
                calls.append(("register", kind))

            def dnd_bind(self, event, callback):
                calls.append(("bind", event))

        application._enable_dnd(Widget())

        assert calls == [("register", ui.DND_FILES), ("bind", "<<Drop>>")]

    def test_dnd_failure_is_logged(self, app, caplog):
        application, _ = app

        class BrokenWidget:
            def drop_target_register(self, *args):
                raise RuntimeError("no dnd")

        with caplog.at_level(logging.WARNING, logger=ui.logger.name):
            application._enable_dnd(BrokenWidget())

        assert "Could not enable drag & drop" in caplog.text

    def test_setup_dnd_returns_when_unavailable(self, app, monkeypatch):
        application, _ = app
        monkeypatch.setattr(ui, "HAS_DND", False)

        application._setup_dnd()


def test_window_icon_failure_is_logged(monkeypatch, caplog):
    monkeypatch.setattr(ui, "load_settings", lambda: None)
    monkeypatch.setattr(ui, "save_settings", lambda *a, **k: True)
    monkeypatch.setattr(ui, "detect_system_language", lambda: "en")
    monkeypatch.setattr(
        icon, "load_icon_image", lambda: (_ for _ in ()).throw(OSError("no icon"))
    )
    monkeypatch.setattr(ui, "center_on_screen", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        ui.tkfont, "families", lambda root=None: ["Arial", "DejaVu Sans"]
    )
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk is unavailable: {exc}")
    root.withdraw()

    with caplog.at_level(logging.WARNING, logger=ui.logger.name):
        application = ui.ManipulatorApp(root)
    root.destroy()

    assert "Could not set the window icon" in caplog.text
    application._preview_debouncer.cancel()
    application._save_debouncer.cancel()


class TestPreviewActions:
    def test_refresh_without_an_image_clears_the_size(self, app):
        application, _ = app
        application.original_image = None

        application._refresh_preview()

        assert application.output_size_var.get() == ui.tr("preview.output_size_empty")

    def test_refresh_handles_build_failure(self, app, monkeypatch):
        application, _ = app
        application.original_image = Image.new("RGB", (10, 10))
        monkeypatch.setattr(
            application,
            "_build_manipulator",
            lambda: (_ for _ in ()).throw(RuntimeError("bad settings")),
        )

        application._refresh_preview()

        assert "bad settings" in application.status_var.get()

    def test_show_image_uses_a_fallback_canvas_size(self, app, monkeypatch):
        application, _ = app
        monkeypatch.setattr(application.preview_canvas, "winfo_width", lambda: 1)
        monkeypatch.setattr(application.preview_canvas, "winfo_height", lambda: 1)

        application._show_image(Image.new("RGB", (50, 50), "red"))

        assert application.preview_canvas.image is not None

    def test_show_image_with_a_normal_canvas(self, app, monkeypatch):
        application, _ = app
        monkeypatch.setattr(application.preview_canvas, "winfo_width", lambda: 500)
        monkeypatch.setattr(application.preview_canvas, "winfo_height", lambda: 500)

        application._show_image(Image.new("RGB", (50, 50), "red"))

        assert application.preview_canvas.image is not None

    def test_show_image_handles_only_the_height_being_tiny(self, app, monkeypatch):
        application, _ = app
        monkeypatch.setattr(application.preview_canvas, "winfo_width", lambda: 500)
        monkeypatch.setattr(application.preview_canvas, "winfo_height", lambda: 1)

        application._show_image(Image.new("RGB", (50, 50), "red"))

        assert application.preview_canvas.image is not None

    def test_preview_error_and_empty_result(self, app):
        application, _ = app
        application._preview_generation = 1

        application._on_preview_ready(1, None, RuntimeError("boom"))
        assert "boom" in application.status_var.get()

        application._on_preview_ready(1, None, None)


class TestImageList:
    def test_load_images_uses_the_dialog(self, app, monkeypatch, tmp_path):
        application, _ = app
        source = _image(tmp_path / "photo.png")
        monkeypatch.setattr(
            ui.filedialog, "askopenfilenames", lambda **kwargs: (source,)
        )

        application.load_images()

        assert application.image_paths == [source]
        assert application.current_index == 0

    def test_load_images_with_no_selection(self, app, monkeypatch):
        application, _ = app
        monkeypatch.setattr(ui.filedialog, "askopenfilenames", lambda **kwargs: ())

        application.load_images()

        assert application.image_paths == []

    def test_add_files_skips_unsupported_and_duplicates(
        self, app, monkeypatch, tmp_path
    ):
        application, _ = app
        source = _image(tmp_path / "photo.png")
        note = tmp_path / "note.txt"
        note.write_text("x", encoding="utf-8")
        calls = _capture_dialogs(monkeypatch)

        application._add_files(
            [source, source, str(note), str(tmp_path / "missing.png")]
        )

        assert application.image_paths == [source]
        assert not calls["warning"]

        application._add_files([str(note)])

        assert calls["warning"]

        second = _image(tmp_path / "second.png", "blue")
        application._add_files([second])
        assert len(application.image_paths) == 2

    def test_drop_adds_files(self, app, tmp_path):
        application, root = app
        source = _image(tmp_path / "photo.png")
        event = SimpleNamespace(data=root.tk.call("list", source))

        application._on_drop(event)

        assert source in application.image_paths

    def test_listbox_selection_loads_and_skips_empty(self, app, tmp_path):
        application, _ = app
        source = _image(tmp_path / "photo.png")
        application._add_files([source])

        application.file_listbox.selection_clear(0, tk.END)
        application._on_listbox_select()
        application.file_listbox.selection_set(0)
        application._on_listbox_select()
        application._on_listbox_select()

        assert application.current_index == 0
        assert application.original_image is not None

    def test_selecting_a_broken_image_reports_an_error(
        self, app, monkeypatch, tmp_path
    ):
        application, _ = app
        broken = tmp_path / "broken.png"
        broken.write_text("not an image", encoding="utf-8")
        calls = _capture_dialogs(monkeypatch)
        application._add_files([str(broken)])

        application.file_listbox.selection_clear(0, tk.END)
        application._on_listbox_select()
        application.file_listbox.selection_set(0)
        application._on_listbox_select()

        assert calls["error"]

    def test_select_index_rejects_out_of_range(self, app):
        application, _ = app

        application._select_index(99)
        application.current_index = 0
        application._load_current_image()

        assert application.current_index == 0

    def test_remove_the_last_image(self, app, tmp_path):
        application, _ = app
        application._add_files([_image(tmp_path / "only.png")])
        application.file_listbox.selection_set(0)

        application.remove_selected()

        assert application.image_paths == []
        assert application.current_index == -1

    def test_remove_selected_and_clear(self, app, tmp_path):
        application, _ = app
        first = _image(tmp_path / "a.png")
        second = _image(tmp_path / "b.png", "blue")
        application._add_files([first, second])

        application.file_listbox.selection_clear(0, tk.END)
        application.remove_selected()
        application.file_listbox.selection_set(0)
        application.remove_selected()
        application.clear_images()

        assert application.image_paths == []
        assert application.current_index == -1
        assert application.original_image is None


class TestTextAndFontHandlers:
    def test_save_settings_now_and_apply_saved(self, app, monkeypatch):
        application, _ = app
        saved = []
        monkeypatch.setattr(
            ui, "save_settings", lambda snapshot: saved.append(snapshot)
        )

        application._save_settings_now()
        assert saved

        application._apply_saved_settings(settings_store.default_settings())
        assert application.language_var.get() == "en"

        snapshot = SettingsSnapshot.defaults()
        snapshot.font_path = "/definitely/missing.ttf"
        application._apply_settings(snapshot)
        assert application.font_path is None

    def test_choose_color_cancel_and_apply(self, app, monkeypatch):
        application, _ = app
        monkeypatch.setattr(ui.colorchooser, "askcolor", lambda **kwargs: (None, None))
        application.choose_color()
        assert application.text_color == ui.config.default_color

        monkeypatch.setattr(
            ui.colorchooser, "askcolor", lambda **kwargs: (None, "#123456")
        )
        application.choose_color()
        assert application.text_color == "#123456"

    def test_choose_font_cancel_and_apply(self, app, monkeypatch, tmp_path):
        application, _ = app
        monkeypatch.setattr(ui.filedialog, "askopenfilename", lambda **kwargs: "")
        application.choose_font()

        font = tmp_path / "custom.ttf"
        font.write_bytes(b"font")
        monkeypatch.setattr(
            ui.filedialog, "askopenfilename", lambda **kwargs: str(font)
        )
        application.choose_font()

        assert application.font_path == str(font)
        assert str(application.font_family_combo.cget("state")) == "disabled"

        application.use_system_font()

        assert application.font_path is None
        assert str(application.font_family_combo.cget("state")) == "normal"

    def test_system_font_families_handles_tcl_error(self, app, monkeypatch, caplog):
        application, _ = app
        monkeypatch.setattr(
            ui.tkfont, "families", lambda root=None: ["DejaVu Sans", "Arial"]
        )
        assert application._system_font_families() == ["Arial", "DejaVu Sans"]

        application._refresh_font_families()
        assert application.font_family_combo["values"] == ("Arial", "DejaVu Sans")

        def broken(root=None):
            raise tk.TclError("no fonts")

        monkeypatch.setattr(ui.tkfont, "families", broken)
        with caplog.at_level(logging.WARNING, logger=ui.logger.name):
            assert application._system_font_families() == []
        assert "Failed to enumerate system fonts" in caplog.text

    def test_preset_and_dimension_handlers(self, app):
        application, _ = app
        application.preset_var.set("1920x1080")
        application._on_preset_selected()
        assert application.width_var.get() == "1920"

        application.preset_var.set("Custom")
        application._on_preset_selected()

        application._applying_preset = True
        application.width_var.set("123")
        application._applying_preset = False
        application.width_var.set("456")
        assert application.preset_var.get() == ui.tr("resize.custom")

    def test_apply_existing_font_path(self, app, tmp_path):
        application, _ = app
        font = tmp_path / "custom.ttf"
        font.write_bytes(b"font")
        snapshot = SettingsSnapshot.defaults()
        snapshot.font_path = str(font)

        application._apply_settings(snapshot)

        assert application.font_path == str(font)
        assert str(application.font_family_combo.cget("state")) == "disabled"

    def test_reset_cancel_and_same_language(self, app, monkeypatch):
        application, _ = app
        monkeypatch.setattr(ui.messagebox, "askyesno", lambda *a, **k: False)
        application.reset_settings()

        monkeypatch.setattr(ui.messagebox, "askyesno", lambda *a, **k: True)
        monkeypatch.setattr(ui, "detect_system_language", lambda: "en")
        application.reset_settings()

    def test_browse_output_dir_cancel_and_apply(self, app, monkeypatch, tmp_path):
        application, _ = app
        monkeypatch.setattr(ui.filedialog, "askdirectory", lambda **kwargs: "")
        application.browse_output_dir()
        assert application.output_dir_var.get()

        monkeypatch.setattr(
            ui.filedialog, "askdirectory", lambda **kwargs: str(tmp_path)
        )
        application.browse_output_dir()
        assert application.output_dir_var.get() == str(tmp_path)


class _Var:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value


class _FakeThread:
    started: ClassVar[list] = []

    def __init__(self, target=None, args=(), daemon=None):
        self.target = target
        self.args = args
        self.daemon = daemon

    def start(self):
        self.started.append((self.target, self.args))


class TestProcessing:
    def test_start_processing_without_images_warns(self, app, monkeypatch):
        application, _ = app
        calls = _capture_dialogs(monkeypatch)

        application.start_processing()

        assert calls["warning"]

    def test_start_processing_ignores_a_second_run(self, app):
        application, _ = app
        application._processing = True

        application.start_processing()

    def test_overwrite_confirmation_cancel_and_start(self, app, monkeypatch, tmp_path):
        application, _ = app
        application._add_files([_image(tmp_path / "a.png")])
        application.overwrite_var.set(True)
        monkeypatch.setattr(ui, "threading", SimpleNamespace(Thread=_FakeThread))
        monkeypatch.setattr(ui.messagebox, "askyesno", lambda *a, **k: False)

        application.start_processing()
        assert application._processing is False

        monkeypatch.setattr(ui.messagebox, "askyesno", lambda *a, **k: True)
        application.start_processing()
        assert application._processing is True
        assert str(application.process_button.cget("state")) == "disabled"

    def test_worker_ignores_a_result_without_an_error(self, app):
        application, _ = app

        class FailingManipulator:
            def process_path(self, *args, **kwargs):
                return ProcessResult(False, error=None)

        application._process_worker(["a.png"], FailingManipulator(), "/tmp", False)

        events = []
        while not application._events.empty():
            events.append(application._events.get_nowait())
        complete = next(event for event in events if isinstance(event, CompleteEvent))
        assert complete.errors == []

    def test_worker_collects_a_process_error(self, app):
        application, _ = app

        class FailingManipulator:
            def process_path(self, *args, **kwargs):
                return ProcessResult(False, error="cannot process")

        application._process_worker(["a.png"], FailingManipulator(), "/tmp", False)

        events = []
        while not application._events.empty():
            events.append(application._events.get_nowait())
        complete = next(event for event in events if isinstance(event, CompleteEvent))
        assert complete.errors == ["cannot process"]

    def test_worker_stops_before_the_first_file_when_cancelled(self, app):
        application, _ = app
        application._cancel_event.set()

        application._process_worker(["a.png"], None, "/tmp", False)

        event = application._events.get_nowait()
        assert isinstance(event, CompleteEvent)
        assert event.success == 0

    def test_completion_with_more_than_three_errors(self, app, monkeypatch):
        application, _ = app
        calls = _capture_dialogs(monkeypatch)

        application._on_processing_complete(
            1, 5, ["a", "b", "c", "d", "e"], "/tmp", False
        )

        assert calls["warning"]
        assert "and 2 more" in calls["warning"][0][1]

    def test_show_about_constructs_the_dialog(self, app, monkeypatch):
        application, _ = app
        shown = []
        monkeypatch.setattr(ui, "AboutDialog", lambda parent: shown.append(parent))

        application.show_about()

        assert shown == [application.root]


class TestUpdateCheck:
    def test_maybe_check_respects_the_setting(self, app, monkeypatch):
        application, _ = app
        started = []
        monkeypatch.setattr(
            application, "_start_update_check", lambda manual: started.append(manual)
        )
        application.check_updates_var.set(False)
        application._maybe_check_updates()
        application.check_updates_var.set(True)
        application._maybe_check_updates()

        assert started == [False]

    def test_automatic_check_starts_a_thread(self, app, monkeypatch):
        application, _ = app
        _FakeThread.started = []
        monkeypatch.setattr(ui, "threading", SimpleNamespace(Thread=_FakeThread))
        application.check_updates_var.set(True)

        application._start_update_check(False)

        assert _FakeThread.started

    def test_manual_check_starts_a_thread(self, app, monkeypatch):
        application, _ = app
        _FakeThread.started = []
        monkeypatch.setattr(ui, "threading", SimpleNamespace(Thread=_FakeThread))

        application.check_updates_now()

        assert application._update_check_running is True
        assert application.status_var.get() == ui.tr("status.checking_updates")
        assert _FakeThread.started

    def test_start_check_ignores_duplicates_and_disabled_auto(self, app, monkeypatch):
        application, _ = app
        application._update_check_running = True
        application._start_update_check(True)
        application._update_check_running = False
        application.check_updates_var.set(False)
        application._start_update_check(False)

        assert application._update_check_running is False

    def test_worker_reports_error_and_success(self, app, monkeypatch):
        application, _ = app
        monkeypatch.setattr(
            ui, "check_for_update", lambda: (_ for _ in ()).throw(OSError("offline"))
        )
        application._update_worker(True)
        error_event = application._events.get_nowait()
        assert isinstance(error_event, UpdateEvent)
        assert error_event.error == "offline"

        info = object()
        monkeypatch.setattr(ui, "check_for_update", lambda: info)
        application._update_worker(False)
        success_event = application._events.get_nowait()
        assert success_event.info is info

    def test_dispatch_ignores_an_unknown_event(self, app):
        application, _ = app

        application._dispatch_event(object())

    def test_dispatch_complete_event(self, app, monkeypatch):
        application, _ = app
        captured = []
        monkeypatch.setattr(
            application,
            "_on_processing_complete",
            lambda *args: captured.append(args),
        )

        application._dispatch_event(CompleteEvent(1, 1, [], "/tmp", False))

        assert captured == [(1, 1, [], "/tmp", False)]

    def test_int_value_without_limits(self):
        assert ui.ManipulatorApp._int_value(_Var("5"), 1) == 5

    def test_on_close_without_processing(self):
        destroyed = []

        class StubRoot:
            def destroy(self):
                destroyed.append(True)

        app = SimpleNamespace(
            _processing=False,
            _cancel_event=threading.Event(),
            root=StubRoot(),
            _cancel_scheduled_preview=lambda: None,
            _cancel_scheduled_settings_save=lambda: None,
            _save_settings_now=lambda: None,
        )

        ui.ManipulatorApp._on_close(app)

        assert destroyed == [True]

    def test_update_result_paths(self, app, monkeypatch):
        application, _ = app
        calls = _capture_dialogs(monkeypatch)
        application.status_var.set(ui.tr("status.checking_updates"))

        application._on_update_result(True, None, "offline")
        assert calls["warning"]

        application.status_var.set(ui.tr("status.checking_updates"))
        application._on_update_result(True, None, None)
        assert calls["info"]

        application._on_update_result(False, object(), None)
        assert calls["update"]

        application._on_update_result(False, None, "silent")
        application._on_update_result(False, None, None)
