"""Tests for the remaining platform, fallback and defensive branches."""

import sys
import types
from pathlib import Path
from types import SimpleNamespace
from typing import ClassVar

import pytest
from PIL import Image, ImageFont

from image_manipulator import app as app_module
from image_manipulator import (
    debounce,
    i18n,
    icon,
    positioning,
    settings_snapshot,
    text_overlay,
    update_checker,
)
from image_manipulator.pipeline import (
    ImageManipulator,
    _flatten_to_rgb,
    _normalize_mode,
    _to_gif_palette,
    load_image,
    save_image,
)
from image_manipulator.text_overlay import TextOverlay


class TestAppBootstrap:
    def test_create_root_falls_back_when_dnd_fails(self, monkeypatch):
        class BrokenTk:
            def __init__(self, *args, **kwargs):
                raise RuntimeError("no dnd")

        monkeypatch.setitem(
            sys.modules,
            "tkinterdnd2",
            SimpleNamespace(TkinterDnD=SimpleNamespace(Tk=BrokenTk)),
        )
        try:
            root = app_module.create_root()
        except Exception as exc:
            pytest.skip(f"Tk is unavailable: {exc}")
        assert root is not None
        root.destroy()

    def test_main_bootstraps_the_ui(self, monkeypatch):
        calls = []

        class FakeRoot:
            def mainloop(self):
                calls.append("mainloop")

        monkeypatch.setattr(
            app_module, "setup_logging", lambda *a, **k: calls.append("logging")
        )
        monkeypatch.setattr(app_module, "create_root", lambda: FakeRoot())
        monkeypatch.setattr(
            "image_manipulator.ui.ManipulatorApp",
            lambda root: calls.append("app"),
        )

        app_module.main()

        assert calls == ["logging", "app", "mainloop"]


class TestIconFrozenPaths:
    def test_frozen_path_uses_meipass(self, monkeypatch):
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setattr(sys, "_MEIPASS", "/bundle", raising=False)

        assert icon.get_icon_path() == "/bundle/image_manipulator/icon.png"

    def test_frozen_path_falls_back_to_executable_dir(self, monkeypatch):
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.delattr(sys, "_MEIPASS", raising=False)
        monkeypatch.setattr(sys, "executable", "/opt/app/image-manipulator")

        assert icon.get_icon_path() == "/opt/app/image_manipulator/icon.png"


class TestDebouncer:
    def test_cancel_suppresses_a_deleted_after_callback(self):
        class StubRoot:
            callback = None

            def after(self, delay, callback):
                self.callback = callback
                return "after-id"

            def after_cancel(self, after_id):
                raise RuntimeError("window is gone")

        fired = []
        root = StubRoot()
        debouncer = debounce.Debouncer(root, 10, lambda: fired.append(True))
        debouncer.schedule()
        assert debouncer.pending is True
        root.callback()
        assert fired == [True]

        debouncer.schedule()
        debouncer.cancel()

        assert debouncer.pending is False


class TestSettingsSnapshotDefaults:
    def test_from_settings_fills_defaults(self):
        snapshot = settings_snapshot.SettingsSnapshot.from_settings({})

        assert snapshot.width > 0
        assert snapshot.font_path is None
        assert snapshot.to_settings()["language"] == "en"


class TestI18nRemaining:
    def teardown_method(self):
        i18n.set_language("en")

    def test_bad_placeholder_names_are_logged(self):
        assert i18n.tr("status.added", count=1) == "Added images: 1"

        # Unknown formatting fields are caught and the raw text is returned.
        assert "{count}" in i18n.tr("status.added", wrong=1)

    def test_os_locale_name_failures_are_ignored(self, monkeypatch):
        monkeypatch.setattr(
            i18n.locale, "getlocale", lambda: (_ for _ in ()).throw(TypeError("x"))
        )
        monkeypatch.setattr(
            i18n.locale,
            "getdefaultlocale",
            lambda: (_ for _ in ()).throw(ValueError("y")),
            raising=False,
        )

        assert i18n._os_locale_names() == []

    def test_os_locale_name_empty_values_are_ignored(self, monkeypatch):
        monkeypatch.setattr(i18n.locale, "getlocale", lambda: (None, None))
        monkeypatch.setattr(
            i18n.locale, "getdefaultlocale", lambda: (None, None), raising=False
        )

        assert i18n._os_locale_names() == []

    def test_os_locale_names_without_getdefaultlocale(self, monkeypatch):
        monkeypatch.setattr(i18n.locale, "getlocale", lambda: ("en_US", "UTF-8"))
        monkeypatch.delattr(i18n.locale, "getdefaultlocale", raising=False)

        assert i18n._os_locale_names() == ["en_US"]


