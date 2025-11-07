# Usage guide

## Packaging the Vale style with `stilyagi`

- Run `uv sync --group dev` (or `make build`) once so the `stilyagi` entry
  point is available locally.
- Invoke `stilyagi zip` from the repository root to create a distributable ZIP
  that contains `.vale.ini` plus the full `styles/` tree.

### Default workflow

1. `make build` (installs dependencies when needed).
2. `uv run stilyagi zip`
3. Retrieve the archive from `dist/concordat-<version>.zip` and attach it to
   the release you are preparing.

Running the command without flags auto-discovers available styles and the sole
vocabulary (`concordat`). The `.vale.ini` header matches `[*.{md,adoc,txt}]` to
cover Markdown, AsciiDoc, and text files.

### Customisation

- Use `--archive-version` to override the archive suffix (for example,
  `uv run stilyagi zip --archive-version 2025.11.07`). When omitted, the value
  from `pyproject.toml` is used.
- Use `--style` (repeatable) to limit the archive to specific style directories
  when more styles are added later. Without this flag every non-config style in
  `styles/` is included.
- Use `--output-dir` to change the destination directory (defaults to `dist`).
- Use `--project-root` when running the command from outside the repository (the
  path anchors every other relative argument).
- Use `--force` to overwrite an existing archive in the output directory.
- Set environment variables with the `STILYAGI_` prefix when running under CI.
  For example, `STILYAGI_VERSION` mirrors `--archive-version`, and
  `STILYAGI_STYLE` accepts a comma-separated list of style names.

### Verifying the artefact locally

1. Run `uv run stilyagi zip --force` to regenerate the archive.
2. Unzip the resulting file and inspect `.vale.ini` to confirm it references the
   expected style list and vocabulary.
3. Run `vale sync --packages dist/<archive>.zip` inside a consumer repository to
   validate that Vale accepts the package.
