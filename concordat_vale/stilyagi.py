#!/usr/bin/env -S uv run python
# /// script
# requires-python = ">=3.13"
# dependencies = ["cyclopts>=2.9"]
# ///

"""Cyclopts-powered CLI for packaging Concordat Vale styles into ZIPs."""

from __future__ import annotations

import tomllib
import typing as typ
from importlib import metadata
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import cyclopts
from cyclopts import App, Parameter

DEFAULT_OUTPUT_DIR = Path("dist")
DEFAULT_STYLES_PATH = Path("styles")
DEFAULT_TARGET_GLOB = "*.{md,adoc,txt}"
ENV_PREFIX = "STILYAGI_"
PACKAGE_NAME = "concordat-vale"

app = App()
app.help = "Utilities for packaging and distributing Vale styles."
app.config = cyclopts.config.Env(ENV_PREFIX, command=False)


def _split_comma_env(value: str) -> list[str]:
    """Split a comma-separated environment variable into cleaned tokens."""
    return [token.strip() for token in value.split(",") if token.strip()]


def _resolve_project_path(root: Path, candidate: Path) -> Path:
    """Return an absolute path for *candidate* anchored at *root* when needed."""
    return (
        candidate.expanduser().resolve()
        if candidate.is_absolute()
        else (root / candidate).resolve()
    )


def _read_pyproject_version(root: Path) -> str | None:
    pyproject_path = root / "pyproject.toml"
    if not pyproject_path.exists():
        return None
    data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    project = data.get("project", {})
    raw_version = project.get("version")
    if isinstance(raw_version, str) and raw_version.strip():
        return raw_version.strip()
    return None


def _resolve_version(root: Path, override: str | None) -> str:
    if override:
        return override

    pyproject_version = _read_pyproject_version(root)
    if pyproject_version:
        return pyproject_version

    try:
        return metadata.version(PACKAGE_NAME)
    except metadata.PackageNotFoundError:
        return "0.0.0+unknown"


def _discover_style_names(styles_root: Path, explicit: list[str] | None) -> list[str]:
    if explicit:
        return sorted(dict.fromkeys(explicit))

    discovered: list[str] = []
    for entry in sorted(styles_root.iterdir()):
        if not entry.is_dir():
            continue
        if entry.name == "config":
            continue
        discovered.append(entry.name)

    if not discovered:
        msg = f"No styles found under {styles_root}"
        raise RuntimeError(msg)

    return discovered


def _select_vocabulary(styles_root: Path, override: str | None) -> str | None:
    if override:
        return override

    vocab_root = styles_root / "config" / "vocabularies"
    if not vocab_root.exists():
        return None

    names = sorted(entry.name for entry in vocab_root.iterdir() if entry.is_dir())
    if len(names) == 1:
        return names[0]

    return None


def _build_ini(
    styles: list[str],
    target_glob: str,
    vocabulary: str | None,
) -> str:
    based_on = ", ".join(styles)
    body = [
        "StylesPath = styles",
        "",
        f"[{target_glob}]",
        f"BasedOnStyles = {based_on}",
    ]
    if vocabulary:
        body.append(f"Vocab = {vocabulary}")
    body.append("")
    return "\n".join(body)


def _add_styles_to_archive(zip_file: ZipFile, styles_root: Path) -> None:
    for path in sorted(styles_root.rglob("*")):
        if path.is_dir():
            continue
        archive_path = Path("styles") / path.relative_to(styles_root)
        zip_file.write(path, arcname=str(archive_path))


def package_styles(
    *,
    project_root: Path,
    styles_path: Path,
    output_dir: Path,
    version: str,
    explicit_styles: list[str] | None,
    vocabulary: str | None,
    target_glob: str,
    force: bool,
) -> Path:
    """Create a Vale-ready ZIP archive containing styles and config."""
    resolved_root = project_root.expanduser().resolve()
    resolved_styles = _resolve_project_path(resolved_root, styles_path)
    if not resolved_styles.exists():
        msg = f"Styles directory {resolved_styles} does not exist"
        raise FileNotFoundError(msg)

    styles = _discover_style_names(resolved_styles, explicit_styles)
    vocab = _select_vocabulary(resolved_styles, vocabulary)
    ini_contents = _build_ini(styles, target_glob, vocab)

    resolved_output = _resolve_project_path(resolved_root, output_dir)
    resolved_output.mkdir(parents=True, exist_ok=True)
    filename_stem = "-".join(styles)
    archive_path = resolved_output / f"{filename_stem}-{version}.zip"
    if archive_path.exists() and not force:
        msg = f"Archive {archive_path} already exists; rerun with --force to overwrite"
        raise FileExistsError(msg)

    with ZipFile(archive_path, mode="w", compression=ZIP_DEFLATED) as archive:
        archive.writestr(".vale.ini", ini_contents)
        _add_styles_to_archive(archive, resolved_styles)

    return archive_path


@app.command(name="zip")
def zip_command(
    *,
    project_root: typ.Annotated[
        Path, Parameter(help="Root of the repository containing styles.")
    ] = Path(),
    styles_path: typ.Annotated[
        Path, Parameter(help="Path (relative to project root) for styles content.")
    ] = DEFAULT_STYLES_PATH,
    output_dir: typ.Annotated[
        Path, Parameter(help="Directory for generated ZIP archives.")
    ] = DEFAULT_OUTPUT_DIR,
    style: typ.Annotated[
        list[str] | None,
        Parameter(
            help="Specific style directory names to include.",
            env_var_split=_split_comma_env,
        ),
    ] = None,
    vocabulary: typ.Annotated[
        str | None,
        Parameter(help="Override the vocabulary name recorded in .vale.ini."),
    ] = None,
    target_glob: typ.Annotated[
        str, Parameter(help="Vale file glob inside .vale.ini, without brackets.")
    ] = DEFAULT_TARGET_GLOB,
    archive_version: typ.Annotated[
        str | None,
        Parameter(
            help="Version identifier embedded in the archive filename.",
            env_var="STILYAGI_VERSION",
        ),
    ] = None,
    force: typ.Annotated[
        bool, Parameter(help="Overwrite an existing archive if present.")
    ] = False,
) -> str:
    """CLI entry point that writes the archive path to stdout."""
    archive_path = package_styles(
        project_root=project_root,
        styles_path=styles_path,
        output_dir=output_dir,
        version=_resolve_version(project_root.expanduser().resolve(), archive_version),
        explicit_styles=style,
        vocabulary=vocabulary,
        target_glob=target_glob,
        force=force,
    )
    print(archive_path)
    return str(archive_path)


def main() -> None:
    """Invoke the Cyclopts application."""
    app()


if __name__ == "__main__":
    main()
