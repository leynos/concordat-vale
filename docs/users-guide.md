# Usage guide

## Packaging the Vale style with `stilyagi`

- `uv sync --group dev` (or `make build`) should be run once so the `stilyagi`
  entry point is available locally.
- `stilyagi zip` should be invoked from the repository root to create a
  distributable ZIP that contains `.vale.ini` plus the full `styles/` tree.

### Default workflow

1. `make build` (installs dependencies when needed).
2. `uv run stilyagi zip`
3. Retrieve the archive from `dist/concordat-<version>.zip` and attach it to
   the release currently being prepared.

Running the command without flags auto-discovers available styles and the sole
vocabulary (`concordat`). The `.vale.ini` header matches `[*.{md,adoc,txt}]` to
cover Markdown, AsciiDoc, and text files.

### Customisation

- `--archive-version` can be used to override the archive suffix (for example,
  `uv run stilyagi zip --archive-version 2025.11.07`). When omitted, the value
  from `pyproject.toml` is used.
- `--style` (repeatable) limits the archive to specific style directories when
  more styles are added later. Without this flag, every non-config style in
  `styles/` is included.
- `--output-dir` changes the destination directory (defaults to `dist`).
- `--project-root` should be supplied when running the command from outside the
  repository so the path anchors every other relative argument.
- `--ini-styles-path` sets the directory recorded in `StylesPath` inside the
  archive (defaults to `styles`). The same value controls where style files are
  emitted in the ZIP.
- `--force` overwrites an existing archive in the output directory.
- Environment variables with the `STILYAGI_` prefix should be set when running
  under CI. For example, `STILYAGI_VERSION` mirrors `--archive-version`,
  `STILYAGI_STYLE` accepts a comma-separated list of style names, and
  `STILYAGI_INI_STYLES_PATH` mirrors `--ini-styles-path`.

### Verifying the artefact locally

1. Regenerate the archive via `uv run stilyagi zip --force`.
2. Unzip the resulting file and inspect `.vale.ini` to confirm it references the
   expected style list and vocabulary.
3. Validate the package inside a consumer repository by temporarily
   pointing `.vale.ini`'s `Packages` entry at `dist/<archive>.zip` (use an
   absolute path when the consumer lives elsewhere), then run `vale sync`.

## Installing Concordat with `stilyagi install`

`stilyagi install <owner>/<repo>` fetches the latest GitHub release metadata
and rewrites `.vale.ini` so `vale sync` downloads the tagged Concordat package.
The command preserves an existing `StylesPath` (defaulting to `.vale/styles` to
keep downloads out of the tracked `styles/` tree), pins the `Packages` entry to
the archive, raises `MinAlertLevel` to `warning`, and records the
Concordat-focused targets for docs, code, and the README.

Example workflow:

1. `uv run stilyagi install leynos/concordat-vale`
2. `make vale`

Useful options:

- `--config-path` (`STILYAGI_CONFIG_PATH`) writes to an alternate config file.
- `--styles-path` (`STILYAGI_STYLES_PATH`) forces a specific `StylesPath`
  value.
- `--api-base` (`STILYAGI_API_BASE`) points at a mock GitHub API during tests.
- `--token`, `STILYAGI_TOKEN`, or `GITHUB_TOKEN` authenticates API requests
  when rate limits are tight.

The resulting `.vale.ini` resembles:

```ini
StylesPath = .vale/styles
Packages = https://github.com/leynos/concordat-vale/releases/download/v0.1.0/concordat-0.1.0.zip
MinAlertLevel = warning
Vocab = concordat

[docs/**/*.{md,markdown,mdx}]
BasedOnStyles = concordat
# Ignore for footnotes
BlockIgnores = (?m)^\[\^\d+\]:[^\n]*(?:\n[ \t]+[^\n]*)*

[AGENTS.md]
BasedOnStyles = concordat

[*.{rs,ts,js,sh,py}]
BasedOnStyles = concordat
concordat.RustNoRun = NO
concordat.Acronyms = NO

# README.md may use first/second person pronouns
[README.md]
BasedOnStyles = concordat
concordat.Pronouns = NO
```

