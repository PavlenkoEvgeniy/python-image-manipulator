"""Pure resizing logic: target dimensions and pixel resampling."""

from enum import Enum
from typing import Tuple

from PIL import Image

from .config import config


class OutputFormat(Enum):
    """Supported output image formats."""

    JPEG = "JPEG"
    PNG = "PNG"
    WEBP = "WEBP"
    BMP = "BMP"

    @property
    def extension(self) -> str:
        """File extension (without the dot) for this format."""
        return "jpg" if self.value == "JPEG" else self.value.lower()

    @classmethod
    def from_name(cls, name: str) -> "OutputFormat":
        """Resolve a format by its value, falling back to the default."""
        try:
            return cls(name)
        except ValueError:
            return cls(config.default_output_format)


def calculate_dimensions(
    original_width: int,
    original_height: int,
    target_width: int,
    target_height: int,
    maintain_aspect: bool = True,
) -> Tuple[int, int]:
    """Calculate the final pixel size of a resized image.

    With ``maintain_aspect`` the image is scaled to fit inside the target box
    without distortion; otherwise the target size is used as-is.

    Args:
        original_width: Source image width in pixels.
        original_height: Source image height in pixels.
        target_width: Requested width in pixels.
        target_height: Requested height in pixels.
        maintain_aspect: Whether to preserve the original proportions.

    Returns:
        Tuple of (width, height), each at least 1 pixel.

    Raises:
        ValueError: If any dimension is not positive.
    """
    for name, value in (
        ("original_width", original_width),
        ("original_height", original_height),
        ("target_width", target_width),
        ("target_height", target_height),
    ):
        if value <= 0:
            raise ValueError(f"{name} must be positive, got {value}")

    if not maintain_aspect:
        return target_width, target_height

    ratio = min(target_width / original_width, target_height / original_height)
    return max(1, int(original_width * ratio)), max(1, int(original_height * ratio))


def resize_image(
    image: Image.Image,
    target_width: int,
    target_height: int,
    maintain_aspect: bool = True,
) -> Image.Image:
    """Resize an image using high-quality Lanczos resampling.

    Args:
        image: Source PIL image.
        target_width: Requested width in pixels.
        target_height: Requested height in pixels.
        maintain_aspect: Whether to preserve the original proportions.

    Returns:
        A new resized image; the source image is never modified.
    """
    size = calculate_dimensions(
        image.width,
        image.height,
        target_width,
        target_height,
        maintain_aspect,
    )
    if size == image.size:
        return image.copy()
    return image.resize(size, Image.Resampling.LANCZOS)
