"""Tests for the image format registry."""

from image_manipulator import formats
from image_manipulator.config import config


class TestRegistry:
    def test_names_and_suffixes_are_unique(self):
        names = [image_format.pillow_name for image_format in formats.FORMATS]
        suffixes = [
            suffix
            for image_format in formats.FORMATS
            for suffix in image_format.suffixes
        ]

        assert len(names) == len(set(names))
        assert len(suffixes) == len(set(suffixes))

    def test_output_formats_are_derived(self):
        assert formats.OUTPUT_FORMATS == ("JPEG", "PNG", "WEBP", "BMP")
        assert config.output_formats == formats.OUTPUT_FORMATS
        assert config.valid_extensions == formats.SUPPORTED_INPUT_SUFFIXES

    def test_suffix_lookup_is_case_insensitive(self):
        assert formats.format_for_suffix(".JPG").pillow_name == "JPEG"
        assert formats.format_for_suffix(".tif").pillow_name == "TIFF"
        assert formats.format_for_suffix(".unknown") is None

    def test_name_lookup(self):
        assert formats.format_for_name("GIF").supports_alpha is True
        assert formats.format_for_name("BMP").supports_icc is False
        assert formats.format_for_name("WEBP").is_lossy is True
        assert formats.format_for_name("unknown") is None

    def test_only_known_formats_can_be_output(self):
        for image_format in formats.FORMATS:
            if image_format.output_extension is not None:
                assert image_format.pillow_name in formats.OUTPUT_FORMATS
            else:
                assert image_format.pillow_name not in formats.OUTPUT_FORMATS
