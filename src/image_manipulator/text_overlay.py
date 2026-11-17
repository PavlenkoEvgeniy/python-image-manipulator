"""Text overlay logic: font resolution, styling and drawing."""

import logging
import os
from enum import Enum
from typing import Optional, Tuple, Union

from PIL import Image, ImageDraw, ImageFont

from .config import config

FontType = Union[ImageFont.FreeTypeFont, ImageFont.ImageFont]

logger = logging.getLogger(__name__)


class FontStyle(Enum):
    """Font style enumeration."""

    NORMAL = "normal"
    BOLD = "bold"
    ITALIC = "italic"
    BOLD_ITALIC = "bold italic"


class TextPosition(Enum):
    """Text position enumeration."""

    TOP_LEFT = "top left"
    TOP_RIGHT = "top right"
    BOTTOM_LEFT = "bottom left"
    BOTTOM_RIGHT = "bottom right"
    CENTER = "center"


class TextOverlay:
    """Draws styled text onto an image."""

    # Shear factor used to synthesize italic (oblique) text.
    ITALIC_SHEAR = 0.25

    # Suffix appended to a family name to probe its styled variant.
    STYLE_SUFFIXES = {
        "Normal": "",
        "Bold": " Bold",
        "Italic": " Italic",
        "Bold Italic": " Bold Italic",
    }

    # Style names as fontconfig reports them.
    FC_STYLE_NAMES = {
        "Normal": "Regular",
        "Bold": "Bold",
        "Italic": "Italic",
        "Bold Italic": "Bold Italic",
    }

    def __init__(
        self,
        text: str = "",
        color: str = "#FFFFFF",
        font_family: Optional[str] = None,
        font_path: Optional[str] = None,
        font_size: int = 40,
        font_style: str = "Normal",
        position: str = "bottom right",
        offset_up: int = 20,
        offset_left: int = 20,
    ):
        """Initialize the overlay.

        Args:
            text: Text to draw.
            color: Text color (hex format).
            font_family: System font family. Ignored when font_path is set.
            font_path: Custom font file; takes precedence over font_family.
            font_size: Font size in pixels of the processed image.
            font_style: Normal, Bold, Italic or Bold Italic.
            position: Text position on the image.
            offset_up: Vertical offset from the image edge in pixels.
            offset_left: Horizontal offset from the image edge in pixels.
        """
        self.text = text
        self.color = color
        self.font_family = font_family
        self.font_path = font_path
        self.font_size = font_size
        self.font_style = font_style
        self.position = position
        self.offset_up = offset_up
        self.offset_left = offset_left

    # --- Font resolution ---

    def _load_system_font(self, size: int) -> Optional[FontType]:
        """Load a system font by family name, trying the styled variant first."""
        family = (self.font_family or "").strip()
        if not family:
            return None

        style = (self.font_style or "").strip()
        suffix = self.STYLE_SUFFIXES.get(style, "")

        for name in ([family + suffix] if suffix else []) + [family]:
            try:
                font = ImageFont.truetype(name, size)
                logger.debug(f"Loaded system font: {name}")
                return font
            except Exception:
                continue

        fc_style = self.FC_STYLE_NAMES.get(style, "Regular")
        for path in self._fontconfig_candidates(family, fc_style):
            try:
                font = ImageFont.truetype(path, size)
                logger.debug(f"Loaded system font: {path}")
                return font
            except Exception:
                continue

        logger.debug(f"Could not resolve system font family: {family}")
        return None

    @staticmethod
    def _fontconfig_candidates(family: str, fc_style: str) -> list:
        """Query fontconfig for font files of a family, best style first."""
        import subprocess

        try:
            result = subprocess.run(
                ["fc-list", f":family={family}"],
                capture_output=True,
                text=True,
                timeout=5,
            )
        except Exception as e:
            logger.debug(f"fontconfig query failed for {family}: {e}")
            return []

        exact, regular, others = [], [], []
        for line in result.stdout.splitlines():
            path, _, meta = line.partition(":")
            path = path.strip()
            if not path or not os.path.exists(path):
                continue
            styles = (
                [s.strip().lower() for s in meta.split("style=")[-1].split(",")]
                if "style=" in meta
                else []
            )
            if fc_style.lower() in styles:
                exact.append(path)
            elif "regular" in styles:
                regular.append(path)
            else:
                others.append(path)
        return exact + regular + others

    def _font_candidates(self, size: int):
        """Yield loadable fonts in priority order.

        A custom font file comes first, then the selected system family, then
        the fallback system fonts, and finally the default PIL font.
        """
        if self.font_path and os.path.exists(self.font_path):
            try:
                font = ImageFont.truetype(self.font_path, size)
                logger.debug(f"Loaded custom font: {self.font_path}")
                yield font
            except Exception as e:
                logger.warning(
                    f"Failed to load custom font {self.font_path}: {e}. Using fallback."
                )

        font = self._load_system_font(size)
        if font is not None:
            yield font

        for font_name in config.system_fonts:
            try:
                yield ImageFont.truetype(font_name, size)
            except Exception:
                continue

        logger.info("Using default PIL font")
        yield ImageFont.load_default()

    def get_font(self, size: int) -> FontType:
        """Get the first loadable font from the fallback chain."""
        for font in self._font_candidates(size):
            return font
        return ImageFont.load_default()

    def get_font_for_text(self, size: int, text: str) -> FontType:
        """Get a font that actually renders visible glyphs for the text.

        A font that loads but draws nothing for the text (its glyph set does
        not cover it) is skipped in favour of the next candidate.
        """
        last: Optional[FontType] = None
        for font in self._font_candidates(size):
            last = font
            if self._renders_text(font, text):
                return font
            source = getattr(font, "path", "default PIL font")
            logger.warning(f"Font {source} lacks glyphs for the text; trying next")
        return last if last is not None else ImageFont.load_default()

    @staticmethod
    def _renders_text(font: FontType, text: str) -> bool:
        """Check that the font draws at least one visible pixel for the text."""
        if not text.strip():
            return True

        try:
            left, top, right, bottom = font.getbbox(text)
        except Exception:
            return True

        layer = Image.new(
            "RGBA",
            (max(1, right - left + 4), max(1, bottom - top + 4)),
            (0, 0, 0, 0),
        )
        draw = ImageDraw.Draw(layer)
        draw.text((2 - left, 2 - top), text, fill=(255, 255, 255, 255), font=font)
        _, max_alpha = layer.getchannel("A").getextrema()
        return max_alpha > 0

    # --- Text metrics and placement ---

    def _get_style_flags(self) -> Tuple[bool, bool]:
        """Get (bold, italic) flags from the font style setting."""
        style = (self.font_style or "").strip().lower()
        return "bold" in style, "italic" in style

    def _get_stroke_width(self, size: int, bold: bool) -> int:
        """Stroke width used to synthesize bold text."""
        if not bold:
            return 0
        return max(1, round(size / 25))

    def get_text_size(
        self,
        draw: ImageDraw.ImageDraw,
        text: str,
        font: FontType,
        stroke_width: int = 0,
    ) -> Tuple[int, int, int, int]:
        """Measure the text bounding box.

        Returns:
            (width, height, offset_x, offset_y), where the offsets place the
            bounding box top-left relative to the drawing origin.
        """
        try:
            bbox = draw.textbbox((0, 0), text, font=font, stroke_width=stroke_width)
            width = bbox[2] - bbox[0]
            height = bbox[3] - bbox[1]
            offset_x, offset_y = bbox[0], bbox[1]
        except Exception:
            width, height = draw.textsize(text, font=font)
            offset_x, offset_y = 0, 0
        return int(width), int(height), int(offset_x), int(offset_y)

    def calculate_position(
        self,
        img_width: int,
        img_height: int,
        text_width: int,
        text_height: int,
    ) -> Tuple[int, int]:
        """Calculate the text bounding box position inside the image."""
        position = self.position
        offset_up = self.offset_up
        offset_left = self.offset_left

        x = 0
        y = 0

        if position == "top left":
            x = offset_left
            y = offset_up
        elif position == "top right":
            x = img_width - text_width - offset_left
            y = offset_up
        elif position == "bottom left":
            x = offset_left
            y = img_height - text_height - offset_up
        elif position == "bottom right":
            x = img_width - text_width - offset_left
            y = img_height - text_height - offset_up
        elif position == "center":
            x = (img_width - text_width) // 2
            y = (img_height - text_height) // 2

        return x, y

    # --- Drawing ---

    def apply_text(self, image: Image.Image) -> Optional[Image.Image]:
        """Draw the text onto a copy of the image.

        Args:
            image: Source image.

        Returns:
            A new image with the text drawn on it, or None when the text is
            empty.
        """
        if not self.text:
            logger.warning("No text provided for overlay")
            return None

        img = image.copy()
        draw = ImageDraw.Draw(img)

        font = self.get_font_for_text(self.font_size, self.text)
        bold, italic = self._get_style_flags()
        stroke_width = self._get_stroke_width(self.font_size, bold)

        text_width, text_height, offset_x, offset_y = self.get_text_size(
            draw, self.text, font, stroke_width
        )

        # Italic shear widens the rendered text to the right
        shear_extra = int(self.ITALIC_SHEAR * text_height) if italic else 0
        text_width += shear_extra

        x, y = self.calculate_position(img.width, img.height, text_width, text_height)

        if italic:
            self._draw_italic_text(
                img,
                x,
                y,
                text_width,
                text_height,
                offset_x,
                offset_y,
                font,
                stroke_width,
            )
        else:
            draw.text(
                (x, y),
                self.text,
                fill=self.color,
                font=font,
                stroke_width=stroke_width,
                stroke_fill=self.color,
            )

        logger.info(
            f"Applied text overlay: '{self.text}' at position ({x}, {y}) "
            f"(style: {self.font_style})"
        )
        return img

    def _draw_italic_text(
        self,
        img: Image.Image,
        x: int,
        y: int,
        text_width: int,
        text_height: int,
        offset_x: int,
        offset_y: int,
        font: FontType,
        stroke_width: int,
    ) -> None:
        """Draw text with a synthesized oblique (italic) shear."""
        pad = stroke_width + 2
        layer = Image.new(
            "RGBA", (text_width + 2 * pad, text_height + 2 * pad), (0, 0, 0, 0)
        )
        layer_draw = ImageDraw.Draw(layer)
        layer_draw.text(
            (pad - offset_x, pad - offset_y),
            self.text,
            fill=self.color,
            font=font,
            stroke_width=stroke_width,
            stroke_fill=self.color,
        )

        shear = self.ITALIC_SHEAR
        offset = int(shear * layer.height)
        layer = layer.transform(
            (layer.width + offset, layer.height),
            Image.AFFINE,
            (1, shear, -shear * layer.height, 0, 1, 0),
        )

        img.paste(layer, (x - pad, y - pad), layer)

    # --- Serialization ---

    @classmethod
    def from_dict(cls, settings: dict) -> "TextOverlay":
        """Create an overlay from a settings mapping."""
        return cls(
            text=settings.get("text", ""),
            color=settings.get("color", config.default_color),
            font_family=settings.get("font_family"),
            font_path=settings.get("font_path"),
            font_size=settings.get("font_size", config.default_font_size),
            font_style=settings.get("font_style", config.default_font_style),
            position=settings.get("position", config.default_position),
            offset_up=settings.get("offset_up", config.default_offset_up),
            offset_left=settings.get("offset_left", config.default_offset_left),
        )

    def to_dict(self) -> dict:
        """Convert the overlay settings to a mapping."""
        return {
            "text": self.text,
            "color": self.color,
            "font_family": self.font_family,
            "font_path": self.font_path,
            "font_size": self.font_size,
            "font_style": self.font_style,
            "position": self.position,
            "offset_up": self.offset_up,
            "offset_left": self.offset_left,
        }
