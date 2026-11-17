"""Text overlay logic: font resolution, styling and drawing."""

import logging
import os
import re
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any, ClassVar, cast

from PIL import Image, ImageDraw, ImageFont

from .config import config

FontType = ImageFont.FreeTypeFont | ImageFont.ImageFont

logger = logging.getLogger(__name__)

_ALLOWED_FONT_SUFFIXES = {
    "",
    "regular",
    "normal",
    "book",
    "roman",
    "bold",
    "italic",
    "oblique",
    "bolditalic",
    "italicbold",
    "semibold",
    "demibold",
    "light",
    "extralight",
    "ultralight",
    "black",
    "heavy",
    "medium",
    "thin",
    "condensed",
    "narrow",
}
_FONT_EXTENSIONS = {".ttf", ".otf", ".ttc", ".otc"}
_PLATFORM_FONT_FILES: list[tuple[str, Path]] | None = None
_FONT_CANDIDATE_CACHE: dict[tuple[str, str], list[str]] = {}
_WARNED_UNRESOLVED_FAMILIES: set[str] = set()


def _normalize_font_text(value: str) -> str:
    """Reduce a font file name or registry label to a comparison key."""
    text = os.path.splitext(os.path.basename(str(value)))[0]
    text = re.sub(r"\((?:TrueType|OpenType|All Res)\)", " ", text, flags=re.I)
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def _font_style_flags(name: str) -> tuple[bool, bool, bool]:
    """Return (bold, italic, condensed) flags for a font label."""
    normalized = _normalize_font_text(name)
    bold = any(
        token in normalized
        for token in ("bold", "black", "heavy", "semibold", "demibold")
    )
    italic = "italic" in normalized or "oblique" in normalized
    condensed = "condensed" in normalized or "narrow" in normalized
    return bold, italic, condensed


def _choose_platform_font(
    files: list[tuple[str, Path]], family: str, style: str
) -> list[Path]:
    """Pick the best installed file for a family and style.

    ``files`` contains (display name, path) pairs from the Windows registry or
    the macOS font directories. The function is pure so it can be tested
    without those platforms.
    """
    family_key = _normalize_font_text(family)
    wanted_bold, wanted_italic, _ = _font_style_flags(style)
    best = None
    best_key = None
    for display_name, path in files:
        normalized = _normalize_font_text(display_name)
        if not normalized.startswith(family_key):
            continue
        suffix = normalized[len(family_key) :]
        if suffix not in _ALLOWED_FONT_SUFFIXES:
            continue
        bold, italic, condensed = _font_style_flags(display_name)
        if (
            condensed
            and "condensed" not in family.lower()
            and "narrow" not in family.lower()
        ):
            continue
        score = 0
        if bold == wanted_bold:
            score += 4
        if italic == wanted_italic:
            score += 4
        if suffix in ("", "regular", "normal", "book", "roman"):
            score += 2
        if path.is_file():
            score += 1
        candidate_key = (-score, len(normalized), str(path))
        if best_key is None or candidate_key < best_key:
            best_key = candidate_key
            best = path
    return [best] if best is not None else []


def _windows_font_files() -> list[tuple[str, Path]]:
    """Read family labels and file paths from the Windows font registry."""
    try:
        import winreg
    except ImportError:
        return []

    font_dir = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    user_dir = (
        Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "Windows" / "Fonts"
    )
    entries = []
    # winreg exists only on Windows. Casting the module to Any keeps the
    # Windows-only attributes out of the cross-platform type check.
    registry = cast(Any, winreg)
    keys = (
        (
            registry.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts",
        ),
        (
            registry.HKEY_CURRENT_USER,
            r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts",
        ),
    )
    for hive, key_name in keys:
        try:
            with registry.OpenKey(hive, key_name) as key:
                index = 0
                while True:
                    try:
                        name, value, _ = registry.EnumValue(key, index)
                    except OSError:
                        break
                    index += 1
                    path = Path(value)
                    if not path.is_absolute():
                        path = font_dir / path
                    if path.suffix.lower() in _FONT_EXTENSIONS:
                        entries.append((name, path))
        except OSError:
            continue

    if user_dir.is_dir():
        entries.extend(
            (path.stem, path)
            for path in user_dir.iterdir()
            if path.suffix.lower() in _FONT_EXTENSIONS
        )
    return entries


def _macos_font_directories() -> tuple[Path, ...]:
    """Standard directories that contain macOS font files."""
    return (
        Path("/System/Library/Fonts"),
        Path("/System/Library/Fonts/Supplemental"),
        Path("/Library/Fonts"),
        Path.home() / "Library" / "Fonts",
    )


