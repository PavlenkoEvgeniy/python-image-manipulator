"""Coverage tests for the 1.8.0 code base (no behavior changes)."""

import logging
import os
import subprocess
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image, ImageDraw, ImageFont

from image_manipulator import app as app_module
from image_manipulator import config, i18n, icon, logging_config, positioning
from image_manipulator import settings_store, text_overlay, uifonts, update_checker
from image_manipulator.pipeline import (
    ImageManipulator,
    _flatten_to_rgb,
    _normalize_mode,
    _prepare_for_save,
    load_image,
    save_image,
)
from image_manipulator.text_overlay import TextOverlay


class TestApp:
    def test_create_root_fallback(self, monkeypatch):
        class BrokenTk:
            def __init__(self, *a, **k):
                raise RuntimeError("no dnd")

        monkeypatch.setitem(sys.modules, "tkinterdnd2", SimpleNamespace(TkinterDnD=SimpleNamespace(Tk=BrokenTk)))
        try:
            root = app_module.create_root()
        except Exception as exc:
            pytest.skip(f"Tk unavailable: {exc}")
        root.destroy()

    def test_main(self, monkeypatch):
        calls = []

        class Root:
            def mainloop(self):
                calls.append("mainloop")

        monkeypatch.setattr(app_module, "setup_logging", lambda *a, **k: calls.append("logging"))
        monkeypatch.setattr(app_module, "create_root", lambda: Root())
        monkeypatch.setattr("image_manipulator.ui.ManipulatorApp", lambda root: calls.append("app"))

        app_module.main()

        assert calls == ["logging", "app", "mainloop"]


class TestConfig:
    def test_resource_path_meipass(self, monkeypatch):
        monkeypatch.setattr(sys, "_MEIPASS", "/bundle", raising=False)
        assert config.resource_path("icon.png") == os.path.join("/bundle", "icon.png")

    def test_resource_path_fallback(self, monkeypatch, tmp_path):
        monkeypatch.delattr(sys, "_MEIPASS", raising=False)
        monkeypatch.chdir(tmp_path)
        assert config.resource_path("icon.png") == str(tmp_path / "icon.png")

    def test_get_app_dir(self, monkeypatch):
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setattr(sys, "executable", "/opt/app/bin")
        assert config.get_app_dir() == "/opt/app"
        monkeypatch.setattr(sys, "frozen", False, raising=False)
        assert config.get_app_dir() == os.path.dirname(os.path.abspath(config.__file__))


class TestIcon:
    def test_frozen_paths(self, monkeypatch):
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setattr(sys, "_MEIPASS", "/bundle", raising=False)
        assert icon.get_icon_path() == os.path.join("/bundle", "image_manipulator", "icon.png")
        monkeypatch.delattr(sys, "_MEIPASS", raising=False)
        monkeypatch.setattr(sys, "executable", "/opt/app/image-manipulator")
        assert icon.get_icon_path() == os.path.join("/opt/app", "image_manipulator", "icon.png")


class TestLogging:
    def test_with_and_without_file(self, monkeypatch, tmp_path):
        captured = {}
        monkeypatch.setattr(logging, "basicConfig", lambda **kwargs: captured.update(kwargs))
        logging_config.setup_logging(logging.DEBUG, str(tmp_path / "app.log"))
        assert len(captured["handlers"]) == 2
        logging_config.setup_logging()
        assert len(captured["handlers"]) == 1


