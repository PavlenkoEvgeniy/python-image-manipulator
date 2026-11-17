"""Tk action coverage for the 1.8.0 user interface."""

import logging
import os
import queue
import sys
import threading
from types import SimpleNamespace

import pytest
from PIL import Image

tk = pytest.importorskip("tkinter")

if sys.platform == "darwin" and os.environ.get("CI"):
    pytest.skip("Tk GUI tests are unstable on macOS CI", allow_module_level=True)

from image_manipulator import icon, settings_store, ui  # noqa: E402


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setattr(ui, "load_settings", lambda: None)
    monkeypatch.setattr(ui, "save_settings", lambda *a, **k: True)
    monkeypatch.setattr(ui, "clear_settings", lambda *a, **k: True)
    monkeypatch.setattr(ui, "detect_system_language", lambda: "en")
    monkeypatch.setattr(ui, "center_on_screen", lambda *a, **k: None)
    monkeypatch.setattr(ui.tkfont, "families", lambda root=None: ["Arial", "DejaVu Sans"])
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk unavailable: {exc}")
    root.withdraw()
    application = ui.ManipulatorApp(root)
    try:
        yield application, root
    finally:
        application._cancel_scheduled_preview()
        application._cancel_scheduled_settings_save()
        root.destroy()


def _dialogs(monkeypatch):
    calls = {"info": [], "warning": [], "error": [], "update": []}
    for level in ("info", "warning", "error"):
        monkeypatch.setattr(
            ui.ErrorDialog,
            f"show_{level}",
            staticmethod(lambda *a, _l=level, **k: calls[_l].append(a)),
        )
    monkeypatch.setattr(ui, "UpdateDialog", lambda parent, info: calls["update"].append(info))
    return calls


def _image(path, color="red"):
    Image.new("RGB", (32, 24), color).save(path)
    return str(path)


class TestWindowAndHandlers:
    def test_icon_failure(self, monkeypatch, caplog):
        monkeypatch.setattr(ui, "load_settings", lambda: None)
        monkeypatch.setattr(ui, "save_settings", lambda *a, **k: True)
        monkeypatch.setattr(ui, "detect_system_language", lambda: "en")
        monkeypatch.setattr(ui, "center_on_screen", lambda *a, **k: None)
        monkeypatch.setattr(icon, "load_icon_image", lambda: (_ for _ in ()).throw(OSError("no icon")))
        monkeypatch.setattr(ui.tkfont, "families", lambda root=None: ["Arial"])
        try:
            root = tk.Tk()
        except tk.TclError as exc:
            pytest.skip(f"Tk unavailable: {exc}")
        root.withdraw()
        with caplog.at_level(logging.WARNING, logger=ui.logger.name):
            app = ui.ManipulatorApp(root)
        assert "Could not set the window icon" in caplog.text
        app._cancel_scheduled_preview(); app._cancel_scheduled_settings_save(); root.destroy()

    def test_language_and_dimension_handlers(self, app, monkeypatch):
        application, _ = app
        calls = _dialogs(monkeypatch)
        application._on_language_selected()
        assert calls["info"]
        application._applying_preset = True
        application._on_dimension_changed()
        application._applying_preset = False
        application._on_dimension_changed()
        assert application.preset_var.get() == ui.tr("resize.custom")

        application.preset_var.set("1920x1080")
        application._on_preset_selected()
        assert application.width_var.get() == "1920"
        application.preset_var.set("Custom")
        application._on_preset_selected()

    def test_dnd_paths(self, app, monkeypatch):
        application, _ = app
        monkeypatch.setattr(ui, "HAS_DND", False)
        application._setup_dnd()
        monkeypatch.setattr(ui, "HAS_DND", True)

        class Good:
            def drop_target_register(self, kind): pass
            def dnd_bind(self, event, callback): pass

        class Bad:
            def drop_target_register(self, kind): raise RuntimeError("bad")

        application.root = Good(); application.file_listbox = Good(); application.preview_canvas = Good()
        application._setup_dnd()
        application.file_listbox = Bad()
        application._setup_dnd()

    def test_preview_paths(self, app, monkeypatch):
        application, _ = app
        application.original_image = None
        application._refresh_preview()
        assert application.output_size_var.get() == ui.tr("preview.output_size_empty")

        application.original_image = Image.new("RGB", (40, 30))
        monkeypatch.setattr(application, "_build_manipulator", lambda: (_ for _ in ()).throw(RuntimeError("bad")))
        application._refresh_preview()
        assert "bad" in application.status_var.get()

        application._build_manipulator = lambda: SimpleNamespace(render=lambda img: img.copy())
        application._refresh_preview()
        assert application.preview_canvas.image is not None

        monkeypatch.setattr(application.preview_canvas, "winfo_width", lambda: 1)
        monkeypatch.setattr(application.preview_canvas, "winfo_height", lambda: 1)
        application._show_image(Image.new("RGB", (50, 50)))
        monkeypatch.setattr(application.preview_canvas, "winfo_width", lambda: 500)
        monkeypatch.setattr(application.preview_canvas, "winfo_height", lambda: 500)
        application._show_image(Image.new("RGB", (50, 50)))

    def test_debounce_cancel_errors(self, app, monkeypatch):
        application, _ = app
        application._preview_after_id = "preview-id"
        application._save_after_id = "save-id"
        monkeypatch.setattr(application.root, "after_cancel", lambda ident: (_ for _ in ()).throw(RuntimeError("gone")))
        application._schedule_preview()
        application._schedule_settings_save()
        application._cancel_scheduled_preview()
        application._cancel_scheduled_settings_save()
        assert application._preview_after_id is None
        assert application._save_after_id is None


