# Concordat Vale style

Concordat Vale bundles the Concordat prose style, vocabulary, and helper
scripts for the Vale 3 linter. It also ships the `stilyagi` commands used to
package and install the style, so teams can sync a single ZIP in their own
repositories.

## Quick start

- Install the tooling once with `uv sync --group dev` or `make build`.
- Create a distributable archive via `uv run stilyagi zip`; the ZIP lands in
  `dist/concordat-<version>.zip`.
- Install the latest release into another repository with
  `uv run stilyagi install leynos/concordat-vale`, which rewrites `.vale.ini`
  and adds a `vale` Makefile target for you.
- Need fuller instructions? The usage flow, flags, and examples live in
  `docs/users-guide.md`.

## Repository layout

- `styles/` – Concordat Vale rules plus shared config (`scripts/`, `actions/`,
  `vocabularies/`).
- `.vale.ini` – Reference config that ships inside the packaged ZIP.
- `stilyagi.toml` – Manifest that defines defaults for installers
  (style name, vocabulary, alert level, and post-sync steps).
- `concordat_vale/` – Python package implementing `stilyagi zip`,
  `stilyagi install`, and Tengo map helpers.
- `docs/` – How-to guides, design notes, and local validation tips; the
  primary entry point is `docs/users-guide.md`.
- `features/` and `tests/` – Behavioural and unit coverage for the CLI,
  packaging flow, and Tengo map generation.
- `dist/` – Locally built ZIP artefacts ready to upload to a release.

## Common tasks

- Build and package: `make build` then `uv run stilyagi zip --force` when you
  need to refresh the archive.
- Run checks: `make test`, `make lint`, `make check-fmt`, and
  `make typecheck` keep the package healthy before tagging a release.
- Update vocabulary or scripts: edit files under `styles/config/`, then
  regenerate the ZIP and rerun the test suite.

## Further help

- `docs/users-guide.md` – detailed usage, install flags, and release
  workflows.
- `docs/packaging-a-vale-style-as-a-zip.md` – background on the ZIP layout and
  how Vale resolves scripts, actions, and vocabulary.
- `docs/stilyagi-design.md` – design decisions behind the installer and
  packaging commands.

If you spot gaps or have questions, open an issue so we can improve the
onboarding experience together.
