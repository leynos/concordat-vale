# valedate users' guide

Use `valedate` to exercise Vale rulesets inside pytest. The harness spins up an
isolated working directory with its own `.vale.ini` and `styles/` tree, invokes
the real `vale` binary, and returns structured diagnostics to assert against.
Install it from PyPI instead of relying on a vendored copy, so the helper can
evolve independently of this repository.

## Prerequisites

- Python 3.10 or newer
- The Vale Command-Line Interface (CLI) installed and available on `PATH`
- PyPI `valedate` (e.g., `pip install valedate==0.1.0b1`)

The harness intentionally shells out to Vale rather than mocking it. Tests are
expected to reflect how the ruleset behaves in production.

## Creating a sandbox

```python
from valedate import Valedate

ini = {
    "__root__": {"MinAlertLevel": "suggestion"},
    "[*.md]": {"BasedOnStyles": "Test"},
}

styles = {
    "Test/NoFoo.yml": """
        extends: existence
        message: "Avoid 'foo'."
        level: warning
        tokens:
          - foo
    """,
}

with Valedate(ini, styles=styles) as env:
    diags = env.lint("foo shows up here")
```

Provide styles either as a `Path` to an existing `styles` directory or as a
mapping of relative file paths to string/byte contents. The harness injects
`StylesPath = styles` into the generated `.vale.ini`, so setting it manually is
unnecessary.

## Assertion helpers

The `valedate.assertions` module shortens common checks:

- `assert_no_diagnostics(diags)` fails with a readable listing when any
  alerts are present.
- `assert_has_diagnostic` filters by check name, severity, line, match, or
  a substring of the message and returns the matching diagnostic.
- `assert_only_checks` enforces that the emitted diagnostics belong to the
  expected set of checks.

These helpers surface the actual Vale output in failures to keep iteration fast
when refining rules.

## Using `min_alert_level`

Set `min_alert_level` on the harness or per call to mirror `--minAlertLevel`
behaviour:

```python
with Valedate(ini, styles=styles, min_alert_level="error") as env:
    diags = env.lint("foo")  # warning-level rule suppressed
```

## Cleaning up

The harness acts as a context manager and cleans up its temporary directory on
exit. If constructed outside a `with` block, call `cleanup()` to remove the
temporary sandbox when finished.
