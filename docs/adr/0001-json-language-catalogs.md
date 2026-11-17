# 1. JSON language catalogs instead of gettext

- **Status:** Accepted
- **Date:** 2026-11-15

## Context

The interface was English-only with strings inlined in Tk widgets, dialogs, and
pipeline errors. The application needs ten interface languages, including
Russian, and ships as a PyInstaller binary for Linux, Windows, and macOS. There
is no build step beyond PyInstaller, and CI has no `msgfmt` on every runner.

Tk 8.6 also constrains the choice of languages: it does not shape Devanagari or
Arabic scripts, so Hindi and Arabic are not viable interface languages until the
Tk version changes.

## Decision

Store translations as JSON catalogs in the package, one file per language, keyed
by symbolic message IDs. English is the source catalog and the fallback for
missing keys and missing placeholders. Use symbolic keys rather than English
source text as the lookup key. Load catalogs from the package directory so the
existing `package-data` and `--collect-data` mechanism bundles them.

A language change is saved immediately but applies after the application is
restarted; rebuilding the whole Tk window in place was rejected.

The ten languages are English, Russian, Spanish, French, German, Portuguese
(Brazil), Italian, Chinese (Simplified), Japanese, and Korean — all render
correctly without complex text shaping.

Update 2026-11-15: Tagalog (`tl`, also matched from the `fil` locale code) was
added as the eleventh language. The rationale and the shaping constraint are
unchanged.

Update 2026-11-16: Turkish (`tr`), Dutch (`nl`), Polish (`pl`), Ukrainian
(`uk`) and Indonesian (`id`, also matched from the legacy `in` locale code)
were added as languages twelve through sixteen. All are Latin or Cyrillic and
need no text shaping.

## Consequences

- No external dependency, no `msgfmt`, and no per-OS build tooling.
- `tests/test_i18n.py` can enforce catalog key parity and placeholder parity
  headlessly on every platform.
- Translations are plain UTF-8 JSON and can be reviewed or machine-drafted
  without translation tooling.
- Adding a language means one catalog file plus one entry in the language list;
  `tests/test_i18n.py` checks that the two sets match.
- Missing or malformed catalogs degrade to English instead of failing startup.
- Switching languages requires a restart; live switching would mean rebuilding
  the widget tree and preserving loaded images and widget state.
- Hindi, Arabic, Bengali, and Urdu remain out of scope until the Tk version
  supports complex text shaping.