class TestI18n:
    def teardown_method(self):
        i18n.set_language("en")

    def test_catalog_failures(self, monkeypatch, tmp_path):
        monkeypatch.setattr(i18n, "CATALOG_DIR", str(tmp_path))
        i18n._catalogs.pop("xx", None)
        (tmp_path / "xx.json").write_text("[1,2]", encoding="utf-8")
        assert i18n.load_catalog("xx") == {}
        i18n._catalogs.pop("yy", None)
        (tmp_path / "yy.json").write_text("{bad", encoding="utf-8")
        assert i18n.load_catalog("yy") == {}

    def test_bad_placeholders(self):
        assert "{count}" in i18n.tr("status.added", wrong=1)

    def test_os_locale_names(self, monkeypatch):
        monkeypatch.setattr(i18n.locale, "getlocale", lambda: ("ru_RU", "UTF-8"))
        monkeypatch.setattr(i18n.locale, "getdefaultlocale", lambda: ("de_DE", "UTF-8"), raising=False)
        assert i18n._os_locale_names() == ["ru_RU", "de_DE"]

        monkeypatch.setattr(i18n.locale, "getlocale", lambda: (_ for _ in ()).throw(TypeError("x")))
        monkeypatch.setattr(i18n.locale, "getdefaultlocale", lambda: (_ for _ in ()).throw(ValueError("y")), raising=False)
        assert i18n._os_locale_names() == []

        monkeypatch.setattr(i18n.locale, "getlocale", lambda: (None, None))
        monkeypatch.setattr(i18n.locale, "getdefaultlocale", lambda: (None, None), raising=False)
        assert i18n._os_locale_names() == []

        monkeypatch.delattr(i18n.locale, "getdefaultlocale", raising=False)
        monkeypatch.setattr(i18n.locale, "getlocale", lambda: ("en_US", "UTF-8"))
        assert i18n._os_locale_names() == ["en_US"]

    def test_detect_without_env(self, monkeypatch):
        monkeypatch.setattr(i18n, "_os_locale_names", lambda: ["ru_RU"])
        monkeypatch.setattr(i18n.os, "environ", {})
        assert i18n.detect_system_language() == "ru"


class TestPipeline:
    def test_normalize_modes(self):
        assert _normalize_mode(Image.new("L", (2, 2))).mode == "RGB"
        p = Image.new("P", (2, 2))
        p.info["transparency"] = 0
        assert _normalize_mode(p).mode == "RGBA"
        la = Image.new("LA", (2, 2))
        assert _normalize_mode(la).mode == "RGBA"

    def test_cmyk_profile_is_dropped(self, tmp_path):
        source = tmp_path / "cmyk.jpg"
        Image.new("CMYK", (8, 8), (0, 0, 0, 0)).save(source)
        image, profile = load_image(source)
        assert image.mode == "RGB"
        assert profile is None

    def test_flatten_and_gif(self):
        assert _flatten_to_rgb(Image.new("L", (2, 2))).mode == "RGB"
        assert _prepare_for_save(Image.new("RGB", (2, 2)), "GIF").mode == "P"

    def test_save_bmp_without_icc(self, tmp_path, monkeypatch):
        captured = {}
        def fake_save(self, target, **kwargs):
            captured.update(kwargs); Path(target).write_bytes(b"x")
        monkeypatch.setattr(Image.Image, "save", fake_save)
        save_image(Image.new("RGB", (2, 2)), tmp_path / "out.bmp", "BMP")
        assert "quality" not in captured

    def test_save_options(self, tmp_path, monkeypatch):
        captured = {}
        def fake_save(self, target, **kwargs):
            captured.update(kwargs)
            Path(target).write_bytes(b"x")
        monkeypatch.setattr(Image.Image, "save", fake_save)
        save_image(Image.new("RGB", (2, 2)), tmp_path / "out.webp", "WEBP", jpeg_quality=80, icc_profile=b"p")
        assert captured["quality"] == 80
        assert captured["icc_profile"] == b"p"

    def test_render_overlay_none(self):
        class Overlay:
            text = "x"
            def apply_text(self, image):
                return None
        result = ImageManipulator(target_width=2, target_height=2, text_overlay=Overlay()).render(Image.new("RGB", (2, 2)))
        assert result.size == (2, 2)

    def test_unsupported_overwrite_and_corrupt(self, tmp_path):
        source = tmp_path / "photo.xyz"
        source.write_text("x", encoding="utf-8")
        out, fmt = ImageManipulator().resolve_output_path(source, tmp_path / "out", Image.new("RGB", (2, 2)), overwrite=True)
        assert out.parent == tmp_path / "out"
        assert fmt == "JPEG"
        broken = tmp_path / "broken.png"
        broken.write_text("nope", encoding="utf-8")
        assert ImageManipulator().process_path(broken, tmp_path / "out").success is False


