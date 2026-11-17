"""Tests for interface language catalogs, lookup and detection."""

import string

from image_manipulator import i18n
from image_manipulator.config import config

EXPECTED_CODES = [
    "en",
    "ru",
    "es",
    "fr",
    "de",
    "pt_BR",
    "it",
    "zh_CN",
    "ja",
    "ko",
    "tl",
    "tr",
    "nl",
    "pl",
    "uk",
    "id",
]


def _placeholders(text: str) -> set:
    """Names of the ``{placeholder}`` fields used by a message."""
    return {
        field
        for _, field, _, _ in string.Formatter().parse(text)
        if field is not None
    }


class TestLanguages:
    """The supported language set."""

    def test_every_supported_language_is_listed_in_order(self):
        assert [language.code for language in i18n.LANGUAGES] == EXPECTED_CODES

    def test_native_names_are_unique(self):
        names = [language.native_name for language in i18n.LANGUAGES]
        assert len(names) == len(set(names))

    def test_validate_language_falls_back_to_the_default(self):
        assert i18n.validate_language("ru") == "ru"
        assert i18n.validate_language("xx") == config.default_language
        assert i18n.validate_language(5) == config.default_language
        assert i18n.validate_language(None) == config.default_language


class TestCatalogs:
    """Every language ships a complete catalog."""

    def test_every_language_has_a_catalog(self):
        for code in EXPECTED_CODES:
            assert i18n.load_catalog(code), code

    def test_catalogs_match_the_english_keys(self):
        source = i18n.load_catalog("en")
        for code in EXPECTED_CODES:
            assert set(i18n.load_catalog(code)) == set(source), code

    def test_values_are_not_empty(self):
        for code in EXPECTED_CODES:
            for key, value in i18n.load_catalog(code).items():
                assert value.strip(), (code, key)

    def test_placeholders_match_english(self):
        source = i18n.load_catalog("en")
        for code in EXPECTED_CODES:
            catalog = i18n.load_catalog(code)
            for key, text in source.items():
                assert _placeholders(catalog[key]) == _placeholders(text), (
                    code,
                    key,
                )


class TestTranslation:
    """Lookup, fallback and enum labels."""

    def teardown_method(self):
        i18n.set_language(config.default_language)

    def test_translates_in_the_active_language(self):
        i18n.set_language("ru")

        assert i18n.tr("menu.file") == "Файл"

    def test_substitutes_placeholders(self):
        i18n.set_language("en")

        assert i18n.tr("status.added", count=3) == "Added images: 3"

    def test_missing_key_falls_back_to_english(self, monkeypatch):
        monkeypatch.setitem(i18n._catalogs, "ru", {})
        i18n.set_language("ru")

        assert i18n.tr("menu.file") == "File"

    def test_unknown_key_returns_the_key(self):
        i18n.set_language("en")

        assert i18n.tr("no.such.key") == "no.such.key"

    def test_enum_labels_round_trip(self):
        i18n.set_language("ru")

        assert i18n.translate_enum("position", "bottom right") == "нижний правый"
        assert i18n.canonical_enum("position", "нижний правый") == "bottom right"

    def test_canonical_enum_accepts_tokens_and_unknown_values(self):
        i18n.set_language("ru")

        assert i18n.canonical_enum("position", "bottom right") == "bottom right"
        assert i18n.canonical_enum("position", "middle") == "middle"

    def test_unknown_enum_kind_is_returned_unchanged(self):
        assert i18n.translate_enum("unknown", "value") == "value"


class TestDetection:
    """Choosing the initial language from the OS locale."""

    def test_plain_locale(self):
        assert i18n.detect_system_language({"LANG": "ru_RU.UTF-8"}) == "ru"

    def test_priority_order(self):
        assert (
            i18n.detect_system_language(
                {"LC_ALL": "ko_KR.UTF-8", "LANG": "en_US.UTF-8"}
            )
            == "ko"
        )

    def test_language_variable_is_split(self):
        assert i18n.detect_system_language({"LANGUAGE": "it:en"}) == "it"

    def test_portuguese_maps_to_brazil(self):
        assert i18n.detect_system_language({"LANG": "pt_PT.UTF-8"}) == "pt_BR"

    def test_only_simplified_chinese_is_supported(self):
        assert i18n.detect_system_language({"LANG": "zh_CN.UTF-8"}) == "zh_CN"
        assert i18n.detect_system_language({"LANG": "zh_TW.UTF-8"}) == "en"

    def test_tagalog_accepts_both_locale_codes(self):
        assert i18n.detect_system_language({"LANG": "tl_PH.UTF-8"}) == "tl"
        assert i18n.detect_system_language({"LANG": "fil_PH.UTF-8"}) == "tl"

    def test_new_latin_and_cyrillic_locales(self):
        assert i18n.detect_system_language({"LANG": "tr_TR.UTF-8"}) == "tr"
        assert i18n.detect_system_language({"LANG": "nl_NL.UTF-8"}) == "nl"
        assert i18n.detect_system_language({"LANG": "pl_PL.UTF-8"}) == "pl"
        assert i18n.detect_system_language({"LANG": "uk_UA.UTF-8"}) == "uk"

    def test_indonesian_accepts_both_locale_codes(self):
        assert i18n.detect_system_language({"LANG": "id_ID.UTF-8"}) == "id"
        assert i18n.detect_system_language({"LANG": "in_ID.UTF-8"}) == "id"

    def test_unknown_locale_falls_back(self):
        assert i18n.detect_system_language({}) == config.default_language

    def test_match_locale_handles_hyphens_and_modifiers(self):
        assert i18n.match_locale("de-DE") == "de"
        assert i18n.match_locale("sr_RS@latin") is None
        assert i18n.match_locale("") is None

    def test_match_locale_handles_script_and_region(self):
        assert i18n.match_locale("zh-Hans-CN") == "zh_CN"
        assert i18n.match_locale("zh_Hans_CN") == "zh_CN"
        assert i18n.match_locale("zh-Hans-SG") == "zh_CN"
        assert i18n.match_locale("zh-Hant-TW") is None

    def test_match_locale_handles_windows_names(self):
        assert i18n.match_locale("Russian_Russia.1251") == "ru"
        assert i18n.match_locale("Chinese (Simplified)_China.936") == "zh_CN"
        assert i18n.match_locale("Portuguese_Brazil.1252") == "pt_BR"
        assert i18n.match_locale("English_United States.1252") == "en"

    def test_match_locale_rejects_unsupported_windows_language(self):
        assert i18n.match_locale("Chinese (Traditional)_Taiwan.950") is None
