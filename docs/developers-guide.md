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

## Acronym link-mask regressions

`styles/config/scripts/AcronymsFirstUse.tengo` is the canonical source of the
first-use rule. Its link-mask pass remembers when an opening bracket search
reaches the end without an eligible closing bracket. Ignored ranges only grow,
so later masking cannot introduce a closing bracket. The outer pass continues
to mask later autolinks; successful links and nested targets retain their
existing handling.

The regression module `tests/styles/test_acronyms_first_use.py` covers plain
and unmatched-bracket prefixes at 2,048 and 4,096 characters, code and link
masking, definitions, first-use warnings, and exact diagnostic spans. Before
the change, the 4,096-bracket case failed with Vale exit status 2 under both
Vale 3.22.0 and the owning CI pin, 3.24.0; the other 17 cases passed. This is
controlled regression evidence, not identification of a failing consumer guide.
Run the focused module through the repository's environment helper:

```sh
python3 scripts/uv_gate.py run --group dev -- pytest -v -n 0 tests/styles/test_acronyms_first_use.py
```

Validate with the pinned 3.24.0 binary for this repository and separately with
3.22.0 for the consumer compatibility contract. Neither check replaces the
complete `make test` suite. A merged fix still needs an approved versioned
style release and verified archive before consumer adoption. Review the full
package diff: current main also includes previously merged mixed-case and
composite-token handling absent from the published v0.1.0 archive. Real
consumer guide inspection remains a separate check after adoption.

## Acronym ignored-range cache regressions

`tests/styles/test_acronym_ignore_cache.py` exercises dense inline masks
followed by fixed 128 and 256 KiB prose gaps. The native tests require a
reachable outside warning with its complete public diagnostic metadata; a
successful process exit alone is insufficient. The remaining cases cover mask
appends, lookahead rewinds, half-open boundaries, overlapping and equal-start
masks, multibyte spans, and a test-local project exception. The existing
definition and repeated-first-use corpus remains unchanged.

Any cached miss must apply only to its proven search gap and be invalidated
when an ignored range is appended. A rewind outside that gap must perform the
original lookup. These invariants preserve the existing lookup result rather
than introduce a different interval-union policy. The canonical source and the
project allow-map injection interface remain separate concerns.

The canonical lookup caches only the half-open gap established by a failed
binary search. Each left branch bounds the gap above by that range's start;
each right branch bounds it below by that range's end. Every index inside those
bounds follows the same comparisons and also misses. Hits and sorting retain
their original handling, and adding any range invalidates the cache.

`tests/fixtures/acronym-real-guide.txt` preserves the original 286,636-byte
`docs/concordat-design.md` consumer workload used in the H26-REAL diagnosis.
Its SHA-256 is
`151a241e50bb871e9310eeb8c4b29f666a66b3475f511c4628ac3d06f5ae1242`. It is
byte-exact test data, not maintained prose: do not reflow or correct its
examples. The native regression checks complete early XDG and later ADR
first-use diagnostics rather than treating successful completion as enough. The
fixture-equivalent stdin run reproduced the canonical rule's explicit E201
two-second deadline failure with Vale 3.23.0 before the cache change; this does
not establish identical historical consumer invocation or general timing
guarantees. Runtime exceptions retain their original type and status; the
regression adds the harness's captured stderr as a diagnostic note.

Run the new module with the existing regression corpus through the environment
helper, using the approved Vale binary on `PATH`:

```sh
python3 scripts/uv_gate.py run --group dev -- pytest -v -n 0 \
  tests/styles/test_acronym_ignore_cache.py tests/styles/test_acronyms_first_use.py
```

The first failing dense case must be measured before changing the canonical
lookup. Keep the two fixed input bounds and the native script budget; if
neither case reproduces the failure, investigate before enlarging the corpus.
The owning 3.24.0 suite, documented 3.22.0 compatibility checks, and the 3.23.0
consumer reproduction are distinct evidence. Completion on one workload does
not establish warning parity with an earlier run that produced no report, a
universal timing guarantee, a release, or consumer adoption.
