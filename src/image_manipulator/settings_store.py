"""Persistence of Saved settings between sessions.

Settings are stored as versioned JSON in the user's platform config
directory and loaded back on the next launch. Loading is forgiving: a
corrupt file falls back silently to defaults, and each invalid field falls
back to its own default while the remaining fields load as-is.
"""

import json
import os
import re
import sys
import tempfile
from typing import Any, Optional

from .config import config
from .logging_config import get_logger

logger = get_logger(__name__)

SETTINGS_VERSION = 1
SETTINGS_DIR_NAME = "image-manipulator"
SETTINGS_FILENAME = "settings.json"

_HEX_COLOR = re.compile(r"#[0-9a-fA-F]{6}")
_MAX_OFFSET = 100000


def get_settings_path() -> str:
    """Get the platform-specific path of the Settings file."""
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    elif sys.platform == "darwin":
        base = os.path.join(os.path.expanduser("~"), "Library", "Application Support")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(
            os.path.expanduser("~"), ".config"
        )
    return os.path.join(base, SETTINGS_DIR_NAME, SETTINGS_FILENAME)


def default_settings() -> dict:
    """Return a complete settings mapping with every default value."""
    return {
        "width": config.default_width,
        "height": config.default_height,
        "maintain_aspect": config.default_maintain_aspect_ratio,
        "add_dimensions": config.default_add_dimensions_to_filename,
        "rotate_portrait": config.default_rotate_portrait_to_landscape,
        "output_format": config.default_output_format,
        "jpeg_quality": config.default_jpeg_quality,
        "text": config.default_text,
        "color": config.default_color,
        "font_family": config.default_font_family,
        "font_path": None,
        "font_size": config.default_font_size,
        "font_style": config.default_font_style,
        "position": config.default_position,
        "offset_up": config.default_offset_up,
        "offset_left": config.default_offset_left,
        "output_dir": "",
        "overwrite": False,
    }


def _clamped_int(raw: dict, key: str, default: int, minimum: int, maximum: int) -> int:
    """Read an integer, falling back to the default and clamping to range."""
    value = raw.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        return default
    return max(minimum, min(value, maximum))


def _bool(raw: dict, key: str, default: bool) -> bool:
    """Read a boolean, falling back to the default."""
    value = raw.get(key)
    return value if isinstance(value, bool) else default


def _string(raw: dict, key: str, default: str) -> str:
    """Read a string, falling back to the default."""
    value = raw.get(key)
    return value if isinstance(value, str) else default


def validate_settings(raw: dict) -> dict:
    """Validate saved values one by one; invalid ones fall back to defaults.

    Args:
        raw: Raw settings mapping as read from the Settings file.

    Returns:
        A complete settings dict with every known key holding a safe value.
    """
    settings: dict[str, Any] = {}

    # Resize settings
    settings["width"] = _clamped_int(
        raw, "width", config.default_width, config.min_dimension, config.max_dimension
    )
    settings["height"] = _clamped_int(
        raw, "height", config.default_height, config.min_dimension, config.max_dimension
    )
    settings["maintain_aspect"] = _bool(
        raw, "maintain_aspect", config.default_maintain_aspect_ratio
    )
    settings["add_dimensions"] = _bool(
        raw, "add_dimensions", config.default_add_dimensions_to_filename
    )
    settings["rotate_portrait"] = _bool(
        raw, "rotate_portrait", config.default_rotate_portrait_to_landscape
    )

    output_format = raw.get("output_format")
    settings["output_format"] = (
        output_format
        if output_format in config.output_formats
        else config.default_output_format
    )
    settings["jpeg_quality"] = _clamped_int(
        raw,
        "jpeg_quality",
        config.default_jpeg_quality,
        config.min_jpeg_quality,
        config.max_jpeg_quality,
    )

    # Text styling
    settings["text"] = _string(raw, "text", config.default_text)

    color = raw.get("color")
    settings["color"] = (
        color
        if isinstance(color, str) and _HEX_COLOR.fullmatch(color)
        else config.default_color
    )

    settings["font_family"] = _string(
        raw, "font_family", config.default_font_family
    )

    font_path = raw.get("font_path")
    settings["font_path"] = font_path if font_path is None or isinstance(
        font_path, str
    ) else None

    settings["font_size"] = _clamped_int(
        raw, "font_size", config.default_font_size,
        config.min_font_size, config.max_font_size,
    )

    font_style = raw.get("font_style")
    settings["font_style"] = (
        font_style if font_style in config.font_styles else config.default_font_style
    )

    position = raw.get("position")
    settings["position"] = (
        position if position in config.text_positions else config.default_position
    )

    for key, default in (
        ("offset_up", config.default_offset_up),
        ("offset_left", config.default_offset_left),
    ):
        settings[key] = _clamped_int(raw, key, default, 0, _MAX_OFFSET)

    # Output
    settings["output_dir"] = _string(raw, "output_dir", "")
    settings["overwrite"] = _bool(raw, "overwrite", False)

    return settings


def save_settings(settings: dict, path: Optional[str] = None) -> bool:
    """Save settings atomically to the Settings file.

    Args:
        settings: Complete settings mapping to persist.
        path: Target path; defaults to the platform settings path.

    Returns:
        True on success, False if writing failed (already logged).
    """
    target = path or get_settings_path()
    payload = {"version": SETTINGS_VERSION, "settings": settings}
    try:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        fd, tmp = tempfile.mkstemp(
            prefix=".settings-", suffix=".tmp", dir=os.path.dirname(target)
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            os.replace(tmp, target)
        except BaseException:
            try:
                os.remove(tmp)
            except OSError:
                pass
            raise
        return True
    except Exception as e:
        logger.warning(f"Failed to save settings to {target}: {e}")
        return False


def load_settings(path: Optional[str] = None) -> Optional[dict]:
    """Load and validate Saved settings.

    Args:
        path: Source path; defaults to the platform settings path.

    Returns:
        A validated settings dict, or None when defaults should be used.
    """
    target = path or get_settings_path()
    try:
        with open(target, encoding="utf-8") as f:
            payload = json.load(f)
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as e:
        logger.warning(f"Ignoring corrupt settings file {target}: {e}")
        return None

    if not isinstance(payload, dict) or payload.get("version") != SETTINGS_VERSION:
        logger.warning(f"Ignoring settings file {target}: unsupported format")
        return None

    raw = payload.get("settings")
    if not isinstance(raw, dict):
        logger.warning(f"Ignoring settings file {target}: no settings object")
        return None

    return validate_settings(raw)


def clear_settings(path: Optional[str] = None) -> bool:
    """Delete the Settings file (Reset settings).

    Args:
        path: Target path; defaults to the platform settings path.

    Returns:
        True when the file is gone (or was never there), False on failure.
    """
    target = path or get_settings_path()
    try:
        os.remove(target)
        return True
    except FileNotFoundError:
        return True
    except OSError as e:
        logger.warning(f"Failed to delete settings file {target}: {e}")
        return False
