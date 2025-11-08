# Stilyagi design

## Purpose

- Provide a reproducible zip builder for the Vale assets shipped in `styles/`.
- Include a self-contained `.vale.ini` so consumers can `vale sync` the archive
  without extra wiring.
- Follow the scripting standards by centring Cyclopts and environment-first
  configuration.

## CLI surface

- `stilyagi` is exposed via `pyproject.toml` as an entry point that calls
  `concordat_vale.stilyagi:main`.
- Cyclopts drives the CLI with an `STILYAGI_` environment prefix, so every flag
  can also be injected via CI inputs.
- The `zip` sub-command is focused on packaging. Other automation should be
  added as additional sub-commands rather than new binaries.

### Parameters

- `--project-root` defaults to `.` and anchors every relative path, so the CLI
  can be run from outside the repository.
- `--styles-path` defaults to `styles`. The command auto-discovers style
  directories under that path (excluding `config`) unless `--style` is
  specified.
- `--style` is repeatable and allows packaging a subset of styles when more are
  added later. When omitted, discovery keeps the tool zero-config for the
  single `concordat` style that exists today.
- `--output-dir` defaults to `dist` so artefacts do not clutter the repo root.
- `--ini-styles-path` defaults to `styles` and sets both the `StylesPath`
  entry inside `.vale.ini` and the directory name used for archived files. This
  keeps the exported structure aligned with consumer expectations while still
  permitting alternative layouts.
- `--archive-version` overrides the archive suffix. When omitted, the tool reads
  the `project.version` from `pyproject.toml`, then falls back to the installed
  distribution metadata, and finally to `0.0.0+unknown`. This keeps ad-hoc runs
  reproducible while surfacing the configured release version under normal use.
- `--target-glob` changes the `[<glob>]` header written to `.vale.ini` without
  forcing users to edit templates by hand. The default matches Markdown,
  AsciiDoc, and plain text.
- `--vocabulary` overrides automatic vocabulary detection. When a single
  directory exists at `styles/config/vocabularies`, it is used automatically
  (currently `concordat`).
- `--force` opts into overwriting an existing archive to shelter users from
  accidental data loss.

## Generated `.vale.ini`

- Defaults to `StylesPath = styles`, but honours the CLI/environment override
  so packages can opt into custom directory names without post-processing.
- Injects `BasedOnStyles` using the discovered style directory names, so the
  value remains consistent with Vale's casing rules or any explicit `--style`
  values coming from `STILYAGI_STYLE`.
- Records `Vocab = <name>` only when a vocabulary is chosen, so consumers are
  not forced to create placeholder directories.

## Archive layout & naming

- The archive embeds the entire `styles/` tree (including `config/`) and a
  generated `.vale.ini` at the root. This mirrors the workflow depicted in the
  packaging guide and keeps auxiliary assets with their rules.
- Archives are written to `<output-dir>/<style-names-joined>-<version>.zip`. The
  joined style names keep the filename descriptive without requiring extra CLI
  flags.

## Testing strategy

- Unit tests exercise `package_styles` directly to verify `.vale.ini`
  generation, vocabulary selection, rejection of missing directories, and both
  overwrite paths (`--force` and refusal without it).
- Behavioural tests (`pytest-bdd`) exercise the CLI end-to-end by running
  `python -m concordat_vale.stilyagi zip` against a staged copy of the real
  `styles/` tree. Scenarios now cover successful packaging plus environment
  overrides, and they assert that the archive contains both the rules and
  configuration assets, and that the generated `.vale.ini` references the
  `concordat` style. Direct subprocess tests validate error reporting and exit
  codes.
