# Developers' guide

This guide records how the repository's development tooling is wired, for
people changing the Vale style or its documentation. Using the style in another
repository is covered in the [usage guide](users-guide.md).

## Markdown formatting and linting

- `make fmt` rewrites Markdown with
  `mdtablefix --in-place --git --include-untracked --wrap --renumber --breaks
  --ellipsis --fences`,
  then runs `markdownlint-cli2 --fix "**/*.md"`.
- `make check-fmt` runs the same `mdtablefix` command with `--check` in place of
  `--in-place`, and fails when any file would change.
- `make markdownlint` runs `markdownlint-cli2 '**/*.md'`. It does not run
  Vale; run `make vale` separately for the Vale checks, including the spelling
  rules.
- `.markdownlint-cli2.jsonc` carries the canonical markdownlint configuration.
  Keep its `config` entries and `ignores` globs; add repository-specific rules
  or globs beside them.
- CI lints `**/*.md` with the pinned `markdownlint-cli2-action` in the
  `markdownlint` workflow.

Install mdtablefix 0.6.1 or later with
`cargo binstall --no-confirm mdtablefix@0.6.1` or
`cargo install --locked mdtablefix@0.6.1`, and markdownlint-cli2 with
`bun add --global markdownlint-cli2` or
`npm install --global markdownlint-cli2`.

### The linter is a required tool

`MDLINT` is the literal command name `markdownlint-cli2`, not a
`$(shell which ...)` lookup. A lookup expands to nothing when the tool is
missing, and Make then reads the leading `--` of `$(MDLINT) --fix` as recipe
prefix characters, so `make fmt` could report success without linting. With the
literal name, a missing tool stops Make with
`'markdownlint-cli2' is required, but not installed`.
`tests/test_makefile_markdownlint.py` runs `make markdownlint` and `make fmt`
from the real Makefile with a controlled `PATH` of recording stubs, to hold
both the missing-tool and present-tool paths.

## Running the tests

`make test` runs every test with `pytest -n auto`. The style tests under
`tests/styles` drive a real `vale` binary through valedate and provide no stub,
so `vale` must be on `PATH`; without it they error with
`ValeBinaryNotFoundError`.

CI installs the Vale release pinned in `.github/workflows/tests.yml`
(`VALE_VERSION` and `VALE_SHA256`, currently 3.24.0) and checks the archive's
SHA-256 before unpacking it, so a moved or replaced download fails the job
instead of changing what the tests accept. Install the same version locally to
match. To change the pin, update both values together, from the digest GitHub
publishes for the `Linux_64-bit` archive.

`tests/test_tests_workflow_wiring.py` parses the workflow as YAML and holds the
wiring: `make test` is the last step, Vale is pinned by version and digest and
checked before it is unpacked and put on `PATH`, the push and pull request
triggers, the timeout, the read-only token, and the commit pins on every
action. It needs PyYAML, a development dependency.