def _macos_font_files() -> list[tuple[str, Path]]:
    """List font files from the standard macOS font directories."""
    directories = _macos_font_directories()
    return [
        (path.stem, path)
        for directory in directories
        if directory.is_dir()
        for path in directory.rglob("*")
        if path.is_file() and path.suffix.lower() in _FONT_EXTENSIONS
    ]


def _platform_font_files() -> list[tuple[str, Path]]:
    """Return a cached font file list for Windows and macOS."""
    global _PLATFORM_FONT_FILES
    if _PLATFORM_FONT_FILES is None:
        if sys.platform.startswith("win"):
            _PLATFORM_FONT_FILES = _windows_font_files()
        elif sys.platform == "darwin":
            _PLATFORM_FONT_FILES = _macos_font_files()
        else:
            _PLATFORM_FONT_FILES = []
    return _PLATFORM_FONT_FILES


def _default_font(size: int) -> FontType:
    """Load Pillow's default font at the requested size when supported."""
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


class TextOverlay:
    """Draws styled text onto an image."""

    # Shear factor used to synthesize italic (oblique) text.
    ITALIC_SHEAR = 0.25

    # The canonical style registry from config drives the family suffix,
    # fontconfig style and bold/italic flags used below.
    STYLE_SUFFIXES: ClassVar[dict[str, str]] = {
        token: spec[1] for token, spec in config.STYLE_SPECS.items()
    }
    FC_STYLE_NAMES: ClassVar[dict[str, str]] = {
        token: spec[2] for token, spec in config.STYLE_SPECS.items()
    }

    def __init__(
        self,
        text: str = "",
        color: str = "#FFFFFF",
        font_family: str | None = None,
        font_path: str | None = None,
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

    @staticmethod
    def _try_load_font(name: str | Path, size: int) -> FontType | None:
        """Load a font file, returning None when the path cannot be opened."""
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            return None

    def _load_system_font(self, size: int) -> FontType | None:
        """Load a system font by family name, trying the styled variant first."""
        family = (self.font_family or "").strip()
        if not family:
            return None

        style = (self.font_style or "").strip()
        suffix = self.STYLE_SUFFIXES.get(style, "")

        for name in ([family + suffix] if suffix else []) + [family]:
            font = self._try_load_font(name, size)
            if font is not None:
                logger.debug(f"Loaded system font: {name}")
                return font

        fc_style = self.FC_STYLE_NAMES.get(style, "Regular")
        for path in self._fontconfig_candidates(family, fc_style):
            font = self._try_load_font(path, size)
            if font is not None:
                logger.debug(f"Loaded system font: {path}")
                return font

        if family not in _WARNED_UNRESOLVED_FAMILIES:
            logger.warning(
                "Could not resolve system font family %r; using fallback",
                family,
            )
            _WARNED_UNRESOLVED_FAMILIES.add(family)
        return None

    @staticmethod
    def _fontconfig_candidates(family: str, fc_style: str) -> list[str]:
        """Find the best face of a family, platform by platform."""
        import subprocess

        cache_key = (family, fc_style)
        cached = _FONT_CANDIDATE_CACHE.get(cache_key)
        if cached is not None:
            return list(cached)

        platform_matches = _choose_platform_font(
            _platform_font_files(), family, fc_style
        )
        if platform_matches:
            candidates = [str(path) for path in platform_matches]
            _FONT_CANDIDATE_CACHE[cache_key] = candidates
            return list(candidates)

        # Fontconfig style names differ between families (Book, Roman,
        # Oblique), so ask by slant and weight instead of by style name.
        # fc-match also avoids condensed variants unless they are the best
        # match for the family.
        slant_weight = {
            "Regular": "slant=roman:weight=regular",
            "Bold": "slant=roman:weight=bold",
            "Italic": "slant=italic:weight=regular",
            "Bold Italic": "slant=italic:weight=bold",
        }.get(fc_style)
        queries = (f"{family}:{slant_weight}", family) if slant_weight else (family,)
        candidates = []
        seen = set()
        for query in queries:
            try:
                result = subprocess.run(  # noqa: S603 - fixed executable
                    ["fc-match", "-f", "%{file}\t%{family}\n", query],  # noqa: S607
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
            except Exception as e:
                logger.debug(f"fontconfig query failed for {query}: {e}")
                _FONT_CANDIDATE_CACHE[cache_key] = candidates
                return candidates

            for line in result.stdout.splitlines():
                path, _, found_families = line.partition("\t")
                path = path.strip()
                families = [
                    name.strip().lower()
                    for name in found_families.split(",")
                    if name.strip()
                ]
                if not path or path in seen:
                    continue
                if families and family.lower() not in families:
                    continue
                filename = os.path.basename(path).lower()
                if (
                    ("condensed" in filename or "narrow" in filename)
                    and "condensed" not in family.lower()
                    and "narrow" not in family.lower()
                ):
                    continue
                if not os.path.exists(path):
                    continue
                seen.add(path)
                candidates.append(path)
        _FONT_CANDIDATE_CACHE[cache_key] = candidates
        return candidates

    def _font_candidates(self, size: int) -> Iterator[FontType]:
        """Yield loadable fonts in priority order.

        A custom font file comes first, then the selected system family, then
        the fallback system fonts, and finally the default PIL font.
        """
        if self.font_path and os.path.exists(self.font_path):
            try:
                custom_font = ImageFont.truetype(self.font_path, size)
            except Exception as e:
                logger.warning(
                    f"Failed to load custom font {self.font_path}: {e}. Using fallback."
                )
            else:
                logger.debug(f"Loaded custom font: {self.font_path}")
                yield custom_font

        system_font = self._load_system_font(size)
        if system_font is not None:
            yield system_font

        for font_name in config.system_fonts:
            fallback_font = self._try_load_font(font_name, size)
            if fallback_font is not None:
                yield fallback_font

        logger.info("Using default PIL font")
        yield _default_font(size)

    def get_font(self, size: int) -> FontType:
        """Get the first loadable font from the fallback chain."""
        for font in self._font_candidates(size):
            return font
        return _default_font(size)

    def get_font_for_text(self, size: int, text: str) -> FontType:
        """Get a font that actually renders visible glyphs for the text.

        A font that loads but draws nothing for the text (its glyph set does
        not cover it) is skipped in favour of the next candidate.
        """
        last: FontType | None = None
        for font in self._font_candidates(size):
            last = font
            if self._renders_text(font, text):
                return font
            source = getattr(font, "path", "default PIL font")
            logger.warning(f"Font {source} lacks glyphs for the text; trying next")
        return last if last is not None else _default_font(size)

    @staticmethod
    def _glyph_signature(
        font: FontType, character: str
    ) -> tuple[tuple[int, int], bytes]:
        """Return the size and pixels of one rendered glyph."""
        mask = font.getmask(character)
        return mask.size, bytes(mask)

    @classmethod
    def _renders_text(cls, font: FontType, text: str) -> bool:
        """Check that every non-space character has a real glyph.

        FreeType draws the ``.notdef`` box for missing characters, which is
        not empty. Comparing each glyph with U+FFFF (an unassigned codepoint
        that always maps to ``.notdef``) distinguishes real glyphs from tofu.
        """
        if not text.strip():
            return True

        try:
            notdef = cls._glyph_signature(font, "\uffff")
            for character in text:
                if character.isspace():
                    continue
                if cls._glyph_signature(font, character) == notdef:
                    return False
        except Exception:
            # Keep the historical optimistic behavior for exotic font
            # objects; drawing will still surface a real error.
            return True
        return True

    # --- Text metrics and placement ---

    def _get_style_flags(self) -> tuple[bool, bool]:
        """Get (bold, italic) flags from the canonical style token."""
        spec = config.STYLE_SPECS.get(self.font_style or "")
        if spec is not None:
            return spec[3], spec[4]
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
    ) -> tuple[int, int, int, int]:
        """Measure the text bounding box.

        Returns:
            (width, height, offset_x, offset_y), where the offsets place the
            bounding box top-left relative to the drawing origin.
        """
        try:
            bbox = draw.textbbox((0, 0), text, font=font, stroke_width=stroke_width)
        except Exception:
            # Pillow 10+ has no draw.textsize(); font.getbbox() is the
            # portable fallback and simply ignores the synthetic stroke.
            bbox = font.getbbox(text)
        width = bbox[2] - bbox[0]
        height = bbox[3] - bbox[1]
        offset_x, offset_y = bbox[0], bbox[1]
        return int(width), int(height), int(offset_x), int(offset_y)

    def calculate_position(
        self,
        img_width: int,
        img_height: int,
        text_width: int,
        text_height: int,
    ) -> tuple[int, int]:
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

    def apply_text(self, image: Image.Image) -> Image.Image | None:
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
                (x - offset_x, y - offset_y),
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
            Image.Transform.AFFINE,
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
