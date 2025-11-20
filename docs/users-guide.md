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

Releases expose a ready-to-sync ZIP that contains `.vale.ini`, the Concordat
style files, and the supporting vocabulary. Consumers should download the
artefact from <https://github.com/leynos/concordat-vale/releases>, record the
release URL in the consuming repository's `.vale.ini` via `Packages = <url>`,
run `vale sync`, then reference the style in their configuration.

### Example `.vale.ini`

```ini
StylesPath = styles
MinAlertLevel = suggestion
Packages = https://github.com/leynos/concordat-vale/releases/download/v0.1.0/concordat-0.1.0.zip

[*.{md,adoc,txt}]
BasedOnStyles = Vale, concordat
```

This configuration downloads the `v0.1.0` artefact into `styles/` (when
`vale sync` is executed) and enables the Concordat checks for Markdown,
AsciiDoc, and plain-text files alongside Vale’s defaults.

### Example `vale` Makefile target

```makefile
VALE ?= vale
VALE_CONFIG ?= .vale.ini
VALE_TARGETS ?= docs/**/*.md README.md

.PHONY: vale-sync
vale-sync:
	$(VALE) sync --config $(VALE_CONFIG)

.PHONY: vale
vale: vale-sync
	$(VALE) --config $(VALE_CONFIG) --minAlertLevel suggestion $(VALE_TARGETS)
```

Running `make vale` synchronises whatever packages are listed in
`$(VALE_CONFIG)` before linting the selected documentation paths. Update the
`Packages` entry in that configuration (or point `VALE_CONFIG` at an
alternative file) to pin a different release URL, and adjust `VALE_TARGETS` to
match the files in your repository.

### Local linting workflow for this repository

This repository ships a `.vale.ini` that points `StylesPath` at `.vale/styles`
and references the locally built archive `dist/concordat-dev.zip`. Running
`make vale` orchestrates the following steps:

1. `make vale-archive` rebuilds the development archive via
   `uv run stilyagi zip --archive-version dev --force`.
2. `make vale-sync` invokes `vale sync --config .vale.ini` to unpack the
   archive into `.vale/styles`.
3. `scripts/update_acronym_allowlist.py` reads `.config/common-acronyms` and
   injects those entries into
   `.vale/styles/config/scripts/AcronymsFirstUse.tengo`.
4. `vale --config .vale.ini --minAlertLevel suggestion $(VALE_TARGETS)` lints
   `README.md` plus every Markdown and AsciiDoc file under `docs/`.

Running the helper script immediately after `vale sync` ensures the packaged
`AcronymsFirstUse.tengo` always includes the repository-specific acronyms
before linting begins.

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

### Updating Tengo maps with `stilyagi`

- `stilyagi update-tengo-map` merges entries from a source file into a Tengo
  map. The `--dest` argument accepts a Tengo script path plus an optional map
  suffix (for example, `scripts/AcronymsFirstUse.tengo::allow`). When the
  suffix is omitted, the `allow` map is targeted.
- `--source` points at the list of entries. Blank lines and lines that start
  with `#` are ignored, and any text after whitespace and an optional `#` is
  stripped.
- `--type` defaults to `true`, which writes every entry as `"key": true`. Use
  `=` to write string values (splitting on the first `=` per line), `=b` to
  coerce booleans, and `=n` for numeric values.
- The command exits after printing a concise summary such as
  `2 entries provided, 1 updated`.
- Example: to inject local acronyms without the helper script, run:

  ```bash
  uv run stilyagi update-tengo-map \
    --source .config/common-acronyms \
    --dest .vale/styles/config/scripts/AcronymsFirstUse.tengo
  ```
