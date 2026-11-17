"""Tests for the pure resizing logic."""

import pytest
from PIL import Image

from image_manipulator.resize import (
    OutputFormat,
    calculate_dimensions,
    resize_image,
)


class TestOutputFormat:
    """Tests for OutputFormat."""

    def test_extensions(self):
        assert OutputFormat.JPEG.extension == "jpg"
        assert OutputFormat.PNG.extension == "png"
        assert OutputFormat.WEBP.extension == "webp"
        assert OutputFormat.BMP.extension == "bmp"

    def test_from_name_known(self):
        assert OutputFormat.from_name("PNG") is OutputFormat.PNG

    def test_from_name_unknown_falls_back(self):
        assert OutputFormat.from_name("GIF") is OutputFormat.JPEG


class TestCalculateDimensions:
    """Tests for aspect-ratio aware dimension calculation."""

    def test_fits_inside_target_box(self):
        assert calculate_dimensions(400, 200, 200, 200) == (200, 100)

    def test_landscape_target_limits_width(self):
        assert calculate_dimensions(100, 300, 400, 300) == (100, 300)

    def test_portrait_target_limits_height(self):
        assert calculate_dimensions(300, 100, 100, 400) == (100, 33)

    def test_without_aspect_ratio_uses_target(self):
        assert calculate_dimensions(400, 200, 150, 150, maintain_aspect=False) == (
            150,
            150,
        )

    def test_upscales_when_needed(self):
        assert calculate_dimensions(100, 50, 400, 400) == (400, 200)

    @pytest.mark.parametrize(
        "values",
        [(0, 100, 100, 100), (100, 0, 100, 100), (100, 100, 0, 100), (100, 100, 100, 0)],
    )
    def test_rejects_non_positive_values(self, values):
        with pytest.raises(ValueError):
            calculate_dimensions(*values)


class TestResizeImage:
    """Tests for resize_image."""

    def test_result_size_and_source_untouched(self):
        image = Image.new("RGB", (400, 200), "red")
        result = resize_image(image, 200, 200)

        assert result.size == (200, 100)
        assert image.size == (400, 200)

    def test_same_size_returns_a_copy(self):
        image = Image.new("RGB", (100, 100), "red")
        result = resize_image(image, 100, 100)

        assert result.size == (100, 100)
        assert result is not image
