"""Processing pipeline: load → resize → text overlay → save."""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

from PIL import Image, ImageOps

from .config import config
from .resize import OutputFormat, resize_image
from .text_overlay import TextOverlay

logger = logging.getLogger(__name__)

# Pillow output formats keyed by file suffix, used when overwriting originals.
_FORMAT_BY_SUFFIX = {
    ".jpg": "JPEG",
    ".jpeg": "JPEG",
    ".png": "PNG",
    ".webp": "WEBP",
    ".bmp": "BMP",
    ".tif": "TIFF",
    ".tiff": "TIFF",
    ".gif": "GIF",
}

# Formats that can carry an ICC profile in Pillow.
_ICC_FORMATS = {"JPEG", "PNG", "WEBP", "TIFF"}


@dataclass
class ProcessResult:
    """Result of processing a single image."""

    success: bool
    output_path: Optional[Path] = None
    error: Optional[str] = None


def _normalize_mode(image: Image.Image) -> Image.Image:
    """Convert exotic color modes to RGB or RGBA.

    Palette, grayscale-with-alpha, CMYK and 16-bit images either cannot be
    resized with Lanczos or cannot be drawn on with a hex color, so they are
    normalized before processing.
    """
    if image.mode in ("RGB", "RGBA"):
        return image
    has_alpha = image.mode in ("PA", "LA") or "transparency" in image.info
    if has_alpha:
        return image.convert("RGBA")
    return image.convert("RGB")


def load_image(path) -> Tuple[Image.Image, Optional[bytes]]:
    """Load an image with its display orientation baked into the pixels.

    Viewers display an image according to its EXIF Orientation tag, which may
    differ from how the pixels are stored. Transposing the pixels here means
    every later step — resizing, text placement, saving — works on what the
    user actually sees.

    Args:
        path: Path to the image file.

    Returns:
        Tuple of (normalized PIL image, ICC profile bytes or None).
    """
    with Image.open(path) as raw:
        original_mode = raw.mode
        icc_profile = raw.info.get("icc_profile")
        image = ImageOps.exif_transpose(raw)
        image.load()

    image = _normalize_mode(image)

    # A CMYK profile is meaningless after converting the pixels to RGB.
    if original_mode == "CMYK":
        icc_profile = None
    return image, icc_profile


def _flatten_to_rgb(image: Image.Image) -> Image.Image:
    """Flatten transparency onto a white background for JPEG/BMP output."""
    if image.mode == "RGB":
        return image
    if image.mode in ("RGBA", "LA", "PA", "P") or "transparency" in image.info:
        rgba = image.convert("RGBA")
        background = Image.new("RGB", rgba.size, (255, 255, 255))
        background.paste(rgba, mask=rgba.getchannel("A"))
        return background
    return image.convert("RGB")


def _prepare_for_save(image: Image.Image, pil_format: str) -> Image.Image:
    """Convert the image mode to one the target format supports."""
    if pil_format in ("JPEG", "BMP"):
        return _flatten_to_rgb(image)
    if pil_format == "GIF" and image.mode != "P":
        return image.convert("RGB").convert("P", palette=Image.Palette.ADAPTIVE)
    return image


def save_image(
    image: Image.Image,
    path,
    pil_format: str,
    jpeg_quality: int = 95,
    icc_profile: Optional[bytes] = None,
) -> None:
    """Save an image in the given Pillow format with format-aware options.

    Args:
        image: Image to save.
        path: Destination file path.
        pil_format: Pillow format name, e.g. "JPEG" or "PNG".
        jpeg_quality: Quality used for lossy formats (JPEG/WEBP), 1-100.
        icc_profile: ICC profile carried over from the original, if any.
    """
    prepared = _prepare_for_save(image, pil_format)

    kwargs = {}
    if pil_format == "JPEG":
        kwargs["quality"] = jpeg_quality
        kwargs["optimize"] = True
    elif pil_format == "PNG":
        kwargs["optimize"] = True
    elif pil_format == "WEBP":
        kwargs["quality"] = jpeg_quality
    if icc_profile and pil_format in _ICC_FORMATS:
        kwargs["icc_profile"] = icc_profile

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    prepared.save(path, format=pil_format, **kwargs)