class TestPipelineRemaining:
    def test_plain_mode_is_converted_to_rgb(self):
        assert _normalize_mode(Image.new("L", (2, 2))).mode == "RGB"

    def test_cmyk_profile_is_dropped(self, tmp_path):
        source = tmp_path / "cmyk.jpg"
        Image.new("CMYK", (8, 8), (0, 0, 0, 0)).save(source)

        image, profile = load_image(source)

        assert image.mode == "RGB"
        assert profile is None

    def test_flatten_plain_mode(self):
        assert _flatten_to_rgb(Image.new("L", (2, 2))).mode == "RGB"

    def test_short_palette_is_extended(self, monkeypatch):
        class FakePalette:
            mode = "P"
            info: ClassVar[dict] = {}

            def __init__(self):
                self.palette = [0, 0, 0]
                self.pasted = False

            def getpalette(self):
                return self.palette

            def putpalette(self, colors):
                self.palette = colors

            def paste(self, value, mask=None):
                self.pasted = True

        fake = FakePalette()
        monkeypatch.setattr(Image.Image, "quantize", lambda *a, **k: fake)

        result = _to_gif_palette(Image.new("RGBA", (2, 2), (255, 0, 0, 0)))

        assert len(result.palette) == 768
        assert result.pasted is True

    def test_long_palette_and_opaque_alpha_skip_both_branches(self, monkeypatch):
        class FakePalette:
            mode = "P"
            info: ClassVar[dict] = {}

            def __init__(self):
                self.palette = list(range(768))

            def getpalette(self):
                return self.palette

            def putpalette(self, colors):
                raise AssertionError("palette must not be extended")

            def paste(self, value, mask=None):
                raise AssertionError("opaque image must not be masked")

        fake = FakePalette()
        monkeypatch.setattr(Image.Image, "quantize", lambda *a, **k: fake)

        result = _to_gif_palette(Image.new("RGBA", (2, 2), (255, 0, 0, 255)))

        assert result.info == {}

    def test_icc_profile_is_passed_to_png(self, tmp_path, monkeypatch):
        captured = {}

        def fake_save(self, target, **kwargs):
            captured.update(kwargs)
            Path(target).write_bytes(b"x")

        monkeypatch.setattr(Image.Image, "save", fake_save)

        save_image(
            Image.new("RGB", (2, 2)),
            tmp_path / "out.png",
            "PNG",
            icc_profile=b"profile",
        )

        assert captured["icc_profile"] == b"profile"

    def test_overlay_returning_none_is_ignored(self):
        class Overlay:
            text = "x"

            def apply_text(self, image):
                return None

        result = ImageManipulator(
            target_width=2, target_height=2, text_overlay=Overlay()
        ).render(Image.new("RGB", (2, 2)))

        assert result.size == (2, 2)


class TestPositioningRemaining:
    def test_aligned_window_does_not_move_twice(self):
        class Window:
            def update_idletasks(self):
                pass

            def winfo_ismapped(self):
                return True

            def winfo_rootx(self):
                return 10

            def winfo_rooty(self):
                return 20

            def geometry(self, value):
                raise AssertionError("must not move an already aligned window")

        positioning._align_client(Window(), 10, 20, 100, 50)


