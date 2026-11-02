"""Tests for the bundled application icon."""

from pathlib import Path

from PIL import Image

from image_manipulator.icon import get_icon_path, load_icon_image

REPO_ROOT = Path(__file__).resolve().parent.parent
ASSETS = REPO_ROOT / "assets"


class TestPackagedIcon:
    """The runtime icon ships with the package."""

    def test_icon_file_exists(self):
        assert Path(get_icon_path()).is_file()

    def test_loads_as_rgba(self):
        image = load_icon_image()

        assert image.mode == "RGBA"
        assert image.width == image.height

    def test_resizes_to_requested_square(self):
        image = load_icon_image(64)

        assert image.size == (64, 64)

    def test_default_size_is_the_packaged_icon(self):
        assert load_icon_image().size == (256, 256)


class TestPlatformAssets:
    """The platform-specific build icons exist and have valid signatures."""

    def test_png(self):
        data = (ASSETS / "icon.png").read_bytes()
        assert data[:8] == b"\x89PNG\r\n\x1a\n"

    def test_ico_contains_small_and_large_sizes(self):
        with Image.open(ASSETS / "icon.ico") as icon:
            sizes = icon.ico.sizes()

        assert (16, 16) in sizes
        assert (256, 256) in sizes

    def test_icns_signature(self):
        assert (ASSETS / "icon.icns").read_bytes()[:4] == b"icns"
