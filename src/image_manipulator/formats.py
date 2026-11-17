"""One registry for image format capabilities and filename rules."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ImageFormat:
    """Everything the pipeline needs to know about one image format."""

    pillow_name: str
    suffixes: tuple[str, ...]
    output_extension: str | None
    supports_icc: bool
    supports_alpha: bool
    is_lossy: bool


FORMATS: tuple[ImageFormat, ...] = (
    ImageFormat("JPEG", (".jpg", ".jpeg"), "jpg", True, False, True),
    ImageFormat("PNG", (".png",), "png", True, True, False),
    ImageFormat("WEBP", (".webp",), "webp", True, True, True),
    ImageFormat("BMP", (".bmp",), "bmp", False, False, False),
    ImageFormat("GIF", (".gif",), None, False, True, False),
    ImageFormat("TIFF", (".tif", ".tiff"), None, True, True, False),
)

FORMAT_BY_NAME: dict[str, ImageFormat] = {
    image_format.pillow_name: image_format for image_format in FORMATS
}
FORMAT_BY_SUFFIX: dict[str, ImageFormat] = {
    suffix: image_format for image_format in FORMATS for suffix in image_format.suffixes
}
SUPPORTED_INPUT_SUFFIXES: tuple[str, ...] = tuple(FORMAT_BY_SUFFIX)
OUTPUT_FORMATS: tuple[str, ...] = tuple(
    image_format.pillow_name
    for image_format in FORMATS
    if image_format.output_extension is not None
)


def format_for_suffix(suffix: str) -> ImageFormat | None:
    """Return the format for a file suffix, case-insensitively."""
    return FORMAT_BY_SUFFIX.get(suffix.lower())


def format_for_name(name: str) -> ImageFormat | None:
    """Return the format for a Pillow format name."""
    return FORMAT_BY_NAME.get(name)