class TestPositioning:
    class Window:
        def __init__(self, mapped=True, rootx=10, rooty=20):
            self.mapped = mapped; self.rootx = rootx; self.rooty = rooty; self.calls = []
        def geometry(self, value): self.calls.append(value)
        def update_idletasks(self): pass
        def update(self): pass
        def winfo_pointerx(self): return 100
        def winfo_pointery(self): return 100
        def winfo_screenwidth(self): return 1920
        def winfo_screenheight(self): return 1080
        def winfo_reqwidth(self): return 400
        def winfo_reqheight(self): return 300
        def winfo_width(self): return 1000
        def winfo_height(self): return 800
        def winfo_rootx(self): return self.rootx
        def winfo_rooty(self): return self.rooty
        def winfo_ismapped(self): return self.mapped

    def test_monitors(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "screeninfo", SimpleNamespace(get_monitors=lambda: [SimpleNamespace(x=1,y=2,width=3,height=4)]))
        assert positioning.detect_monitors() == [(1,2,3,4)]
        monkeypatch.setitem(sys.modules, "screeninfo", SimpleNamespace(get_monitors=lambda: (_ for _ in ()).throw(RuntimeError())))
        assert positioning.detect_monitors() == []

    def test_centering_and_align(self):
        w = self.Window(); positioning.center_on_screen(w, 800, 600, monitors=[(0,0,1920,1080)]); assert w.calls
        w2 = self.Window(); positioning.center_on_screen(w2, 800, 600, monitors=[]); assert w2.calls
        positioning._align_client(self.Window(mapped=True), 10, 20, 100, 50)
        positioning._align_client(self.Window(mapped=False), 10, 20, 100, 50)
        positioning.center_over_parent(window=self.Window(), parent=self.Window(rootx=100, rooty=50))

    def test_detection_used(self, monkeypatch):
        w = self.Window(); monkeypatch.setattr(positioning, "detect_monitors", lambda: [])
        positioning.center_on_screen(w, 100, 100); assert w.calls


class TestSettingsStore:
    def test_platform_paths(self, monkeypatch, tmp_path):
        monkeypatch.setattr(sys, "platform", "win32"); monkeypatch.setenv("APPDATA", r"C:\Users\me\AppData\Roaming")
        assert settings_store.get_settings_path().endswith("settings.json")
        monkeypatch.setattr(sys, "platform", "darwin"); monkeypatch.setenv("HOME", str(tmp_path))
        assert "Library" in settings_store.get_settings_path()
        monkeypatch.setattr(sys, "platform", "linux"); monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        assert settings_store.get_settings_path().startswith(str(tmp_path))

    def test_save_and_clear_failures(self, monkeypatch, tmp_path):
        monkeypatch.setattr(settings_store.os, "replace", lambda *a, **k: (_ for _ in ()).throw(OSError("x")))
        assert settings_store.save_settings(settings_store.default_settings(), path=str(tmp_path / "s.json")) is False
        monkeypatch.setattr(settings_store.os, "remove", lambda p: (_ for _ in ()).throw(OSError("cleanup")))
        assert settings_store.save_settings(settings_store.default_settings(), path=str(tmp_path / "t.json")) is False
        target = tmp_path / "s.json"; target.write_text("{}", encoding="utf-8")
        monkeypatch.setattr(settings_store.os, "remove", lambda p: (_ for _ in ()).throw(OSError("x")))
        assert settings_store.clear_settings(path=str(target)) is False