class TestUpdateCheckerRemaining:
    def test_missing_os_release_uses_tools(self):
        assert (
            update_checker.linux_package_kind(
                os_release="/definitely/missing", which=lambda name: None
            )
            == "deb"
        )

    def test_non_dict_assets_are_ignored(self):
        assert update_checker._https_assets([None, 5, {"name": "x"}], "linux") == []

    def test_non_list_assets_are_ignored(self):
        assert update_checker._https_assets(None, "linux") == []

    def test_linux_asset_falls_back_to_the_first_match(self):
        matches = [("image-linux.txt", "https://example/1")]
        assert update_checker._pick_linux_asset(matches, "deb") is None
        assert (
            update_checker.pick_download_url(
                [{"name": "image-linux.txt", "browser_download_url": "https://x/1"}],
                "linux",
                package_kind="deb",
            )
            == "https://x/1"
        )

    def test_windows_and_macos_asset_fallbacks(self):
        windows = [("image-windows.zip", "https://x/w")]
        macos = [("image-macos.zip", "https://x/m")]
        assert update_checker._pick_windows_asset(windows) is None
        assert update_checker._pick_macos_asset(macos) is None
        assert (
            update_checker.pick_download_url(
                [{"name": "image-windows.zip", "browser_download_url": "https://x/w"}],
                "win32",
            )
            == "https://x/w"
        )
        assert (
            update_checker.pick_download_url(
                [{"name": "image-macos.zip", "browser_download_url": "https://x/m"}],
                "darwin",
            )
            == "https://x/m"
        )

    def test_unknown_platform_key_uses_the_first_match(self, monkeypatch):
        monkeypatch.setattr(
            update_checker, "platform_asset_key", lambda platform: "other"
        )
        assert (
            update_checker.pick_download_url(
                [{"name": "other.bin", "browser_download_url": "https://x/o"}],
                "other",
            )
            == "https://x/o"
        )

    def test_missing_content_type_header_is_tolerated(self, monkeypatch):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def geturl(self):
                return "https://api.github.com/"

            def read(self, size):
                return b'{"tag_name": "v9.0.0"}'

        monkeypatch.setattr(
            update_checker.urllib.request,
            "urlopen",
            lambda request, timeout=None: Response(),
        )

        assert update_checker.fetch_latest_release()["tag_name"] == "v9.0.0"


