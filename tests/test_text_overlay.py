"""Tests for the text overlay logic."""

import subprocess
from types import SimpleNamespace

import pytest
from PIL import Image, ImageDraw

from image_manipulator.config import config
from image_manipulator.text_overlay import (
    TextOverlay,
    _choose_platform_font,
    _normalize_font_text,
)


def _sample_image():
    return Image.new("RGB", (200, 100), "red")


class TestApplyText:
    """Tests for drawing text onto an image."""

    def test_returns_new_image_with_same_size(self):
        overlay = TextOverlay(text="Hi", color="#FFFFFF", font_size=20)
        image = _sample_image()

        result = overlay.apply_text(image)

        assert result is not None
        assert result.size == image.size
        assert result is not image
        assert result.tobytes() != image.tobytes()

    def test_draws_visible_light_pixels(self):
        overlay = TextOverlay(
            text="Hi",
            color="#FFFFFF",
            font_size=20,
            position="top left",
            offset_up=0,
            offset_left=0,
        )

        result = overlay.apply_text(_sample_image())

        colors = result.getcolors(maxcolors=result.width * result.height) or []
        assert any(r > 200 and g > 200 and b > 200 for _, (r, g, b) in colors)

    def test_empty_text_returns_none(self):
        overlay = TextOverlay(text="", color="#FFFFFF", font_size=20)
        assert overlay.apply_text(_sample_image()) is None

    def test_italic_style_still_draws(self):
        overlay = TextOverlay(
            text="Hi",
            color="#FFFFFF",
            font_size=20,
            font_style="Italic",
        )
        result = overlay.apply_text(_sample_image())

        assert result is not None
        assert result.size == (200, 100)
        assert result.tobytes() != _sample_image().tobytes()

    @pytest.mark.parametrize(
        "position", ["top left", "top right", "bottom left", "bottom right", "center"]
    )
    def test_text_is_visible_at_every_position(self, position):
        overlay = TextOverlay(
            text="Wgj",
            color="#FFFFFF",
            font_size=30,
            position=position,
            offset_up=5,
            offset_left=5,
        )

        result = overlay.apply_text(Image.new("RGB", (300, 120), "black"))

        assert result is not None
        light = sum(
            count
            for count, (red, green, blue) in result.getcolors(maxcolors=300 * 120)
            if red > 200 and green > 200 and blue > 200
        )
        assert light > 0

    def test_dots_at_bottom_right_land_inside_the_image(self):
        overlay = TextOverlay(
            text="....",
            color="#FFFFFF",
            font_size=40,
            position="bottom right",
            offset_up=20,
            offset_left=20,
        )

        result = overlay.apply_text(Image.new("RGB", (300, 120), "black"))

        assert result is not None
        light = sum(
            count
            for count, (red, green, blue) in result.getcolors(maxcolors=300 * 120)
            if red > 200 and green > 200 and blue > 200
        )
        assert light > 0

    def test_hex_color_is_used(self):
        overlay = TextOverlay(
            text="X",
            color="#00FF00",
            font_size=40,
            position="top left",
            offset_up=0,
            offset_left=0,
        )
        result = overlay.apply_text(_sample_image())

        colors = result.getcolors(maxcolors=result.width * result.height) or []
        assert any(g > 200 and r < 100 and b < 100 for _, (r, g, b) in colors)


class TestPositioning:
    """Tests for text bounding box placement."""

    def test_top_left(self):
        overlay = TextOverlay(position="top left", offset_up=7, offset_left=9)
        assert overlay.calculate_position(100, 50, 20, 10) == (9, 7)

    def test_top_right(self):
        overlay = TextOverlay(position="top right", offset_up=7, offset_left=9)
        assert overlay.calculate_position(100, 50, 20, 10) == (71, 7)

    def test_bottom_left(self):
        overlay = TextOverlay(position="bottom left", offset_up=7, offset_left=9)
        assert overlay.calculate_position(100, 50, 20, 10) == (9, 33)

    def test_bottom_right(self):
        overlay = TextOverlay(position="bottom right", offset_up=7, offset_left=9)
        assert overlay.calculate_position(100, 50, 20, 10) == (71, 33)

    def test_center(self):
        overlay = TextOverlay(position="center")
        assert overlay.calculate_position(100, 50, 20, 10) == (40, 20)


class TestSerialization:
    """Tests for from_dict / to_dict."""

    def test_round_trip(self):
        settings = {
            "text": "Hello",
            "color": "#123456",
            "font_family": "DejaVu Sans",
            "font_path": None,
            "font_size": 33,
            "font_style": "Bold",
            "position": "center",
            "offset_up": 4,
            "offset_left": 8,
        }

        assert TextOverlay.from_dict(settings).to_dict() == settings

    def test_defaults(self):
        overlay = TextOverlay.from_dict({})

        assert overlay.color == config.default_color
        assert overlay.font_size == config.default_font_size
        assert overlay.position == config.default_position


