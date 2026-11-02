"""Tests for Application configuration."""

from image_manipulator.config import AppConfig, config


class TestPresets:
    """Tests for preset resolution."""

    def test_known_preset(self):
        assert config.get_preset_dimensions("1920x1080") == (1920, 1080)

    def test_unknown_preset(self):
        assert config.get_preset_dimensions("nope") == (0, 0)

    def test_custom_is_zero(self):
        assert config.get_preset_dimensions("Custom") == (0, 0)


class TestDefaults:
    """Tests for shared defaults."""

    def test_supported_extensions_include_webp(self):
        assert ".webp" in config.valid_extensions

    def test_output_formats_match_enum(self):
        assert set(config.output_formats) == {"JPEG", "PNG", "WEBP", "BMP"}

    def test_default_output_dir(self):
        assert config.default_output_dir == "processed_images"

    def test_portrait_rotation_is_off_by_default(self):
        assert config.default_rotate_portrait_to_landscape is False

    def test_config_is_an_appconfig(self):
        assert isinstance(AppConfig(), AppConfig)