class ImageManipulator:
    """Resizes images and draws text on the resized result.

    The order is fixed by design: the text is applied last, so the font size
    is expressed in pixels of the output image, not of the original.
    """

    SUPPORTED_INPUT_FORMATS = config.valid_extensions

    def __init__(
        self,
        target_width: int = config.default_width,
        target_height: int = config.default_height,
        maintain_aspect: bool = config.default_maintain_aspect_ratio,
        output_format: OutputFormat = OutputFormat.JPEG,
        jpeg_quality: int = config.default_jpeg_quality,
        add_dimensions_to_filename: bool = config.default_add_dimensions_to_filename,
        text_overlay: Optional[TextOverlay] = None,
    ):
        self.target_width = target_width
        self.target_height = target_height
        self.maintain_aspect = maintain_aspect
        self.output_format = output_format
        self.jpeg_quality = jpeg_quality
        self.add_dimensions_to_filename = add_dimensions_to_filename
        self.text_overlay = text_overlay

    def has_text(self) -> bool:
        """Whether a non-blank text overlay is configured."""
        return self.text_overlay is not None and bool(self.text_overlay.text.strip())

    def render(self, image: Image.Image) -> Image.Image:
        """Produce the final image: resize first, then draw text.

        Args:
            image: Source image.

        Returns:
            A new image; the source is never modified.
        """
        image = _normalize_mode(image)
        result = resize_image(
            image,
            self.target_width,
            self.target_height,
            self.maintain_aspect,
        )
        if self.has_text():
            overlaid = self.text_overlay.apply_text(result)
            if overlaid is not None:
                result = overlaid
        return result

    def resolve_output_path(
        self,
        input_path: Path,
        output_dir,
        rendered: Image.Image,
        overwrite: bool,
    ) -> Tuple[Path, str]:
        """Choose the destination path and Pillow format for a result.

        Args:
            input_path: Original file path.
            output_dir: Destination folder for new files.
            rendered: Final image (its size goes into the filename).
            overwrite: Whether the original file is replaced.

        Returns:
            Tuple of (output path, Pillow format name).
        """
        if overwrite:
            pil_format = _FORMAT_BY_SUFFIX.get(input_path.suffix.lower())
            if pil_format is not None:
                return input_path, pil_format
            logger.warning(
                f"Cannot overwrite {input_path.name}: unsupported output suffix. "
                "Saving to the output folder instead."
            )

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        parts = [input_path.stem]
        if self.add_dimensions_to_filename:
            parts.append(f"{rendered.width}x{rendered.height}")
        if self.has_text():
            parts.append("text")

        stem = "_".join(parts)
        extension = self.output_format.extension
        output_path = output_dir / f"{stem}.{extension}"

        # Never overwrite a previous result silently when writing to a folder.
        counter = 1
        while output_path.exists():
            output_path = output_dir / f"{stem}_{counter}.{extension}"
            counter += 1

        return output_path, self.output_format.value

    def process_path(
        self,
        input_path,
        output_dir,
        overwrite: bool = False,
    ) -> ProcessResult:
        """Load, resize, overlay text and save one image.

        Args:
            input_path: Path to the source image.
            output_dir: Destination folder when not overwriting.
            overwrite: Replace the original file instead of writing a new one.

        Returns:
            ProcessResult describing success, the output path or an error.
        """
        path = Path(input_path)

        if not path.is_file():
            return ProcessResult(False, error=f"Input file not found: {path}")
        if path.suffix.lower() not in self.SUPPORTED_INPUT_FORMATS:
            return ProcessResult(
                False, error=f"Unsupported image format: {path.suffix or path.name}"
            )

        try:
            image, icc_profile = load_image(path)
            rendered = self.render(image)
            output_path, pil_format = self.resolve_output_path(
                path, output_dir, rendered, overwrite
            )
            save_image(
                rendered,
                output_path,
                pil_format,
                jpeg_quality=self.jpeg_quality,
                icc_profile=icc_profile,
            )
            logger.info(f"Processed {path.name} -> {output_path}")
            return ProcessResult(True, output_path=output_path)
        except Exception as e:
            logger.error(f"Failed to process {path.name}: {e}")
            return ProcessResult(False, error=f"Failed to process {path.name}: {e}")
