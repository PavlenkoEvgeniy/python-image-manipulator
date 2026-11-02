"""Tests for the text overlay logic."""

from PIL import Image

from image_manipulator.config import config
from image_manipulator.text_overlay import TextOverlay


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