class TestImageList:
    def test_load_and_add_files(self, app, monkeypatch, tmp_path):
        application, _ = app
        source = _image(tmp_path / "photo.png")
        calls = _dialogs(monkeypatch)
        monkeypatch.setattr(ui.filedialog, "askopenfilenames", lambda **k: ())
        application.load_images()
        monkeypatch.setattr(ui.filedialog, "askopenfilenames", lambda **k: (source,))
        application.load_images()
        note = tmp_path / "note.txt"; note.write_text("x", encoding="utf-8")
        application._add_files([source, str(note), str(tmp_path / "missing.png")])
        application._add_files([str(note)])
        assert calls["warning"]

    def test_drop_and_list_selection(self, app, monkeypatch, tmp_path):
        application, root = app
        _dialogs(monkeypatch)
        source = _image(tmp_path / "a.png")
        application._on_drop(SimpleNamespace(data=root.tk.call("list", source)))
        application.file_listbox.selection_clear(0, tk.END)
        application._on_listbox_select()
        application.file_listbox.selection_set(0)
        application._on_listbox_select()
        application._on_listbox_select()
        assert application.original_image is not None

        broken = tmp_path / "broken.png"; broken.write_text("x", encoding="utf-8")
        application._add_files([str(broken)])
        application.file_listbox.selection_clear(0, tk.END)
        application.file_listbox.selection_set(1)
        application._on_listbox_select()

    def test_select_load_remove_clear(self, app, tmp_path, monkeypatch):
        application, _ = app
        first = _image(tmp_path / "a.png"); second = _image(tmp_path / "b.png", "blue")
        application._select_index(99)
        application.current_index = -1
        application.image_paths = []
        application._load_current_image()

        application._add_files([first, second])
        application.file_listbox.selection_clear(0, tk.END)
        application.remove_selected()
        application.file_listbox.selection_set(0)
        application.remove_selected()
        application.file_listbox.selection_set(0)
        application.remove_selected()
        application.clear_images()
        assert application.image_paths == []
        assert application.current_index == -1