class TestTextOverlay:
    def test_load_system_font_paths(self, monkeypatch):
        sentinel = object()
        o = TextOverlay(font_family="Family", font_style="Bold", font_size=20)
        monkeypatch.setattr(TextOverlay, "_try_load_font", staticmethod(lambda name, size: sentinel), raising=False)
        # 1.8.0 has no _try_load_font; patch ImageFont.truetype instead.
        monkeypatch.setattr(ImageFont, "truetype", lambda name, size, **kwargs: sentinel)
        assert o._load_system_font(20) is sentinel

        monkeypatch.setattr(ImageFont, "truetype", lambda name, size: (_ for _ in ()).throw(OSError()))
        monkeypatch.setattr(TextOverlay, "_fontconfig_candidates", staticmethod(lambda family, style: ["/tmp/font.ttf"]))
        monkeypatch.setattr(ImageFont, "truetype", lambda name, size: sentinel if name == "/tmp/font.ttf" else (_ for _ in ()).throw(OSError()))
        assert o._load_system_font(20) is sentinel

        monkeypatch.setattr(TextOverlay, "_fontconfig_candidates", staticmethod(lambda family, style: []))
        monkeypatch.setattr(ImageFont, "truetype", lambda name, size: (_ for _ in ()).throw(OSError()))
        assert o._load_system_font(20) is None

    def test_font_path_failures_and_get_font_fallback(self, monkeypatch):
        sentinel = object()
        o = TextOverlay(font_family="Family", font_size=20)
        monkeypatch.setattr(
            ImageFont,
            "truetype",
            lambda name, size: sentinel if name == "good" else (_ for _ in ()).throw(OSError()),
        )
        monkeypatch.setattr(TextOverlay, "_fontconfig_candidates", staticmethod(lambda family, style: ["bad", "good"]))
        assert o._load_system_font(20) is sentinel

        o2 = TextOverlay(font_size=20)
        monkeypatch.setattr(o2, "_font_candidates", lambda size: iter(()))
        monkeypatch.setattr(ImageFont, "load_default", lambda: sentinel)
        assert o2.get_font(20) is sentinel

    def test_fontconfig_parsing(self, tmp_path, monkeypatch):
        exact = tmp_path / "exact.ttf"; exact.write_bytes(b"x")
        regular = tmp_path / "regular.ttf"; regular.write_bytes(b"x")
        other = tmp_path / "other.ttf"; other.write_bytes(b"x")
        stdout = f"{exact}:style=Bold\n{regular}:style=Regular\n{other}:style=Thin\nmissing.ttf:style=Bold\n"
        monkeypatch.setattr(subprocess, "run", lambda *a, **k: SimpleNamespace(stdout=stdout))
        assert TextOverlay._fontconfig_candidates("F", "Bold") == [str(exact), str(regular), str(other)]
        monkeypatch.setattr(subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(OSError()))
        assert TextOverlay._fontconfig_candidates("F", "Bold") == []

    def test_font_candidates(self, tmp_path, monkeypatch):
        custom = tmp_path / "custom.ttf"; custom.write_bytes(b"x")
        sentinel = object()
        o = TextOverlay(font_path=str(custom), font_size=20)
        monkeypatch.setattr(ImageFont, "truetype", lambda name, size, **kwargs: sentinel)
        monkeypatch.setattr(TextOverlay, "_load_system_font", lambda self, size: sentinel)
        assert list(o._font_candidates(20))[:2] == [sentinel, sentinel]

        bad = tmp_path / "bad.ttf"; bad.write_bytes(b"x")
        o2 = TextOverlay(font_path=str(bad), font_size=20)
        monkeypatch.setattr(ImageFont, "truetype", lambda name, size: (_ for _ in ()).throw(OSError()))
        monkeypatch.setattr(ImageFont, "load_default", lambda: sentinel)
        assert list(o2._font_candidates(20))[-1] is sentinel

    def test_font_for_text_fallback_and_probe(self, monkeypatch):
        o = TextOverlay(font_size=20)
        monkeypatch.setattr(o, "_font_candidates", lambda size: iter(()))
        sentinel = object(); monkeypatch.setattr(ImageFont, "load_default", lambda: sentinel)
        assert o.get_font_for_text(20, "x") is sentinel
        monkeypatch.setattr(o, "_font_candidates", lambda size: iter([object()]))
        monkeypatch.setattr(TextOverlay, "_renders_text", staticmethod(lambda font, text: False))
        assert o.get_font_for_text(20, "x") is not None

    def test_measurement_fallback(self):
        o = TextOverlay(font_size=20)
        draw = ImageDraw.Draw(Image.new("RGB", (20, 20)))
        font = o.get_font(20)
        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setattr(ImageDraw.ImageDraw, "textbbox", lambda *a, **k: (_ for _ in ()).throw(RuntimeError()))
        monkeypatch.setattr(ImageDraw.ImageDraw, "textsize", lambda self, text, font=None: (10, 5), raising=False)
        try:
            assert o.get_text_size(draw, "Hi", font) == (10, 5, 0, 0)
        finally:
            monkeypatch.undo()

    def test_style_and_position(self):
        assert TextOverlay(font_size=20)._get_stroke_width(20, True) >= 1
        assert TextOverlay(font_size=20)._get_stroke_width(20, False) == 0
        assert TextOverlay(font_style="Bold Italic")._get_style_flags() == (True, True)
        assert TextOverlay(position="unknown").calculate_position(10, 10, 1, 1) == (0, 0)
        class Broken:
            def getbbox(self, text):
                raise RuntimeError()
        assert TextOverlay._renders_text(Broken(), "x") is True