class TestTextOverlayRemaining:
    def test_chooser_handles_a_missing_candidate_file(self, tmp_path):
        missing = tmp_path / "missing.ttf"

        assert text_overlay._choose_platform_font(
            [("Family", missing)], "Family", "Regular"
        ) == [missing]

    def test_chooser_skips_condensed_faces(self, tmp_path):
        condensed = tmp_path / "Segoe UI Condensed.ttf"
        condensed.write_bytes(b"font")
        files = [("Segoe UI Condensed (TrueType)", condensed)]

        assert text_overlay._choose_platform_font(files, "Segoe UI", "Regular") == []

        allowed = text_overlay._choose_platform_font(
            files, "Segoe UI Condensed", "Regular"
        )
        assert allowed == [condensed]

    def test_windows_registry_import_error(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "winreg", None)

        assert text_overlay._windows_font_files() == []

    def test_windows_registry_discovery(self, monkeypatch, tmp_path):
        font_dir = tmp_path / "Fonts"
        font_dir.mkdir()
        font_file = font_dir / "segoeui.ttf"
        font_file.write_bytes(b"font")
        user_dir = tmp_path / "user"
        user_dir.mkdir()
        (user_dir / "custom.ttf").write_bytes(b"font")

        class FakeKey:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        absolute = font_dir / "absolute.ttf"
        absolute.write_bytes(b"font")
        values = [
            ("Segoe UI (TrueType)", "segoeui.ttf"),
            ("Segoe UI Readme (TrueType)", "readme.txt"),
            ("Segoe UI Absolute (TrueType)", str(absolute)),
            ("Segoe UI Bold (TrueType)", "missing.ttf"),
        ]

        class FakeWinreg(types.ModuleType):
            HKEY_LOCAL_MACHINE = object()
            HKEY_CURRENT_USER = object()

            def OpenKey(self, hive, name):
                return FakeKey()

            def EnumValue(self, key, index):
                if index >= len(values):
                    raise OSError("end")
                name, value = values[index]
                return name, value, 1

        fake_winreg = FakeWinreg("winreg")
        monkeypatch.setitem(sys.modules, "winreg", fake_winreg)
        user_fonts = tmp_path.parent / "Microsoft" / "Windows" / "Fonts"
        user_fonts.mkdir(parents=True)
        (user_fonts / "user.ttf").write_bytes(b"font")
        monkeypatch.setenv("WINDIR", str(tmp_path))
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path.parent))

        entries = text_overlay._windows_font_files()

        assert ("Segoe UI (TrueType)", font_file) in entries
        assert ("Segoe UI Absolute (TrueType)", absolute) in entries
        assert ("user", user_fonts / "user.ttf") in entries

    def test_windows_registry_open_failure_is_ignored(self, monkeypatch):
        class FakeWinreg(types.ModuleType):
            HKEY_LOCAL_MACHINE = object()
            HKEY_CURRENT_USER = object()

            def OpenKey(self, hive, name):
                raise OSError("registry")

        monkeypatch.setitem(sys.modules, "winreg", FakeWinreg("winreg"))

        assert text_overlay._windows_font_files() == []

    def test_macos_font_directories_are_returned(self):
        directories = text_overlay._macos_font_directories()
        assert directories
        assert all(isinstance(path, Path) for path in directories)

    def test_macos_font_discovery(self, monkeypatch, tmp_path):
        font_dir = tmp_path / "Fonts"
        font_dir.mkdir()
        font_file = font_dir / "HelveticaNeue.ttf"
        font_file.write_bytes(b"font")

        monkeypatch.setattr(
            text_overlay, "_macos_font_directories", lambda: (font_dir,)
        )

        assert text_overlay._macos_font_files() == [("HelveticaNeue", font_file)]

    def test_missing_path_is_skipped_and_next_candidate_wins(
        self, tmp_path, monkeypatch
    ):
        import subprocess

        missing = tmp_path / "missing.ttf"
        present = tmp_path / "present.ttf"
        present.write_bytes(b"font")

        monkeypatch.setattr(text_overlay, "_platform_font_files", lambda: [])
        monkeypatch.setattr(
            subprocess,
            "run",
            lambda *a, **k: SimpleNamespace(
                stdout=f"{missing}\tFamily\n{present}\tFamily\n",
                returncode=0,
            ),
        )
        text_overlay._FONT_CANDIDATE_CACHE.clear()

        assert TextOverlay._fontconfig_candidates("Family", "Regular") == [str(present)]

    def test_system_font_success_by_family_and_path(self, monkeypatch):
        sentinel = object()
        overlay = TextOverlay(font_family="Family", font_style="Bold", font_size=20)
        text_overlay._WARNED_UNRESOLVED_FAMILIES.clear()

        monkeypatch.setattr(
            TextOverlay,
            "_try_load_font",
            staticmethod(lambda name, size, **kwargs: sentinel),
        )
        assert overlay._load_system_font(20) is sentinel

        text_overlay._FONT_PATH_CACHE.clear()
        monkeypatch.setattr(
            TextOverlay,
            "_try_load_font",
            staticmethod(
                lambda name, size, **kwargs: (
                    sentinel if str(name) == "/tmp/font.ttf" else None
                )
            ),
        )
        monkeypatch.setattr(
            TextOverlay,
            "_fontconfig_candidates",
            staticmethod(lambda family, style: ["/tmp/font.ttf"]),
        )
        assert overlay._load_system_font(20) is sentinel

    def test_fontconfig_path_continues_after_a_failed_load(self, monkeypatch):
        sentinel = object()
        overlay = TextOverlay(font_family="Family", font_style="Regular", font_size=20)
        monkeypatch.setattr(
            TextOverlay,
            "_try_load_font",
            staticmethod(
                lambda name, size, **kwargs: (
                    sentinel if str(name) == "/tmp/second.ttf" else None
                )
            ),
        )
        monkeypatch.setattr(
            TextOverlay,
            "_fontconfig_candidates",
            staticmethod(lambda family, style: ["/tmp/first.ttf", "/tmp/second.ttf"]),
        )

        assert overlay._load_system_font(20) is sentinel

    def test_custom_font_and_system_font_candidates_are_yielded(
        self, monkeypatch, tmp_path
    ):
        custom = tmp_path / "custom.ttf"
        custom.write_bytes(b"font")
        sentinel = object()
        overlay = TextOverlay(font_path=str(custom), font_size=20)

        monkeypatch.setattr(
            ImageFont, "truetype", lambda name, size, **kwargs: sentinel
        )
        monkeypatch.setattr(
            TextOverlay, "_load_system_font", lambda self, size: sentinel
        )

        candidates = list(overlay._font_candidates(20))

        assert candidates[0] is sentinel
        assert candidates[1] is sentinel

    def test_get_font_falls_back_when_the_chain_is_empty(self, monkeypatch):
        overlay = TextOverlay(font_size=20)
        monkeypatch.setattr(overlay, "_font_candidates", lambda size: iter(()))

        assert overlay.get_font(20) is not None

    def test_style_flags_fall_back_for_unknown_tokens(self):
        overlay = TextOverlay(font_style="Bold Custom")

        assert overlay._get_style_flags() == (True, False)

    def test_stroke_width_is_zero_for_normal_text(self):
        assert TextOverlay(font_size=20)._get_stroke_width(20, False) == 0
        assert TextOverlay(font_size=20)._get_stroke_width(20, True) >= 1

    def test_unknown_position_stays_at_origin(self):
        overlay = TextOverlay(position="unknown")

        assert overlay.calculate_position(100, 50, 10, 10) == (0, 0)

    def test_non_matching_fontconfig_path_is_skipped(self, tmp_path, monkeypatch):
        import subprocess

        text_overlay._FONT_CANDIDATE_CACHE.clear()
        monkeypatch.setattr(
            text_overlay,
            "_platform_font_files",
            lambda: [],
        )
        monkeypatch.setattr(
            subprocess,
            "run",
            lambda *a, **k: SimpleNamespace(
                stdout=f"{tmp_path / 'missing.ttf'}\tMissing\n",
                returncode=0,
            ),
        )

        assert TextOverlay._fontconfig_candidates("Missing", "Regular") == []

    def test_font_path_cache_hits_and_unresolved_families(self, monkeypatch):
        text_overlay._FONT_PATH_CACHE.clear()
        fake_font = SimpleNamespace(path="/tmp/cached.ttf")
        monkeypatch.setattr(
            TextOverlay,
            "_try_load_font",
            staticmethod(lambda name, size, **kwargs: fake_font),
        )
        overlay = TextOverlay(font_family="Cached Family", font_size=20)

        assert overlay._load_system_font(20) is fake_font
        assert overlay._load_system_font(20) is fake_font
        assert (
            text_overlay._FONT_PATH_CACHE[("Cached Family", "Normal")]
            == "/tmp/cached.ttf"
        )

        text_overlay._FONT_PATH_CACHE.clear()
        monkeypatch.setattr(
            TextOverlay,
            "_try_load_font",
            staticmethod(lambda name, size, **kwargs: None),
        )
        monkeypatch.setattr(
            TextOverlay,
            "_fontconfig_candidates",
            staticmethod(lambda family, style: []),
        )
        missing = TextOverlay(font_family="Missing Cached Family", font_size=20)

        assert missing._load_system_font(20) is None
        assert missing._load_system_font(20) is None
        assert (
            text_overlay._FONT_PATH_CACHE[("Missing Cached Family", "Normal")] is None
        )

    def test_stale_cached_path_is_dropped(self, monkeypatch):
        text_overlay._FONT_PATH_CACHE.clear()
        text_overlay._FONT_PATH_CACHE[("Stale Family", "Normal")] = "/tmp/stale.ttf"
        fallback = SimpleNamespace(path="/tmp/fresh.ttf")
        monkeypatch.setattr(
            TextOverlay,
            "_try_load_font",
            staticmethod(
                lambda name, size, **kwargs: (
                    None if name == "/tmp/stale.ttf" else fallback
                )
            ),
        )
        overlay = TextOverlay(font_family="Stale Family", font_size=20)

        assert overlay._load_system_font(20) is fallback
        assert (
            text_overlay._FONT_PATH_CACHE[("Stale Family", "Normal")]
            == "/tmp/fresh.ttf"
        )

    def test_already_warned_family_skips_the_warning(self, monkeypatch):
        text_overlay._FONT_PATH_CACHE.clear()
        text_overlay._WARNED_UNRESOLVED_FAMILIES.add("Warned Family")
        monkeypatch.setattr(
            TextOverlay,
            "_try_load_font",
            staticmethod(lambda name, size, **kwargs: None),
        )
        monkeypatch.setattr(
            TextOverlay,
            "_fontconfig_candidates",
            staticmethod(lambda family, style: []),
        )
        overlay = TextOverlay(font_family="Warned Family", font_size=20)

        assert overlay._load_system_font(20) is None


class TestDialogsRemaining:
    def test_abstract_dialog_content_is_not_implemented(self):
        import image_manipulator.dialogs as dialogs

        dialog = dialogs._ModalDialog.__new__(dialogs._ModalDialog)

        with pytest.raises(NotImplementedError):
            dialog._create_content()
