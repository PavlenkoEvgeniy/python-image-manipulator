"""Tests for error paths that are hard to reach through the main flows."""

import logging
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image, ImageFont

from image_manipulator import (
    config,
    i18n,
    logging_config,
    positioning,
    settings_store,
    text_overlay,
    ui,
    update_checker,
)
from image_manipulator.pipeline import ImageManipulator, _normalize_high_depth
from image_manipulator.resize import OutputFormat
from image_manipulator.text_overlay import TextOverlay


class _Var:
    def __init__(self, value=None):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class _Button:
    def __init__(self):
        self.state = None

    def config(self, **kwargs):
        self.state = kwargs.get("state")


class _Window:
    def __init__(self, mapped=True, rootx=10, rooty=20):
        self.mapped = mapped
        self.rootx = rootx
        self.rooty = rooty
        self.geometry_calls = []

    def geometry(self, value):
        self.geometry_calls.append(value)

    def update_idletasks(self):
        pass

    def update(self):
        pass

    def winfo_pointerx(self):
        return 100

    def winfo_pointery(self):
        return 100

    def winfo_screenwidth(self):
        return 1920

    def winfo_screenheight(self):
        return 1080

    def winfo_reqwidth(self):
        return 400

    def winfo_reqheight(self):
        return 300

    def winfo_width(self):
        return 1000

    def winfo_height(self):
        return 800

    def winfo_rootx(self):
        return self.rootx

    def winfo_rooty(self):
        return self.rooty

    def winfo_ismapped(self):
        return self.mapped


class TestConfigPaths:
    def test_resource_path_uses_meipass(self, monkeypatch):
        monkeypatch.setattr(sys, "_MEIPASS", "/bundle", raising=False)

        assert config.resource_path("icon.png") == os.path.join("/bundle", "icon.png")

    def test_resource_path_falls_back_to_cwd(self, monkeypatch, tmp_path):
        monkeypatch.delattr(sys, "_MEIPASS", raising=False)
        monkeypatch.chdir(tmp_path)

        assert config.resource_path("icon.png") == os.path.join(
            str(tmp_path), "icon.png"
        )

    def test_get_app_dir_for_frozen_build(self, monkeypatch):
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setattr(sys, "executable", "/opt/app/image-manipulator")

        assert config.get_app_dir() == "/opt/app"

    def test_get_app_dir_for_source_run(self, monkeypatch):
        monkeypatch.setattr(sys, "frozen", False, raising=False)

        assert config.get_app_dir() == os.path.dirname(os.path.abspath(config.__file__))


class TestLoggingConfiguration:
    def test_file_handler_is_added(self, monkeypatch, tmp_path):
        captured = {}
        monkeypatch.setattr(
            logging, "basicConfig", lambda **kwargs: captured.update(kwargs)
        )

        logging_config.setup_logging(logging.DEBUG, str(tmp_path / "app.log"))

        assert len(captured["handlers"]) == 2
        assert captured["level"] == logging.DEBUG

    def test_stream_handler_is_used_without_a_file(self, monkeypatch):
        captured = {}
        monkeypatch.setattr(
            logging, "basicConfig", lambda **kwargs: captured.update(kwargs)
        )

        logging_config.setup_logging()

        assert len(captured["handlers"]) == 1


class TestI18nEdges:
    def teardown_method(self):
        i18n.set_language("en")

    def test_language_info_uses_the_active_or_requested_language(self):
        i18n.set_language("en")

        assert i18n.language_info().code == "en"
        assert i18n.language_info("ru").code == "ru"

    def test_corrupt_catalog_is_cached_as_empty(self, monkeypatch, tmp_path):
        monkeypatch.setattr(i18n, "CATALOG_DIR", str(tmp_path))
        i18n._catalogs.pop("xx", None)
        (tmp_path / "xx.json").write_text("{not json", encoding="utf-8")

        assert i18n.load_catalog("xx") == {}
        assert i18n.load_catalog("xx") == {}

    def test_non_object_catalog_is_ignored(self, monkeypatch, tmp_path):
        monkeypatch.setattr(i18n, "CATALOG_DIR", str(tmp_path))
        i18n._catalogs.pop("yy", None)
        (tmp_path / "yy.json").write_text("[]", encoding="utf-8")

        assert i18n.load_catalog("yy") == {}

    def test_bad_placeholders_return_the_raw_text(self):
        i18n.set_language("en")

        assert "{count}" in i18n.tr("status.added")

    def test_os_locale_names_include_both_apis(self, monkeypatch):
        monkeypatch.setattr(i18n.locale, "getlocale", lambda: ("ru_RU.UTF-8", "UTF-8"))
        monkeypatch.setattr(
            i18n.locale,
            "getdefaultlocale",
            lambda: ("de_DE", "UTF-8"),
            raising=False,
        )

        names = i18n._os_locale_names()

        assert "ru_RU.UTF-8" in names
        assert "de_DE" in names

    def test_detection_uses_os_names_when_no_environment_is_given(self, monkeypatch):
        monkeypatch.setattr(i18n, "_os_locale_names", lambda: ["ru_RU"])
        monkeypatch.setattr(i18n.os, "environ", {})

        assert i18n.detect_system_language() == "ru"


