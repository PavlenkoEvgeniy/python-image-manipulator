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
that possible.

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
- Supported input formats are PNG/JPEG/BMP/GIF/TIFF/WEBP; selectable output formats are
  JPEG/PNG/WEBP/BMP. Overwriting keeps the original format, including GIF/TIFF.

### Adding a persisted setting

A setting touches several layers:

1. Default in `config.AppConfig`.
2. `settings_store.default_settings()` and `validate_settings()`.
3. UI variable, widget, trace registration, snapshot/apply/reset in `ui.py`.
4. `tests/test_settings_store.py`, plus a pipeline/UI test where applicable.

### Settings behavior

- Stored in the platform config directory
  (`~/.config/image-manipulator/settings.json` on Linux,
  `%APPDATA%\image-manipulator\settings.json` on Windows,
  `~/Library/Application Support/image-manipulator/settings.json` on macOS).
- A corrupt file is ignored; an invalid field falls back to its own default while the
  rest loads as-is. Autosave is debounced (~300 ms) and flushed on close.
- `tkinterdnd2` and `screeninfo` are optional: missing drag & drop disables drop
  handlers, and missing monitor detection falls back to the whole virtual screen.

### Packaging and icons

- The window icon is `src/image_manipulator/icon.png`, declared in
  `[tool.setuptools.package-data]` and bundled by
  `--collect-data=image_manipulator`. Frozen builds read it from
  `sys._MEIPASS/image_manipulator/icon.png`.
- Build-time icons are `assets/icon.png` (Linux), `assets/icon.ico` (Windows), and
  `assets/icon.icns` (macOS). `tools/generate_icon.py` regenerates all of them.
- The release job uploads exactly three paths. If build names change, update both the
  CI matrix and the release `files:` list. Do not use `artifacts/**/*` — it leaks the
  macOS `.app` bundle internals into release assets.
- The version is duplicated in `src/image_manipulator/__init__.py`,
  `config.AppConfig.version`, `pyproject.toml`, and `README.md`; keep them in sync for a
  release.
