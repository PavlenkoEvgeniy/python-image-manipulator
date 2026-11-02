"""Tests for the resize → text → save pipeline."""

from pathlib import Path

from PIL import Image

from image_manipulator.pipeline import ImageManipulator, load_image
from image_manipulator.resize import OutputFormat
from image_manipulator.text_overlay import TextOverlay


# EXIF orientation tag id
ORIENTATION_TAG = 0x0112


def _make_image(path, size=(400, 200), color="red"):
    Image.new("RGB", size, color).save(path)
    return Path(path)


class TestRender:
    """Tests for the in-memory pipeline."""

    def test_resizes_before_drawing_text(self):
        image = Image.new("RGB", (400, 200), "red")
        manipulator = ImageManipulator(
            target_width=200,
            target_height=100,
            text_overlay=TextOverlay(text="Hi", color="#FFFFFF", font_size=20),
        )

        result = manipulator.render(image)

        assert result.size == (200, 100)
        # Text is present on the resized result
        assert result.tobytes() != image.resize(
            (200, 100), Image.Resampling.LANCZOS
        ).tobytes()

    def test_without_text_only_resizes(self):
        image = Image.new("RGB", (400, 200), "red")
        manipulator = ImageManipulator(
            target_width=200,
            target_height=100,
            text_overlay=TextOverlay(text="   ", font_size=20),
        )

        result = manipulator.render(image)

        assert result.size == (200, 100)
        assert manipulator.has_text() is False

    def test_maintains_aspect_ratio(self):
        image = Image.new("RGB", (400, 200), "red")
        manipulator = ImageManipulator(target_width=200, target_height=200)

        assert manipulator.render(image).size == (200, 100)

    def test_can_ignore_aspect_ratio(self):
        image = Image.new("RGB", (400, 200), "red")
        manipulator = ImageManipulator(
            target_width=150,
            target_height=150,
            maintain_aspect=False,
        )

        assert manipulator.render(image).size == (150, 150)


class TestProcessPath:
    """Tests for loading from and saving to disk."""

    def test_writes_expected_filename_and_size(self, tmp_path):
        source = _make_image(tmp_path / "photo.png")
        output_dir = tmp_path / "out"
        manipulator = ImageManipulator(
            target_width=200,
            target_height=100,
            output_format=OutputFormat.JPEG,
            text_overlay=TextOverlay(text="Hi", color="#FFFFFF", font_size=20),
        )

        result = manipulator.process_path(source, output_dir)

        assert result.success is True
        assert result.output_path == output_dir / "photo_200x100_text.jpg"
        assert result.output_path.is_file()
        with Image.open(result.output_path) as saved:
            assert saved.size == (200, 100)

    def test_no_text_suffix_when_text_is_blank(self, tmp_path):
        source = _make_image(tmp_path / "photo.png")
        manipulator = ImageManipulator(
            target_width=200,
            target_height=100,
            output_format=OutputFormat.PNG,
            text_overlay=TextOverlay(text=" "),
        )

        result = manipulator.process_path(source, tmp_path / "out")

        assert result.output_path.name == "photo_200x100.png"

    def test_without_dimensions_suffix(self, tmp_path):
        source = _make_image(tmp_path / "photo.png")
        manipulator = ImageManipulator(
            target_width=200,
            target_height=100,
            output_format=OutputFormat.PNG,
            add_dimensions_to_filename=False,
            text_overlay=TextOverlay(text="Hi", font_size=20),
        )

        result = manipulator.process_path(source, tmp_path / "out")

        assert result.output_path.name == "photo_text.png"

    def test_overwrite_keeps_original_path_and_format(self, tmp_path):
        source = _make_image(tmp_path / "photo.png")
        manipulator = ImageManipulator(
            target_width=200,
            target_height=100,
            output_format=OutputFormat.JPEG,
        )

        result = manipulator.process_path(source, tmp_path / "unused", overwrite=True)

        assert result.success is True
        assert result.output_path == source
        with Image.open(source) as saved:
            assert saved.format == "PNG"
            assert saved.size == (200, 100)

    def test_missing_file_fails(self, tmp_path):
        manipulator = ImageManipulator(target_width=100, target_height=100)
        result = manipulator.process_path(tmp_path / "missing.png", tmp_path)

        assert result.success is False
        assert "not found" in result.error

    def test_unsupported_format_fails(self, tmp_path):
        source = tmp_path / "notes.txt"
        source.write_text("hello", encoding="utf-8")
        manipulator = ImageManipulator(target_width=100, target_height=100)

        result = manipulator.process_path(source, tmp_path)

        assert result.success is False
        assert "Unsupported" in result.error

    def test_does_not_overwrite_existing_results(self, tmp_path):
        source = _make_image(tmp_path / "photo.png")
        output_dir = tmp_path / "out"
        output_dir.mkdir()
        existing = output_dir / "photo_200x100_text.jpg"
        existing.write_bytes(b"previous result")

        manipulator = ImageManipulator(
            target_width=200,
            target_height=100,
            text_overlay=TextOverlay(text="Hi", font_size=20),
        )
        result = manipulator.process_path(source, output_dir)

        assert result.success is True
        assert result.output_path == output_dir / "photo_200x100_text_1.jpg"
        assert existing.read_bytes() == b"previous result"

    def test_output_directory_is_created(self, tmp_path):
        source = _make_image(tmp_path / "photo.png")
        nested = tmp_path / "a" / "b" / "c"
        manipulator = ImageManipulator(target_width=100, target_height=100)

        result = manipulator.process_path(source, nested)

        assert result.success is True
        assert nested.is_dir()

    def test_transparent_png_becomes_rgb_jpeg(self, tmp_path):
        source = tmp_path / "alpha.png"
        image = Image.new("RGBA", (100, 50), (0, 0, 0, 0))
        image.save(source)

        manipulator = ImageManipulator(
            target_width=100,
            target_height=50,
            output_format=OutputFormat.JPEG,
        )
        result = manipulator.process_path(source, tmp_path / "out")

        assert result.success is True
        with Image.open(result.output_path) as saved:
            assert saved.mode == "RGB"


class TestOrientation:
    """The display orientation must be baked into the output pixels."""

    def test_load_image_transposes_pixels(self, tmp_path):
        source = tmp_path / "sideways.jpg"
        image = Image.new("RGB", (400, 200), "red")
        exif = image.getexif()
        exif[ORIENTATION_TAG] = 6  # rotate 90° CW for display
        image.save(source, exif=exif)

        loaded, _ = load_image(source)

        assert loaded.size == (200, 400)

    def test_pipeline_uses_display_orientation(self, tmp_path):
        source = tmp_path / "sideways.jpg"
        image = Image.new("RGB", (400, 200), "red")
        exif = image.getexif()
        exif[ORIENTATION_TAG] = 6
        image.save(source, exif=exif)

        manipulator = ImageManipulator(
            target_width=1000,
            target_height=1000,
            output_format=OutputFormat.PNG,
        )
        result = manipulator.process_path(source, tmp_path / "out")

        assert result.success is True
        with Image.open(result.output_path) as saved:
            # Display orientation is portrait: 200x400 scaled by 2.5
            assert saved.size == (500, 1000)