class TestPositioningEdges:
    def test_detect_monitors_returns_rectangles(self, monkeypatch):
        monitor = SimpleNamespace(x=1, y=2, width=3, height=4)
        monkeypatch.setitem(
            sys.modules,
            "screeninfo",
            SimpleNamespace(get_monitors=lambda: [monitor]),
        )

        assert positioning.detect_monitors() == [(1, 2, 3, 4)]

    def test_detect_monitors_failure_is_empty(self, monkeypatch):
        def broken():
            raise RuntimeError("no display")

        monkeypatch.setitem(
            sys.modules, "screeninfo", SimpleNamespace(get_monitors=broken)
        )

        assert positioning.detect_monitors() == []

    def test_center_on_a_monitor(self):
        window = _Window()

        positioning.center_on_screen(window, 800, 600, monitors=[(0, 0, 1920, 1080)])

        assert window.geometry_calls
        assert window.geometry_calls[0].endswith("+560+240")

    def test_center_on_the_virtual_screen_without_monitor_data(self):
        window = _Window()

        positioning.center_on_screen(window, 800, 600, monitors=[])

        assert window.geometry_calls[0].endswith("+560+240")

    def test_center_over_parent_uses_parent_geometry(self):
        window = _Window()
        parent = _Window(rootx=100, rooty=50)

        positioning.center_over_parent(window=window, parent=parent)

        assert window.geometry_calls[0].startswith("400x300+")

    def test_unmapped_window_does_not_align_twice(self):
        window = _Window(mapped=False)

        positioning._align_client(window, 10, 20, 100, 50)

        assert window.geometry_calls == []

    def test_monitor_detection_is_used_when_not_injected(self, monkeypatch):
        window = _Window()
        monkeypatch.setattr(positioning, "detect_monitors", lambda: [])

        positioning.center_on_screen(window, 100, 100)

        assert window.geometry_calls


class TestSettingsEdges:
    def test_windows_settings_path(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "win32")
        monkeypatch.setenv("APPDATA", r"C:\Users\me\AppData\Roaming")

        path = settings_store.get_settings_path()

        assert "image-manipulator" in path
        assert path.endswith("settings.json")

    def test_macos_settings_path(self, monkeypatch, tmp_path):
        monkeypatch.setattr(sys, "platform", "darwin")
        monkeypatch.setenv("HOME", str(tmp_path))

        path = settings_store.get_settings_path()

        assert "Library" in path
        assert path.endswith("settings.json")

    def test_linux_settings_path_honours_xdg(self, monkeypatch, tmp_path):
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

        path = settings_store.get_settings_path()

        assert path.startswith(str(tmp_path))
        assert path.endswith("settings.json")

    def test_save_failure_cleans_up_the_temporary_file(self, monkeypatch, tmp_path):
        def fail_replace(*args, **kwargs):
            raise OSError("cannot replace")

        monkeypatch.setattr(settings_store.os, "replace", fail_replace)
        target = tmp_path / "settings.json"

        assert (
            settings_store.save_settings(
                settings_store.default_settings(), path=str(target)
            )
            is False
        )
        assert list(tmp_path.glob(".settings-*")) == []

    def test_clear_failure_returns_false(self, monkeypatch, tmp_path):
        target = tmp_path / "settings.json"
        target.write_text("{}", encoding="utf-8")

        def fail_remove(path):
            raise OSError("cannot remove")

        monkeypatch.setattr(settings_store.os, "remove", fail_remove)

        assert settings_store.clear_settings(path=str(target)) is False


