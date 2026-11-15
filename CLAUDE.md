# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

Development install (Pillow is required; drag & drop and multi-monitor support are optional):

```bash
pip install -e ".[dev,dnd,multimonitor]"
```

If the repository has a local `.venv`, use `.venv/bin/python` / `.venv/bin/pytest`.

Run from source (no install needed — `main.py` adds `src/` to `sys.path`):

```bash
python main.py
python -m image_manipulator
image-manipulator            # after installation
```

Tests:

```bash
make test
python -m pytest -q
python -m pytest tests/test_pipeline.py::TestPortraitRotation::test_rotates_portrait_before_resize -v
```

There is no linter or formatter configured; pytest is the quality gate. Tests must not
create a Tk root — they run on headless CI. The pure processing modules are what keep
that possible. A regression test that genuinely needs Tk must skip when Tk cannot start
(see `tests/test_dialogs.py`).

Build:

```bash
make pyinstaller                 # PyInstaller with per-OS icon and package data
python tools/generate_icon.py    # regenerate assets/icon.{png,ico,icns} + package icon
```

CI (`.github/workflows/build.yml`) runs tests on Ubuntu, Windows, and macOS with
Python 3.14, builds PyInstaller binaries, and publishes a release when a `v*` tag is
pushed. Releases contain exactly three binaries; GitHub adds the source archives
automatically.

## Architecture

The application is one package, `src/image_manipulator`. The processing core is
deliberately independent of Tkinter:

- `resize.py` — aspect-ratio-aware dimension calculation and Lanczos resampling.
- `text_overlay.py` — font fallback chain (custom file → system family → fallback
  fonts → PIL default), glyph-coverage probe so a font without the needed glyphs is
  skipped, synthesized Bold (stroke) and Italic (shear), and text placement.
- `pipeline.py` — the single source of truth for processing order:
  normalize color mode → optional portrait rotation → resize → text → save.
  `load_image()` bakes EXIF orientation into pixels and normalizes palette/CMYK/16-bit
  images to RGB/RGBA; CMYK source profiles are dropped after conversion. ICC profiles
  are carried for JPEG/PNG/WEBP/TIFF. `process_path()` handles output naming,
  format-aware saving, and transparency flattening for JPEG/BMP.
- `settings_store.py` — versioned JSON settings with per-field validation/fallback
  and atomic writes.
- `ui.py` — Tkinter window: Resize/Text tabs, file list, debounced live preview,
  autosave, and a background batch worker. Worker threads never touch Tk widgets;
  status and completion events go through a `queue.Queue` polled on the main thread.
- `i18n.py` — JSON catalogs in `locales/`, symbolic message IDs, English fallback,
  OS-locale detection, and canonical-token ↔ translated-label mapping for enum
  values. `uifonts.py` applies a language's preferred UI font family to the Tk
  named fonts and to the dialogs' explicit fonts.
- `update_checker.py` — optional daily check of the latest GitHub release, numeric
  version comparison, per-OS release-asset selection, and the last-check state file.
  It is Tk-free and touches the network only when `check_for_update()` is called.
- `positioning.py` / `dialogs.py` / `icon.py` / `app.py` — monitor-aware centering,
  modal dialogs, icon loading, and application bootstrap.

### Invariants

- **Resize before text.** Font size is measured in pixels of the output image, not the
  source. Do not reorder the pipeline.
- `resize.py`, `text_overlay.py`, and `pipeline.py` must not import Tkinter; keep
  processing logic testable without a display.
- `ImageManipulator.render()` must not mutate its input image.
- Output filenames are `<stem>_<WxH>_text.<ext>`, with the dimensions and `_text` parts
  conditional. Existing files in the output folder get `_1`, `_2`, … instead of being
  overwritten. `overwrite=True` writes to the original path and keeps its format when
  the suffix is a known output format.
- `center_over_parent` takes keyword-only `window` and `parent`. Passing them
  positionally previously moved the main window instead of the dialog.
- **Tk images need a surviving owner.** A `PhotoImage` referenced only by a short-lived
  dialog is destroyed when that dialog is garbage-collected: Tk deletes the image while
  its `Label` keeps the requested size, so the user sees blank space. Assign it to the
  widget (`label.image = photo`), as `_show_image()` does for the preview canvas.
- Supported input formats are PNG/JPEG/BMP/GIF/TIFF/WEBP; selectable output formats are
  JPEG/PNG/WEBP/BMP. Overwriting keeps the original format, including GIF/TIFF.
