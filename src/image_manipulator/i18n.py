"""Interface language catalogs and translation helpers.

Catalogs are JSON files in ``locales/`` keyed by symbolic message IDs. English
is the source catalog and the fallback for any missing key. The module is free
of Tkinter so the processing modules can use it too.
"""

import json
import locale
import logging
import os
import warnings
from dataclasses import dataclass
from typing import Dict, Mapping, Optional, Tuple

from .config import config

logger = logging.getLogger(__name__)

CATALOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "locales")


@dataclass(frozen=True)
class Language:
    """A supported interface language."""

    code: str
    native_name: str
    english_name: str
    preferred_fonts: Tuple[str, ...] = ()


# Sixteen widely used desktop languages. Hindi and Arabic are deliberately absent:
# Tk 8.6 does not shape Devanagari or Arabic scripts, so they would render
# broken on every platform. CJK, Latin and Cyrillic need no shaping.
LANGUAGES: Tuple[Language, ...] = (
    Language("en", "English", "English"),
    Language("ru", "Русский", "Russian"),
    Language("es", "Español", "Spanish"),
    Language("fr", "Français", "French"),
    Language("de", "Deutsch", "German"),
    Language("pt_BR", "Português (Brasil)", "Portuguese (Brazil)"),
    Language("it", "Italiano", "Italian"),
    Language(
        "zh_CN",
        "简体中文",
        "Chinese (Simplified)",
        ("Microsoft YaHei", "PingFang SC", "Noto Sans CJK SC", "Noto Sans SC"),
    ),
    Language(
        "ja",
        "日本語",
        "Japanese",
        ("Yu Gothic UI", "Yu Gothic", "Hiragino Sans", "Meiryo", "Noto Sans CJK JP"),
    ),
    Language(
        "ko",
        "한국어",
        "Korean",
        ("Malgun Gothic", "Apple SD Gothic Neo", "Noto Sans CJK KR", "Noto Sans KR"),
    ),
    Language("tl", "Tagalog", "Tagalog"),
    Language("tr", "Türkçe", "Turkish"),
    Language("nl", "Nederlands", "Dutch"),
    Language("pl", "Polski", "Polish"),
    Language("uk", "Українська", "Ukrainian"),
    Language("id", "Bahasa Indonesia", "Indonesian"),
)

LANGUAGES_BY_CODE: Dict[str, Language] = {language.code: language for language in LANGUAGES}
SUPPORTED_CODES: Tuple[str, ...] = tuple(LANGUAGES_BY_CODE)

# Windows reports locale names such as "Russian_Russia.1251", not POSIX
# codes. Map the English language names to the catalogs we ship.
_WINDOWS_LANGUAGE_ALIASES: Dict[str, str] = {
    "english": "en",
    "russian": "ru",
    "spanish": "es",
    "french": "fr",
    "german": "de",
    "portuguese": "pt_BR",
    "italian": "it",
    "chinese (simplified)": "zh_CN",
    "japanese": "ja",
    "korean": "ko",
    "tagalog": "tl",
    "filipino": "tl",
    "turkish": "tr",
    "dutch": "nl",
    "polish": "pl",
    "ukrainian": "uk",
    "indonesian": "id",
}

_ENUM_KEYS: Dict[str, Dict[str, str]] = {
    "position": {
        "top left": "position.top_left",
        "top right": "position.top_right",
        "bottom left": "position.bottom_left",
        "bottom right": "position.bottom_right",
        "center": "position.center",
    },
    "font_style": {
        "Normal": "style.normal",
        "Bold": "style.bold",
        "Italic": "style.italic",
        "Bold Italic": "style.bold_italic",
    },
}

_catalogs: Dict[str, Dict[str, str]] = {}
_active_language: str = config.default_language


def catalog_path(code: str) -> str:
    """Absolute path to a language catalog file."""
    return os.path.join(CATALOG_DIR, f"{code}.json")


def load_catalog(code: str) -> Dict[str, str]:
    """Load and cache a catalog; a broken file yields an empty catalog."""
    if code in _catalogs:
        return _catalogs[code]

    catalog: Dict[str, str] = {}
    try:
        with open(catalog_path(code), encoding="utf-8") as handle:
            raw = json.load(handle)
        if isinstance(raw, dict):
            catalog = {
                str(key): str(value)
                for key, value in raw.items()
                if isinstance(value, str)
            }
        else:
            logger.warning("Language catalog %s is not an object", code)
    except (OSError, ValueError) as exc:
        logger.warning("Cannot load language catalog %s: %s", code, exc)

    _catalogs[code] = catalog
    return catalog