class TestPipelineEdges:
    def test_float_range_is_scaled(self):
        image = Image.new("F", (3, 1))
        image.putdata([10.0, 20.0, 30.0])

        assert _normalize_high_depth(image).tobytes()[3] in range(120, 136)

    def test_float_constant_is_black(self):
        image = Image.new("F", (2, 1))
        image.putdata([5.0, 5.0])

        assert _normalize_high_depth(image).tobytes() == bytes(6)

    def test_integer_constant_keeps_its_value(self):
        image = Image.new("I", (2, 1))
        image.putdata([5, 5])

        assert _normalize_high_depth(image).tobytes() == bytes([5] * 6)

    def test_unsupported_overwrite_suffix_uses_the_output_folder(self, tmp_path):
        source = tmp_path / "photo.xyz"
        source.write_text("x", encoding="utf-8")
        rendered = Image.new("RGB", (10, 10))

        output_path, pil_format = ImageManipulator().resolve_output_path(
            source, tmp_path / "out", rendered, overwrite=True
        )

        assert output_path.parent == tmp_path / "out"
        assert pil_format == OutputFormat.JPEG.value

    def test_corrupt_image_is_reported_as_a_failure(self, tmp_path):
        source = tmp_path / "broken.png"
        source.write_text("not an image", encoding="utf-8")

        result = ImageManipulator().process_path(source, tmp_path / "out")

        assert result.success is False
        assert result.error


class TestUpdateCheckerEdges:
    class _Response:
        def __init__(self, payload):
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, size):
            return self.payload

    def test_fetch_reads_and_decodes_the_payload(self, monkeypatch):
        captured = {}

        def fake_urlopen(request, timeout=None):
            captured["request"] = request
            captured["timeout"] = timeout
            return self._Response(b'{"tag_name": "v9.0.0"}')

        monkeypatch.setattr(update_checker.urllib.request, "urlopen", fake_urlopen)

        payload = update_checker.fetch_latest_release(timeout=3)

        assert payload["tag_name"] == "v9.0.0"
        assert captured["timeout"] == 3
        assert "ImageManipulator" in captured["request"].get_header("User-agent")

    def test_fetch_rejects_a_non_object_payload(self, monkeypatch):
        monkeypatch.setattr(
            update_checker.urllib.request,
            "urlopen",
            lambda request, timeout=None: self._Response(b"[]"),
        )

        with pytest.raises(ValueError):
            update_checker.fetch_latest_release()


class TestTextOverlayEdges:
    def test_platform_font_files_caches_each_platform(self, monkeypatch):
        original = text_overlay._PLATFORM_FONT_FILES
        try:
            monkeypatch.setattr(sys, "platform", "win32")
            monkeypatch.setattr(
                text_overlay, "_windows_font_files", lambda: [("x", Path("y"))]
            )
            text_overlay._PLATFORM_FONT_FILES = None
            assert text_overlay._platform_font_files() == [("x", Path("y"))]

            monkeypatch.setattr(sys, "platform", "darwin")
            monkeypatch.setattr(
                text_overlay, "_macos_font_files", lambda: [("a", Path("b"))]
            )
            text_overlay._PLATFORM_FONT_FILES = None
            assert text_overlay._platform_font_files() == [("a", Path("b"))]

            monkeypatch.setattr(sys, "platform", "linux")
            text_overlay._PLATFORM_FONT_FILES = None
            assert text_overlay._platform_font_files() == []
        finally:
            text_overlay._PLATFORM_FONT_FILES = original

    def test_default_font_falls_back_without_a_size(self, monkeypatch):
        calls = []
        original = ImageFont.load_default

        def fake_load_default(size=None):
            calls.append(size)
            if size is not None:
                raise TypeError("size is not supported")
            return original()

        monkeypatch.setattr(text_overlay.ImageFont, "load_default", fake_load_default)

        assert text_overlay._default_font(20) is not None
        assert calls == [20, None]

    def test_glyph_probe_is_optimistic_when_masking_fails(self):
        class BrokenFont:
            def getmask(self, character):
                raise RuntimeError("no mask")

        assert TextOverlay._renders_text(BrokenFont(), "text") is True

    def test_invalid_custom_font_falls_back(self, tmp_path):
        custom = tmp_path / "bad.ttf"
        custom.write_bytes(b"not a font")
        overlay = TextOverlay(font_path=str(custom), font_size=20)

        fonts = list(overlay._font_candidates(20))

        assert fonts

    def test_platform_match_short_circuits_fontconfig(self, tmp_path, monkeypatch):
        path = tmp_path / "only.ttf"
        path.write_bytes(b"font")
        text_overlay._FONT_CANDIDATE_CACHE.clear()
        monkeypatch.setattr(
            text_overlay, "_platform_font_files", lambda: [("Only Regular", path)]
        )

        assert TextOverlay._fontconfig_candidates("Only Regular", "Regular") == [
            str(path)
        ]

    def test_unresolved_family_warns_once(self):
        text_overlay._WARNED_UNRESOLVED_FAMILIES.clear()
        overlay = TextOverlay(font_family="Definitely Missing Family", font_size=20)

        assert overlay._load_system_font(20) is None
        assert overlay._load_system_font(20) is None
        assert "definitely missing family" in {
            name.lower() for name in text_overlay._WARNED_UNRESOLVED_FAMILIES
        }

    def test_font_for_text_falls_back_to_the_last_candidate(self, monkeypatch):
        monkeypatch.setattr(
            TextOverlay, "_renders_text", classmethod(lambda cls, font, text: False)
        )
        overlay = TextOverlay(font_size=20)

        assert overlay.get_font_for_text(20, "text") is not None


