# Glossary

- **Interface language** — the language of the text the user sees: menus, labels,
  buttons, statuses, dialogs, and error messages. It is not the OS locale: dates,
  numbers, and collation are not localized.
- **Source language** — English. It is the language of the message IDs' fallback
  text and of the settings values.
- **Translation catalog** — the complete set of interface strings for one
  interface language, keyed by symbolic message IDs.
- **Canonical token** — a machine-readable English value persisted in settings and
  accepted by the processing pipeline (`bottom right`, `Bold`, `Custom`). It is
  distinct from the **display label**, the translated text shown in a widget.
- **Bundled icon** — the application icon shown in the window, the About dialog,
  and frozen builds. Distinct from the **platform build icon**, the OS-specific
  file used by the installer or executable shell.
- **Output folder** — the directory that receives processed images when originals
  are not overwritten. Its default name is language-neutral.
- **Update check** — an optional query of the project's public release metadata at
  application startup to learn whether a newer version exists. It sends no user data.
- **Release asset** — a downloadable file attached to a release. The direct
  download link in an update check points at the asset for the running operating
  system, falling back to the release page when that asset is absent.
- **Batch run** — one full processing pass over every selected file in the list,
  started by the "Process All" action. A repeated batch run is a new pass that
  produces new results; it never replaces the results of earlier runs.
  _Avoid_: reprocess, run, session.