- **Settings and the pipeline store canonical English tokens.** `position` and
  `font_style` in `settings.json` and `TextOverlay` are always `bottom right`,
  `Bold`, …; comboboxes show translated labels and convert with `translate_enum` /
  `canonical_enum`. Output filenames (`_text`) and `processed_images` are never
  localized.
- **The default output folder is `processed_images` on the Desktop** (`~/Desktop`
  or `%USERPROFILE%\Desktop`), falling back to the home directory when no Desktop
  folder exists. Never default to the directory of an installed binary: `/usr/bin`
  and `Program Files` are not writable by the user.
- **No hardcoded user-visible text.** Widgets, menus, statuses, dialogs, file-dialog
  titles and pipeline error messages go through `tr()`. Logs and README stay English.
- **Network access lives only in `update_checker.py`** and only inside an explicit
  check call — never at import or while loading settings. The UI runs it in a worker
  thread and reports through the event queue, so updates never block Tk. Only
  `https://` release URLs are opened in the browser.

### Adding a persisted setting

A setting touches several layers:

1. Default in `config.AppConfig`.
2. `settings_store.default_settings()` and `validate_settings()`.
3. UI variable, widget, trace registration, snapshot/apply/reset in `ui.py`.
4. `tests/test_settings_store.py`, plus a pipeline/UI test where applicable.

### Adding a UI string

1. Add the key to `src/image_manipulator/locales/en.json` (the English source).
2. Add the same key to every other catalog in `locales/`; `tests/test_i18n.py`
   enforces identical keys and identical `{placeholders}`.
3. Call `tr("section.key", **kwargs)`; use symbolic keys, not English text as the key.
4. Enum labels shown in comboboxes are translated with `translate_enum` and read back
   with `canonical_enum`.

### Settings behavior

- Stored in the platform config directory
  (`~/.config/image-manipulator/settings.json` on Linux,
  `%APPDATA%\image-manipulator\settings.json` on Windows,
  `~/Library/Application Support/image-manipulator/settings.json` on macOS).
- A corrupt file is ignored; an invalid field falls back to its own default while the
  rest loads as-is. Autosave is debounced (~300 ms) and flushed on close.
- The interface language is stored as `language` (e.g. `ru`) and applies after a
  restart. The first launch uses the OS locale, falling back to English.
- `check_updates` (default `true`) enables the daily automatic update check. The
  timestamp of the last successful check is state, not a setting: it lives in
  `update_check.json` next to `settings.json` and a failed check does not update it.
- `tkinterdnd2` and `screeninfo` are optional: missing drag & drop disables drop
  handlers, and missing monitor detection falls back to the whole virtual screen.

### Packaging and icons

- The window icon is `src/image_manipulator/icon.png`, declared in
  `[tool.setuptools.package-data]` and bundled by
  `--collect-data=image_manipulator`. Frozen builds read it from
  `sys._MEIPASS/image_manipulator/icon.png`.
- Build-time icons are `assets/icon.png` (Linux), `assets/icon.ico` (Windows), and
  `assets/icon.icns` (macOS). `tools/generate_icon.py` regenerates all of them.
- Language catalogs are `src/image_manipulator/locales/*.json`, covered by the same
  `[tool.setuptools.package-data]` entry and `--collect-data=image_manipulator`.
- Release assets are installers, not raw PyInstaller binaries:
  - Linux: `.deb` (Debian family) and `.rpm` (Fedora/openSUSE family), built by
    `packaging/linux/build_packages.sh`. Both install `/usr/bin/image-manipulator`,
    a desktop entry, and a 256 px icon. The RPM spec disables `__os_install_post`
    so the one-file payload is never stripped.
  - Windows: Inno Setup `setup.exe` built from
    `packaging/windows/image-manipulator.iss`; installs to `{autopf}`, creates Start
    Menu and optional desktop shortcuts, and registers an uninstaller in
    Apps & Features.
  - macOS: a `.dmg` containing `Image Manipulator.app` and an `/Applications`
    symlink, created with `hdiutil` on the macOS runner.
- Installers are unsigned: macOS Gatekeeper and Windows SmartScreen may warn. Do not
  claim they are signed or notarized.
- The update checker picks the installer for the running system: Linux `.deb` or
  `.rpm` via `/etc/os-release` (falling back to available tools), Windows `setup.exe`,
  macOS `.dmg`/`.pkg`, and the release page when no matching asset exists.
- The release job uploads the installer globs only. Do not use `artifacts/**/*` — it
  leaks the macOS `.app` bundle internals into release assets.
- The version is duplicated in `src/image_manipulator/__init__.py`,
  `config.AppConfig.version`, `pyproject.toml`, and `README.md`; keep them in sync for a
  release.