class TestFontResolution:
    """Tests for the fallback font chain."""

    def test_get_font_for_text_returns_renderable_font(self):
        overlay = TextOverlay(font_size=20)
        font = overlay.get_font_for_text(20, "Hello")

        assert overlay._renders_text(font, "Hello") is True

    def test_whitespace_counts_as_renderable(self):
        overlay = TextOverlay(font_size=20)
        font = overlay.get_font(20)

        assert overlay._renders_text(font, "   ") is True

    def test_missing_glyphs_are_rejected_as_tofu(self):
        overlay = TextOverlay(font_size=20)
        font = overlay.get_font(20)
        try:
            font.getmask("\ue000")
        except Exception as exc:
            pytest.skip(f"this font cannot be probed: {exc}")

        assert overlay._renders_text(font, "\ue000") is False
        assert overlay._renders_text(font, "Hello") is True


class TestFontconfigFaces:
    """fc-match gives the requested style without condensed look-alikes."""

    def test_exact_style_comes_first_and_foreign_families_are_ignored(
        self, tmp_path, monkeypatch
    ):
        oblique = tmp_path / "oblique.ttf"
        foreign = tmp_path / "foreign.ttf"
        for path in (oblique, foreign):
            path.write_bytes(b"font")

        def fake_run(args, **kwargs):
            query = args[-1]
            if "slant=italic" in query:
                output = f"{oblique}\tDejaVu Sans\n"
            else:
                output = (
                    f"{oblique}\tDejaVu Sans\n"
                    f"{foreign}\tOther Family\n"
                )
            return SimpleNamespace(stdout=output, returncode=0)

        monkeypatch.setattr(subprocess, "run", fake_run)

        candidates = TextOverlay._fontconfig_candidates("DejaVu Sans", "Italic")

        assert candidates == [str(oblique)]

    def test_condensed_variants_are_ignored(self, tmp_path, monkeypatch):
        regular = tmp_path / "regular.ttf"
        condensed = tmp_path / "condensed.ttf"
        for path in (regular, condensed):
            path.write_bytes(b"font")

        def fake_run(args, **kwargs):
            query = args[-1]
            if "slant=roman" in query:
                output = f"{regular}\tDejaVu Sans\n"
            else:
                output = f"{condensed}\tDejaVu Sans,DejaVu Sans Condensed\n"
            return SimpleNamespace(stdout=output, returncode=0)

        monkeypatch.setattr(subprocess, "run", fake_run)

        candidates = TextOverlay._fontconfig_candidates("DejaVu Sans", "Regular")

        assert candidates == [str(regular)]

    def test_missing_fc_match_returns_no_candidates(self, monkeypatch):
        def missing(*args, **kwargs):
            raise FileNotFoundError("fc-match")

        monkeypatch.setattr(subprocess, "run", missing)

        assert TextOverlay._fontconfig_candidates("DejaVu Sans", "Regular") == []


class TestPlatformFontResolution:
    """Windows/macOS font files are matched by family and style."""

    @staticmethod
    def _files(tmp_path):
        names = {
            "regular": "Segoe UI (TrueType)",
            "bold": "Segoe UI Bold (TrueType)",
            "italic": "Segoe UI Italic (TrueType)",
            "bold_italic": "Segoe UI Bold Italic (TrueType)",
            "condensed": "Segoe UI Condensed (TrueType)",
            "other": "Segoe UI Symbol (TrueType)",
        }
        files = []
        for key, display in names.items():
            path = tmp_path / f"{key}.ttf"
            path.write_bytes(b"font")
            files.append((display, path))
        return files

    def test_normalizes_registry_labels(self):
        assert _normalize_font_text("Segoe UI Bold (TrueType)") == "segoeuibold"
        assert _normalize_font_text("HelveticaNeue-Bold.otf") == "helveticaneuebold"

    @pytest.mark.parametrize(
        ("style", "expected"),
        [
            ("Regular", "regular"),
            ("Bold", "bold"),
            ("Italic", "italic"),
            ("Bold Italic", "bold_italic"),
        ],
    )
    def test_selects_the_requested_face(self, tmp_path, style, expected):
        files = self._files(tmp_path)

        chosen = _choose_platform_font(files, "Segoe UI", style)

        assert chosen == [tmp_path / f"{expected}.ttf"]

    def test_condensed_and_unrelated_faces_are_ignored(self, tmp_path):
        files = self._files(tmp_path)

        chosen = _choose_platform_font(files, "Segoe UI", "Regular")

        assert chosen == [tmp_path / "regular.ttf"]
        assert all("condensed" not in path.name for path in chosen)
        assert all("other" not in path.name for path in chosen)

    def test_unknown_family_has_no_platform_match(self, tmp_path):
        files = self._files(tmp_path)

        assert _choose_platform_font(files, "Missing Family", "Regular") == []


class TestMeasurementFallback:
    """Pillow 10+ has no draw.textsize(), so bbox failures use font.getbbox()."""

    def test_falls_back_to_the_font_bounding_box(self, monkeypatch):
        overlay = TextOverlay(font_size=20)
        font = overlay.get_font(20)
        draw = ImageDraw.Draw(Image.new("RGB", (50, 50)))

        def fail_textbbox(*args, **kwargs):
            raise RuntimeError("textbbox is unavailable")

        monkeypatch.setattr(ImageDraw.ImageDraw, "textbbox", fail_textbbox)

        width, height, offset_x, offset_y = overlay.get_text_size(draw, "Hi", font)

        assert width > 0
        assert height > 0
        assert isinstance(offset_x, int)
        assert isinstance(offset_y, int)
