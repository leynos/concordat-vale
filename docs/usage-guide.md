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
3. Validate the package inside a consumer repository by running
   `vale sync --packages dist/<archive>.zip`.