class TestSettingsAndTextHandlers:
    def test_save_apply_reset(self, app, monkeypatch, tmp_path):
        application, _ = app
        saved = []
        monkeypatch.setattr(ui, "save_settings", lambda snapshot: saved.append(snapshot))
        application._save_settings_now()
        assert saved

        application._apply_saved_settings(None)
        application._apply_saved_settings(settings_store.default_settings())

        font = tmp_path / "font.ttf"; font.write_bytes(b"x")
        settings = settings_store.default_settings(); settings["font_path"] = str(font)
        application._apply_saved_settings(settings)
        assert str(application.font_family_combo.cget("state")) == "disabled"
        settings["font_path"] = "/missing/font.ttf"
        application._apply_saved_settings(settings)
        assert application.font_path is None

        monkeypatch.setattr(ui.messagebox, "askyesno", lambda *a, **k: False)
        application.reset_settings()
        monkeypatch.setattr(ui.messagebox, "askyesno", lambda *a, **k: True)
        application.reset_settings()

    def test_color_font_and_paths(self, app, monkeypatch, tmp_path):
        application, _ = app
        monkeypatch.setattr(ui.colorchooser, "askcolor", lambda **k: (None, None))
        application.choose_color()
        monkeypatch.setattr(ui.colorchooser, "askcolor", lambda **k: (None, "#123456"))
        application.choose_color()
        assert application.text_color == "#123456"

        monkeypatch.setattr(ui.filedialog, "askopenfilename", lambda **k: "")
        application.choose_font()
        font = tmp_path / "custom.ttf"; font.write_bytes(b"x")
        monkeypatch.setattr(ui.filedialog, "askopenfilename", lambda **k: str(font))
        application.choose_font()
        assert application.font_path == str(font)
        application.use_system_font()
        assert application.font_path is None

        monkeypatch.setattr(ui.tkfont, "families", lambda root=None: ["Arial", "DejaVu Sans"])
        assert application._system_font_families() == ["Arial", "DejaVu Sans"]
        application._refresh_font_families()
        monkeypatch.setattr(ui.tkfont, "families", lambda root=None: (_ for _ in ()).throw(tk.TclError()))
        assert application._system_font_families() == []

        monkeypatch.setattr(ui.filedialog, "askdirectory", lambda **k: "")
        application.browse_output_dir()
        monkeypatch.setattr(ui.filedialog, "askdirectory", lambda **k: str(tmp_path))
        application.browse_output_dir()
        assert application.output_dir_var.get() == str(tmp_path)


class _FakeThread:
    started = []

    def __init__(self, target=None, args=(), daemon=None):
        self.target = target; self.args = args

    def start(self):
        self.started.append((self.target, self.args))