def validate_language(value: object) -> str:
    """Return a supported language code, falling back to the default."""
    if isinstance(value, str) and value in LANGUAGES_BY_CODE:
        return value
    return config.default_language


def set_language(code: str) -> str:
    """Activate a language for every later ``tr()`` call."""
    global _active_language
    _active_language = validate_language(code)
    return _active_language


def get_language() -> str:
    """The language code currently used by ``tr()``."""
    return _active_language


def language_info(code: Optional[str] = None) -> Language:
    """Return the Language record for a code (or for the active language)."""
    return LANGUAGES_BY_CODE[validate_language(code if code is not None else _active_language)]


def tr(key: str, **kwargs: object) -> str:
    """Translate a message ID, falling back to English and then to the key.

    Keyword arguments are substituted into ``{name}`` placeholders. A missing
    catalog or key never raises: the English text or the key itself is shown.
    """
    text = load_catalog(_active_language).get(key)
    if text is None:
        text = load_catalog(config.default_language).get(key)
    if text is None:
        logger.warning("Missing translation key: %s", key)
        return key

    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, IndexError, ValueError) as exc:
            logger.warning("Bad placeholders for %s: %s", key, exc)
    return text


def translate_enum(kind: str, value: str) -> str:
    """Translate the display label of a canonical enum value."""
    key = _ENUM_KEYS.get(kind, {}).get(value)
    return tr(key) if key else value


def canonical_enum(kind: str, value: str) -> str:
    """Map a displayed (possibly translated) enum label back to its token.

    Unknown values are returned unchanged so an old settings file or a
    third-party edit cannot corrupt the persisted value.
    """
    for canonical, key in _ENUM_KEYS.get(kind, {}).items():
        if value == canonical or value == tr(key):
            return canonical
    return value


def _normalize_locale(value: str) -> str:
    """Reduce ``ru_RU.UTF-8`` / ``zh-Hans-CN`` to a ``language_REGION`` form."""
    return value.split(".", 1)[0].split("@", 1)[0].replace("-", "_")


def match_locale(value: str) -> Optional[str]:
    """Map an OS locale string to a supported language code, or None."""
    normalized = _normalize_locale(value.strip())
    if not normalized:
        return None
    if normalized in LANGUAGES_BY_CODE:
        return normalized

    language, _, rest = normalized.partition("_")
    language = language.lower()
    subtags = [part.upper() for part in rest.split("_") if part]

    if language in _WINDOWS_LANGUAGE_ALIASES:
        return _WINDOWS_LANGUAGE_ALIASES[language]
    if language == "pt":
        return "pt_BR"
    if language == "zh":
        # Only Simplified Chinese is supported; Traditional falls back to
        # English. Script and region can both be present (zh-Hans-CN).
        return "zh_CN" if any(part in ("CN", "SG", "HANS") for part in subtags) else None
    if language == "fil":
        # Filipino and Tagalog share one catalog; OS locales use both codes.
        return "tl"
    if language == "in":
        # POSIX and some Windows locales still report the old Indonesian code.
        return "id"
    if language in LANGUAGES_BY_CODE:
        return language
    return None


def _os_locale_names() -> list:
    """Best-effort list of locale names reported by the interpreter."""
    names = []
    try:
        current = locale.getlocale()[0]
        if current:
            names.append(current)
    except (TypeError, ValueError):
        pass

    getdefaultlocale = getattr(locale, "getdefaultlocale", None)
    if getdefaultlocale is not None:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", DeprecationWarning)
                default = getdefaultlocale()[0]
            if default:
                names.append(default)
        except (TypeError, ValueError):
            pass
    return names


def detect_system_language(env: Optional[Mapping[str, str]] = None) -> str:
    """Pick the initial language from the OS locale.

    Args:
        env: Environment mapping to inspect; when given, the interpreter's own
            locale is not consulted, which keeps tests deterministic.

    Returns:
        A supported language code; the default when nothing matches.
    """
    environment = os.environ if env is None else env
    candidates = []
    for name in ("LC_ALL", "LC_MESSAGES", "LANGUAGE", "LANG"):
        value = environment.get(name)
        if value:
            candidates.extend(value.split(":"))

    if env is None:
        candidates.extend(_os_locale_names())

    for candidate in candidates:
        code = match_locale(candidate)
        if code:
            return code
    return config.default_language
