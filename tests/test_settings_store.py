"""Tests for Saved settings persistence."""

import json

from image_manipulator import settings_store
from image_manipulator.config import config


def _full_settings():
    settings = settings_store.default_settings()
    settings.update(
        {
            "width": 640,
            "height": 480,
            "maintain_aspect": False,
            "add_dimensions": False,
            "rotate_portrait": True,
            "output_format": "PNG",
            "jpeg_quality": 80,
            "text": "Hello",
            "color": "#123456",
            "font_family": "DejaVu Sans",
            "font_path": None,
            "font_size": 55,
            "font_style": "Bold",
            "position": "center",
            "offset_up": 5,
            "offset_left": 7,
            "output_dir": "/tmp/out",
            "overwrite": True,
        }
    )
    return settings


class TestRoundTrip:
    """Saving and loading a full snapshot."""

    def test_round_trip(self, tmp_path):
        path = str(tmp_path / "settings.json")
        settings = _full_settings()

        assert settings_store.save_settings(settings, path=path)
        assert settings_store.load_settings(path=path) == settings

    def test_file_is_versioned_json(self, tmp_path):
        path = tmp_path / "settings.json"
        settings_store.save_settings(_full_settings(), path=str(path))

        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["version"] == settings_store.SETTINGS_VERSION
        assert payload["settings"]["text"] == "Hello"


class TestValidation:
    """Invalid fields fall back to their own defaults."""

    def test_invalid_fields_fall_back(self):
        result = settings_store.validate_settings(
            {
                "width": "wide",
                "height": -5,
                "maintain_aspect": "yes",
                "add_dimensions": 1,
                "rotate_portrait": "yes",
                "output_format": "GIF",
                "jpeg_quality": 0,
                "text": 42,
                "color": "red",
                "font_family": 7,
                "font_path": 5,
                "font_size": 999,
                "font_style": "Heavy",
                "position": "middle",
                "offset_up": -3,
                "offset_left": "x",
                "output_dir": 9,
                "overwrite": "yes",
            }
        )

        assert result["width"] == config.default_width
        assert result["height"] == config.min_dimension
        assert result["maintain_aspect"] is config.default_maintain_aspect_ratio
        assert result["add_dimensions"] is config.default_add_dimensions_to_filename
        assert (
            result["rotate_portrait"]
            is config.default_rotate_portrait_to_landscape
        )
        assert result["output_format"] == config.default_output_format
        assert result["jpeg_quality"] == config.min_jpeg_quality
        assert result["text"] == config.default_text
        assert result["color"] == config.default_color
        assert result["font_family"] == config.default_font_family
        assert result["font_path"] is None
        assert result["font_size"] == config.max_font_size
        assert result["font_style"] == config.default_font_style
        assert result["position"] == config.default_position
        assert result["offset_up"] == 0
        assert result["offset_left"] == config.default_offset_left
        assert result["output_dir"] == ""
        assert result["overwrite"] is False

    def test_valid_values_survive(self):
        result = settings_store.validate_settings(
            {
                "width": 1920,
                "height": 1080,
                "output_format": "WEBP",
                "font_size": 24,
                "color": "#AABBCC",
            }
        )

        assert result["width"] == 1920
        assert result["height"] == 1080
        assert result["output_format"] == "WEBP"
        assert result["font_size"] == 24
        assert result["color"] == "#AABBCC"


class TestLoadFailureModes:
    """Corrupt or incompatible files fall back to defaults silently."""

    def test_missing_file(self, tmp_path):
        assert settings_store.load_settings(path=str(tmp_path / "nope.json")) is None

    def test_corrupt_json(self, tmp_path):
        path = tmp_path / "settings.json"
        path.write_text("{not json", encoding="utf-8")
        assert settings_store.load_settings(path=str(path)) is None

    def test_unsupported_version(self, tmp_path):
        path = tmp_path / "settings.json"
        path.write_text(json.dumps({"version": 999, "settings": {}}), encoding="utf-8")
        assert settings_store.load_settings(path=str(path)) is None

    def test_settings_not_an_object(self, tmp_path):
        path = tmp_path / "settings.json"
        path.write_text(json.dumps({"version": 1, "settings": []}), encoding="utf-8")
        assert settings_store.load_settings(path=str(path)) is None


class TestClear:
    """Reset settings removes the file."""

    def test_clear_existing_file(self, tmp_path):
        path = tmp_path / "settings.json"
        settings_store.save_settings(_full_settings(), path=str(path))

        assert settings_store.clear_settings(path=str(path)) is True
        assert not path.exists()

    def test_clear_missing_file_is_ok(self, tmp_path):
        assert settings_store.clear_settings(path=str(tmp_path / "nope.json")) is True