class TestProcessingAndUpdates:
    def test_start_processing_paths(self, app, monkeypatch, tmp_path):
        application, _ = app
        calls = _dialogs(monkeypatch)
        application.start_processing()
        assert calls["warning"]

        application._processing = True
        application.start_processing()
        application._processing = False

        application._add_files([_image(tmp_path / "a.png")])
        application.overwrite_var.set(True)
        _FakeThread.started = []
        monkeypatch.setattr(ui, "threading", SimpleNamespace(Thread=_FakeThread))
        monkeypatch.setattr(ui.messagebox, "askyesno", lambda *a, **k: False)
        application.start_processing()
        monkeypatch.setattr(ui.messagebox, "askyesno", lambda *a, **k: True)
        application.start_processing()
        assert application._processing is True
        assert str(application.process_button.cget("state")) == "disabled"

    def test_worker_and_complete(self, app, monkeypatch):
        application, _ = app
        calls = _dialogs(monkeypatch)

        class Good:
            def process_path(self, *a, **k):
                return SimpleNamespace(success=True, error=None)

        application._process_worker(["a.png"], Good(), "/tmp", False)
        status = application._events.get_nowait()
        complete = application._events.get_nowait()
        assert status[0] == "status" and complete[0] == "complete"

        class Bad:
            def process_path(self, *a, **k):
                return SimpleNamespace(success=False, error="err")

        application._process_worker(["a.png"], Bad(), "/tmp", False)
        application._events.get_nowait(); complete = application._events.get_nowait()
        assert complete[3] == ["err"]

        class Silent:
            def process_path(self, *a, **k):
                return SimpleNamespace(success=False, error=None)

        application._process_worker(["a.png"], Silent(), "/tmp", False)
        application._events.get_nowait(); complete = application._events.get_nowait()
        assert complete[3] == []

        class Boom:
            def process_path(self, *a, **k):
                raise RuntimeError("boom")

        application._process_worker(["a.png"], Boom(), "/tmp", False)
        application._events.get_nowait(); complete = application._events.get_nowait()
        assert complete[3] == []

        application._on_processing_complete(1, 1, [], "/tmp", False)
        application._on_processing_complete(1, 2, ["a", "b"], "/tmp", False)
        application._on_processing_complete(1, 2, ["a", "b", "c", "d"], "/tmp", True)
        assert calls["info"] and calls["warning"]

    def test_dispatch_and_poll(self, app, monkeypatch):
        application, _ = app
        application._dispatch_event(("status", "ready"))
        assert application.status_var.get() == "ready"
        seen = []
        monkeypatch.setattr(application, "_on_processing_complete", lambda *a: seen.append(a))
        application._dispatch_event(("complete", 1, 1, [], "/tmp", False))
        assert seen
        monkeypatch.setattr(application, "_on_update_result", lambda *a: seen.append(a))
        application._dispatch_event(("update", False, None, None))
        application._dispatch_event(("unknown",))

        application._poll_events()

        class GoneRoot:
            def after(self, ms, callback):
                raise RuntimeError("gone")

        stub = SimpleNamespace(_drain_events=lambda: None, root=GoneRoot(), _poll_events=lambda: None)
        ui.ManipulatorApp._poll_events(stub)

    def test_build_int_and_about(self, app, monkeypatch):
        application, _ = app
        assert application._build_manipulator() is not None
        assert ui.ManipulatorApp._int_value(SimpleNamespace(get=lambda: "abc"), 7) == 7
        assert ui.ManipulatorApp._int_value(SimpleNamespace(get=lambda: "99"), 7, 1, 10) == 10
        shown = []
        monkeypatch.setattr(ui, "AboutDialog", lambda parent: shown.append(parent))
        application.show_about()
        assert shown

    def test_update_paths(self, app, monkeypatch):
        application, _ = app
        calls = _dialogs(monkeypatch)
        started = []
        original_start = application._start_update_check
        application._start_update_check = lambda manual: started.append(manual)
        application.check_updates_var.set(False)
        application._maybe_check_updates()
        application.check_updates_var.set(True)
        application._maybe_check_updates()
        assert started == [False]
        application._start_update_check = original_start

        _FakeThread.started = []
        monkeypatch.setattr(ui, "threading", SimpleNamespace(Thread=_FakeThread))
        application._update_check_running = True
        application._start_update_check(True)
        application._update_check_running = False
        application.check_updates_var.set(False)
        application._start_update_check(False)
        application.check_updates_var.set(True)
        application._update_check_running = False
        application._start_update_check(True)
        application._update_check_running = False
        application._start_update_check(False)
        application.check_updates_now()
        assert _FakeThread.started

        monkeypatch.setattr(ui, "check_for_update", lambda: (_ for _ in ()).throw(OSError("offline")))
        application._update_worker(True)
        event = application._events.get_nowait()
        assert event[0] == "update" and event[3] == "offline"
        info = object(); monkeypatch.setattr(ui, "check_for_update", lambda: info)
        application._update_worker(False)
        assert application._events.get_nowait()[2] is info

        application.status_var.set(ui.tr("status.checking_updates"))
        application._on_update_result(True, None, "offline")
        application._on_update_result(False, None, "silent")
        application._on_update_result(True, None, None)
        application._on_update_result(False, None, None)
        application._on_update_result(False, info, None)
        assert calls["warning"] and calls["info"] and calls["update"]

    def test_close(self):
        destroyed = []
        app = SimpleNamespace(
            _cancel_scheduled_preview=lambda: None,
            _cancel_scheduled_settings_save=lambda: None,
            _save_settings_now=lambda: None,
            root=SimpleNamespace(destroy=lambda: destroyed.append(True)),
        )
        ui.ManipulatorApp._on_close(app)
        assert destroyed == [True]