class TestUiEdges:
    def test_int_value_clamps_and_falls_back(self):
        assert ui.ManipulatorApp._int_value(_Var("abc"), 7, 1, 10) == 7
        assert ui.ManipulatorApp._int_value(_Var("99"), 7, 1, 10) == 10
        assert ui.ManipulatorApp._int_value(_Var("-5"), 7, 1, 10) == 1

    def test_processing_complete_reports_success(self, monkeypatch):
        calls = []
        monkeypatch.setattr(
            ui.ErrorDialog,
            "show_info",
            staticmethod(lambda *args, **kwargs: calls.append(args)),
        )
        app = SimpleNamespace(
            _processing=True,
            process_button=_Button(),
            status_var=_Var(),
            root=None,
        )

        ui.ManipulatorApp._on_processing_complete(app, 2, 2, [], "/tmp", False)

        assert app._processing is False
        assert app.process_button.state == "normal"
        assert calls
        assert "2" in app.status_var.value

    def test_processing_complete_reports_errors(self, monkeypatch):
        calls = []
        monkeypatch.setattr(
            ui.ErrorDialog,
            "show_warning",
            staticmethod(lambda *args, **kwargs: calls.append(args)),
        )
        app = SimpleNamespace(
            _processing=True,
            process_button=_Button(),
            status_var=_Var(),
            root=None,
        )

        ui.ManipulatorApp._on_processing_complete(app, 1, 3, ["e1", "e2"], "/tmp", True)

        assert calls
        assert "1" in app.status_var.value

    def test_update_result_handles_error_and_latest(self, monkeypatch):
        warnings = []
        infos = []
        monkeypatch.setattr(
            ui.ErrorDialog,
            "show_warning",
            staticmethod(lambda *args, **kwargs: warnings.append(args)),
        )
        monkeypatch.setattr(
            ui.ErrorDialog,
            "show_info",
            staticmethod(lambda *args, **kwargs: infos.append(args)),
        )
        app = SimpleNamespace(
            _update_check_running=True,
            status_var=_Var(ui.tr("status.checking_updates")),
            root=None,
        )

        ui.ManipulatorApp._on_update_result(app, True, None, "offline")
        assert warnings
        assert app.status_var.value == ui.tr("status.ready")

        ui.ManipulatorApp._on_update_result(app, True, None, None)
        assert infos

        ui.ManipulatorApp._on_update_result(app, False, None, "silent")
        assert len(warnings) == 1

    def test_update_result_opens_the_dialog(self, monkeypatch):
        captured = []
        monkeypatch.setattr(
            ui, "UpdateDialog", lambda parent, info: captured.append(info)
        )
        app = SimpleNamespace(
            _update_check_running=True,
            status_var=_Var(ui.tr("status.ready")),
            root=None,
        )
        info = object()

        ui.ManipulatorApp._on_update_result(app, False, info, None)

        assert captured == [info]
        assert app._update_check_running is False

    def test_dispatch_event_routes_status_preview_and_update(self):
        app = SimpleNamespace(
            status_var=_Var(),
            _on_preview_ready=lambda *args: setattr(app, "preview", args),
            _on_update_result=lambda *args: setattr(app, "update", args),
        )

        ui.ManipulatorApp._dispatch_event(app, ("status", "ready"))
        assert app.status_var.value == "ready"

        ui.ManipulatorApp._dispatch_event(app, ("preview", 1, None, None))
        assert app.preview == (1, None, None)

        ui.ManipulatorApp._dispatch_event(app, ("update", False, None, None))
        assert app.update == (False, None, None)
