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
- The `install` sub-command wires a consumer repository for Concordat by
  fetching the latest GitHub release (unless `--release-version`/`--tag` is
  supplied), writing the required `Packages`, `MinAlertLevel`, `Vocab`, and
  section entries to `.vale.ini`, and ensuring a `vale` Makefile target that
  syncs, runs any manifest-defined post-sync steps, then lints. The style name
  is derived from the repository name with a permissive `-vale` suffix strip so
  it remains usable when the archive is named `concordat-<version>.zip`.
- `update-tengo-map` provides a generic way to merge entries into a named Tengo
  map (defaulting to `allow`). It trims comments/blank lines in the source
  file, supports boolean, string, and numeric value parsing via `--type`, and
  rewrites the map in place while preserving existing entries not mentioned in
  the source.

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
- `--vocabulary` overrides automatic vocabulary detection. When a single
  directory exists at `styles/config/vocabularies`, it is used automatically
  (currently `concordat`).
- `--force` opts into overwriting an existing archive to shelter users from
  accidental data loss.

## Generated `.vale.ini`

- Defaults to `StylesPath = styles`, but honours the CLI/environment override
  so packages can opt into custom directory names without post-processing.
- Records `Vocab = <name>` only when a vocabulary is chosen, so consumers are
  not forced to create placeholder directories.
- Purposefully omits `BasedOnStyles` and `[pattern]` sections so consumers can
  decide how to wire the packaged rules into their local config.

## Archive layout & naming

- The archive embeds the entire `styles/` tree (including `config/`) and a
  generated `.vale.ini` at the root. This mirrors the workflow depicted in the
  packaging guide and keeps auxiliary assets with their rules.
- Archives are written to `<output-dir>/<style-names-joined>-<version>.zip`. The
  joined style names keep the filename descriptive without requiring extra CLI
  flags.
- When a `stilyagi.toml` file exists in the project root, `zip` copies it into
  the archive root so downstream installs have a source of truth for default
  settings.

## stilyagi.toml manifest

- Lives at the repository root alongside `styles/` and is packaged when
  present. The manifest is intended to be a single source of truth for install
  defaults as the rule set evolves.
- The `install` command downloads the packaged archive, extracts
  `stilyagi.toml`, and uses it to derive install-time defaults. Missing or
  unreadable manifests fall back to the prior hard-coded defaults to keep the
  command resilient to transient network issues.
- Current fields live under an `[install]` table:
  - `style_name` (default: repo-derived) controls the `BasedOnStyles` and
    per-style option prefixes.
  - `vocab` (default: `style_name`) allows vocabularies to diverge from style
    names when needed.
  - `min_alert_level` (default: `warning`) controls the root `MinAlertLevel`
    written into the consumer `.vale.ini`.
  - `post_sync_steps` (default: `[]`) is an array of tables describing trusted
    actions to run after `vale sync` and before linting. The only structured
    action today is `update-tengo-map`, which renders a fixed
    `uv run stilyagi update-tengo-map --source <src> --dest <dest> --type <t>`
    command. Unknown actions, invalid value types, or non-table entries are
    rejected at parse time.
- Setting the environment variable `STILYAGI_SKIP_MANIFEST_DOWNLOAD=1` skips
  manifest retrieval and falls back to the built-in defaults. This keeps tests
  and offline workflows deterministic while retaining manifest support for real
  installs.

## Testing strategy

- Unit tests exercise `package_styles` directly to verify `.vale.ini`
  generation, vocabulary selection, rejection of missing directories, and both
  overwrite paths (`--force` and refusal without it).
- Behavioural tests (`pytest-bdd`) exercise the CLI end-to-end by running
  `python -m concordat_vale.stilyagi zip` against a staged copy of the real
  `styles/` tree. Scenarios now cover successful packaging plus environment
  overrides, asserting that the archive contains both the rules/config and that
  the generated `.vale.ini` only exposes the core settings. Direct subprocess
  tests validate error reporting and exit codes.