## Release

The `release` GitHub Actions workflow at `.github/workflows/release.yml` keeps
the Concordat Vale package in sync with tagged releases. It runs whenever a
GitHub release is published or when a maintainer manually dispatches the
workflow. The job resolves the correct archive version, installs the UV tool
chain, packages the styles with `stilyagi zip --archive-version <version>`, and
publishes the resulting ZIP straight to the matching release.

### Workflow overview

1. Trigger: either publishing a GitHub release (`release.published`) or a
   manual `workflow_dispatch`. Dispatchers must provide an existing release tag
   (for example `v0.1.0`) and may override the archive version.
2. Metadata: the `Resolve release metadata` step reads the event payload (or
   the dispatch inputs) to derive `tag` and `version`. When `archive_version`
   is omitted, the workflow strips the leading `v`/`V` from the tag and uses
   what remains.
3. Packaging: dependencies are installed via `uv sync --group dev --frozen`,
   then `uv run stilyagi zip --force` emits `dist/concordat-<version>.zip` and
   records the artefact path for later steps.
4. Upload: `gh release upload` attaches the freshly generated archive to the
   release that supplied the tag, replacing any older asset with the same name.

### Triggering a new Concordat release

1. Update `pyproject.toml` with the desired semantic version, document the
   changes, and land the pull request.
2. Create and push an annotated tag that matches the published version
   (for example
   `git tag -a v0.2.0 -m "Concordat v0.2.0" && git push origin v0.2.0`).
3. Draft a GitHub release that references the tag, add the release notes, and
   press **Publish release**. Publishing automatically starts the workflow and
   attaches `concordat-0.2.0.zip` to the release once it finishes.
4. To re-run the packaging step (for example if an upload was removed), open
   the workflow’s **Run workflow** form, supply the same `release_tag`, and
   optionally pass a replacement `archive_version`.

## Consuming the Concordat Vale style

Run `stilyagi install leynos/concordat-vale` in the consumer repository to pin
`.vale.ini` to the freshest release, then `make vale` to sync and lint. The
generated config enables Concordat for Markdown and MDX under `docs/`, for
`AGENTS.md`, for common source files, and for `README.md` while relaxing
pronoun checks there. `MinAlertLevel` is raised to `warning` to surface issues
earlier in CI.

### Example `vale` Makefile target

```makefile
VALE ?= vale

.PHONY: vale
vale: $(VALE)
	$(VALE) sync
	$(VALE) --no-global .
```

`vale --no-global .` forces Vale to respect the repository’s `.vale.ini` only
and lints the full tree after syncing packages.

### Local linting workflow for this repository

This repository ships the generated `.vale.ini` shown above. Running
`make vale` downloads the tagged Concordat release into `.vale/styles` and
lints the entire repository with the documented overrides.

If you need repository-specific acronyms, run
`uv run --script scripts/update_acronym_allowlist.py` after `vale sync`; the
script rewrites the packaged `AcronymsFirstUse.tengo` allow list in place.

#### Project-specific acronyms

The `.config/common-acronyms` file stores one acronym per line. Lines beginning
with `#` (comments) and blank lines are ignored, and entries are normalised to
uppercase. Update this list whenever Concordat documentation introduces a new
acronym that should bypass the first-use check. For example:

```plaintext
# Most documents use these abbreviations without expansion.
CI
CD
OKR
SLA
SLO
```

`scripts/update_acronym_allowlist.py` deduplicates the entries, skips values
already baked into Concordat’s base allow list, and rewrites the
`allow := { ... }` map in `AcronymsFirstUse.tengo`. The script is idempotent,
so editing the acronym file and rerunning `make vale` re-synchronises the map
without leaving merge conflicts in the generated Tengo source.
