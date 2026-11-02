"""Application icon loading for source and frozen builds."""

import os
import sys
from typing import Optional

from PIL import Image

ICON_FILENAME = "icon.png"


def get_icon_path() -> str:
    """Absolute path to the bundled application icon."""
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
        return os.path.join(base, "image_manipulator", ICON_FILENAME)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), ICON_FILENAME)


def load_icon_image(size: Optional[int] = None) -> Image.Image:
    """Load the icon as an RGBA image, optionally resized to a square.

    Args:
        size: Target edge length in pixels, or None to keep the original.

    Returns:
        The loaded icon image.
    """
    with Image.open(get_icon_path()) as source:
        image = source.convert("RGBA")
    if size is not None and image.size != (size, size):
        image = image.resize((size, size), Image.Resampling.LANCZOS)
    return image
