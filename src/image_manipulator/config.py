"""Application configuration and constants."""

import os
import sys
from dataclasses import dataclass
from typing import Tuple


@dataclass
class AppConfig:
    """Application configuration shared by the UI and the pipeline."""

    name: str = "Image Manipulator"
    version: str = "1.0.0"
    window_width: int = 1100
    window_height: int = 800

    # Supported image and font formats
    valid_extensions: Tuple[str, ...] = (
        ".png",
        ".jpg",
        ".jpeg",
        ".bmp",
        ".gif",
        ".tiff",
        ".tif",
        ".webp",
    )
    font_extensions: Tuple[str, ...] = (".ttf", ".otf")

    # Resize defaults
    default_width: int = 800
    default_height: int = 600
    default_maintain_aspect_ratio: bool = True
    default_add_dimensions_to_filename: bool = True
    default_output_format: str = "JPEG"
    default_jpeg_quality: int = 95
    output_formats: Tuple[str, ...] = ("JPEG", "PNG", "WEBP", "BMP")
    min_dimension: int = 1
    max_dimension: int = 20000
    min_jpeg_quality: int = 1
    max_jpeg_quality: int = 100

    # Preset resolutions
    presets: Tuple[Tuple[str, int, int], ...] = (
        ("Custom", 0, 0),
        ("1920x1080", 1920, 1080),
        ("1280x720", 1280, 720),
        ("800x600", 800, 600),
        ("640x480", 640, 480),
        ("320x240", 320, 240),
    )

    # Text styling defaults
    default_text: str = "Your text"
    default_color: str = "#FFFFFF"
    default_font_size: int = 40
    default_position: str = "bottom right"
    default_offset_up: int = 20
    default_offset_left: int = 20
    default_font_style: str = "Normal"
    default_font_family: str = "Arial"

    font_styles: Tuple[str, ...] = ("Normal", "Bold", "Italic", "Bold Italic")
    text_positions: Tuple[str, ...] = (
        "top left",
        "top right",
        "bottom left",
        "bottom right",
        "center",
    )

    min_font_size: int = 10
    max_font_size: int = 200

    # Debounce delays in milliseconds
    preview_debounce_ms: int = 300
    settings_save_debounce_ms: int = 300

    # Fallback system fonts
    system_fonts: Tuple[str, ...] = (
        "arial.ttf",
        "Arial.ttf",
        "DejaVuSans.ttf",
        "FreeSans.ttf",
    )

    @property
    def default_output_dir(self) -> str:
        """Default output directory name."""
        return "processed_images"

    def get_preset_dimensions(self, preset_name: str) -> Tuple[int, int]:
        """Return (width, height) for a named preset, or (0, 0)."""
        for name, width, height in self.presets:
            if name == preset_name:
                return width, height
        return 0, 0


def get_app_dir() -> str:
    """Get the application directory (works for script and frozen builds)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def resource_path(relative_path: str) -> str:
    """Get an absolute path to a resource (works with PyInstaller)."""
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


# Global config instance
config = AppConfig()
