"""Typed settings snapshot shared by loading, saving and resetting."""

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any

from .config import config
from .i18n import validate_language


@dataclass
class SettingsSnapshot:
    """Every persisted setting in one place."""

    language: str
    check_updates: bool
    width: int
    height: int
    maintain_aspect: bool
    add_dimensions: bool
    rotate_portrait: bool
    output_format: str
    jpeg_quality: int
    text: str
    color: str
    font_family: str
    font_path: str | None
    font_size: int
    font_style: str
    position: str
    offset_up: int
    offset_left: int
    output_dir: str
    overwrite: bool

    @classmethod
    def from_settings(cls, settings: Mapping[str, Any]) -> "SettingsSnapshot":
        """Build a snapshot from a validated settings mapping."""
        return cls(
            language=validate_language(settings.get("language")),
            check_updates=bool(
                settings.get("check_updates", config.default_check_updates)
            ),
            width=int(settings.get("width", config.default_width)),
            height=int(settings.get("height", config.default_height)),
            maintain_aspect=bool(
                settings.get("maintain_aspect", config.default_maintain_aspect_ratio)
            ),
            add_dimensions=bool(
                settings.get(
                    "add_dimensions",
                    config.default_add_dimensions_to_filename,
                )
            ),
            rotate_portrait=bool(
                settings.get(
                    "rotate_portrait",
                    config.default_rotate_portrait_to_landscape,
                )
            ),
            output_format=str(
                settings.get("output_format", config.default_output_format)
            ),
            jpeg_quality=int(settings.get("jpeg_quality", config.default_jpeg_quality)),
            text=str(settings.get("text", config.default_text)),
            color=str(settings.get("color", config.default_color)),
            font_family=str(settings.get("font_family", config.default_font_family)),
            font_path=settings.get("font_path"),
            font_size=int(settings.get("font_size", config.default_font_size)),
            font_style=str(settings.get("font_style", config.default_font_style)),
            position=str(settings.get("position", config.default_position)),
            offset_up=int(settings.get("offset_up", config.default_offset_up)),
            offset_left=int(settings.get("offset_left", config.default_offset_left)),
            output_dir=str(settings.get("output_dir", "")),
            overwrite=bool(settings.get("overwrite", False)),
        )

    @classmethod
    def defaults(cls, language: str | None = None) -> "SettingsSnapshot":
        """Return the factory defaults, optionally with a chosen language."""
        return cls(
            language=language or config.default_language,
            check_updates=config.default_check_updates,
            width=config.default_width,
            height=config.default_height,
            maintain_aspect=config.default_maintain_aspect_ratio,
            add_dimensions=config.default_add_dimensions_to_filename,
            rotate_portrait=config.default_rotate_portrait_to_landscape,
            output_format=config.default_output_format,
            jpeg_quality=config.default_jpeg_quality,
            text=config.default_text,
            color=config.default_color,
            font_family=config.default_font_family,
            font_path=None,
            font_size=config.default_font_size,
            font_style=config.default_font_style,
            position=config.default_position,
            offset_up=config.default_offset_up,
            offset_left=config.default_offset_left,
            output_dir="",
            overwrite=False,
        )

    def to_settings(self) -> dict[str, Any]:
        """Convert the snapshot to the persisted settings mapping."""
        return asdict(self)
