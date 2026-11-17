"""Tests for Application configuration."""

from pathlib import Path

from image_manipulator import __version__
from image_manipulator.config import AppConfig, config

REPO_ROOT = Path(__file__).resolve().parent.parent


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

    def test_version_has_one_source(self):
        pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

        assert config.version == __version__
        assert 'dynamic = ["version"]' in pyproject
        assert 'version = {attr = "image_manipulator.__version__"}' in pyproject
        assert "- **Version:** [latest release]" in readme


class TestDefaultOutputDirectory:
    """Results land in a visible folder on the user's Desktop."""

    def test_desktop_folder_is_preferred(self, tmp_path):
        desktop = tmp_path / "Desktop"
        desktop.mkdir()

        result = config.default_output_directory(home=str(tmp_path))

        assert result == str(desktop / "processed_images")

    def test_falls_back_to_home_without_desktop(self, tmp_path):
        result = config.default_output_directory(home=str(tmp_path))

        assert result == str(tmp_path / "processed_images")