class TestUifonts:
    def teardown_method(self):
        uifonts._active_family = uifonts._DEFAULT_FAMILY

    def test_no_candidates(self):
        assert uifonts.apply_ui_family(SimpleNamespace(), []) is None
        assert uifonts._active_family == "Arial"

    def test_applies_family_and_tcl_error(self, monkeypatch):
        import tkinter as tk
        monkeypatch.setattr(uifonts, "tk", tk, raising=False)
        class Root:
            def __init__(self, fail=False): self.tk = self; self.fail = fail
            def call(self, *args):
                if self.fail: raise tk.TclError("x")
        monkeypatch.setattr(uifonts.tkfont, "families", lambda root=None: ["DejaVu Sans"])
        assert uifonts.apply_ui_family(Root(), ["DejaVu Sans"]) == "DejaVu Sans"
        assert uifonts.apply_ui_family(Root(fail=True), ["DejaVu Sans"]) == "DejaVu Sans"

        monkeypatch.setattr(uifonts.tkfont, "families", lambda root=None: (_ for _ in ()).throw(tk.TclError()))
        assert uifonts.apply_ui_family(Root(), ["Missing"]) is None

    def test_ui_font(self):
        assert len(uifonts.ui_font(10)) == 2
        assert len(uifonts.ui_font(10, "bold")) == 3


class TestMainModule:
    def test_main_module_runs_app_main(self, monkeypatch):
        import runpy
        import importlib
        called = []
        monkeypatch.setattr("image_manipulator.app.main", lambda: called.append(True))
        runpy.run_module("image_manipulator.__main__", run_name="__main__")
        importlib.import_module("image_manipulator.__main__")
        assert called == [True]


class TestUpdateChecker:
    def test_os_release_missing_and_assets(self, monkeypatch):
        assert update_checker.linux_package_kind("/definitely/missing", which=lambda n: None) == "deb"
        assert update_checker._https_assets(None, "linux") == []
        assert update_checker._https_assets([None, 5, {"name": "x"}], "linux") == []
        assert update_checker._https_assets([{"name": "x", "browser_download_url": "https://x/1"}], "linux") == []

    def test_asset_fallbacks_and_fetch(self, monkeypatch):
        assert update_checker.pick_download_url(
            [{"name": "image-windows.zip", "browser_download_url": "https://x/w"}], "win32"
        ) == "https://x/w"
        assert update_checker.pick_download_url(
            [{"name": "image-macos.zip", "browser_download_url": "https://x/m"}], "darwin"
        ) == "https://x/m"
        assert update_checker.pick_download_url(
            [{"name": "image-linux.zip", "browser_download_url": "https://x/l"}], "linux"
        ) == "https://x/l"

        class Response:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self, size): return b'{"tag_name": "v9.0.0"}'
        monkeypatch.setattr(update_checker.urllib.request, "urlopen", lambda request, timeout=None: Response())
        assert update_checker.fetch_latest_release()["tag_name"] == "v9.0.0"

        class BadResponse(Response):
            def read(self, size):
                return b"[]"

        monkeypatch.setattr(update_checker.urllib.request, "urlopen", lambda request, timeout=None: BadResponse())
        with pytest.raises(ValueError):
            update_checker.fetch_latest_release()

        monkeypatch.setattr(update_checker, "platform_asset_key", lambda platform: "other")
        assert update_checker.pick_download_url(
            [{"name": "other.bin", "browser_download_url": "https://x/o"}], "other"
        ) == "https://x/o"
