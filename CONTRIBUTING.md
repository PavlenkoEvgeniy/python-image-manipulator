# Contributing

## Local workflow

Install the development dependencies and the pre-commit hooks:

```bash
pip install -e ".[dev,dnd,multimonitor]"
pre-commit install
```

Run the complete local quality gate before pushing:

```bash
make quality
```

This runs Ruff lint and format checks, mypy on `src/`, vulture at 80% confidence,
and the test suite with branch coverage. The same checks run in CI, so a green
local run means CI should agree.

To run the hooks against the whole tree:

```bash
pre-commit run --all-files
```

## Tests

```bash
make test
python -m pytest -q
```

Tests must not create a Tk root unless they explicitly skip when Tk cannot start
(see `tests/test_dialogs.py`). Coverage is measured with branches and must stay
at or above the threshold in `pyproject.toml`.

## Translations

The English catalog is the source. Every other catalog must have the same keys
and the same `{placeholders}`; `tests/test_i18n.py` enforces both.
