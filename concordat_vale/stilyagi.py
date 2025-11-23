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

from .tengo_map import (
    MapValueType,
    TengoMapError,
    parse_source_entries,
    update_tengo_map,
)

DEFAULT_OUTPUT_DIR = Path("dist")
DEFAULT_STYLES_PATH = Path("styles")
DEFAULT_MAP_NAME = "allow"
ENV_PREFIX = "STILYAGI_"
PACKAGE_NAME = "concordat-vale"

app = App()
app.help = "Utilities for packaging and distributing Vale styles."
app.config = cyclopts.config.Env(ENV_PREFIX, command=False)
# Disable Cyclopts' auto-print (which wraps long lines) and print manually instead.
app.result_action = "return_value"


def _split_comma_env(
    _hint: object,
    value: str,
    *,
    delimiter: str | None = ",",
) -> list[str]:
    """Split a delimiter-separated environment variable into cleaned tokens."""
    sep = delimiter or ","
    return [token.strip() for token in value.split(sep) if token.strip()]


def _resolve_project_path(root: Path, candidate: Path) -> Path:
    """Return an absolute path for *candidate* anchored at *root* when needed."""
    return (
        candidate.expanduser().resolve()
        if candidate.is_absolute()
        else (root / candidate).resolve()
    )


def _split_dest(dest: str) -> tuple[Path, str]:
    """Split ``dest`` into a filesystem path and map name."""
    path_part, _, map_suffix = dest.partition("::")
    if not path_part:
        msg = "Destination must include a Tengo script path."
        raise ValueError(msg)
    map_name = map_suffix or DEFAULT_MAP_NAME
    return Path(path_part), map_name


def _coerce_value_type(raw: str) -> MapValueType:
    """Convert raw CLI input into a MapValueType."""
    try:
        return MapValueType(raw)
    except ValueError as exc:
        msg = (
            "Invalid --type value. Choose from "
            f"{', '.join(choice.value for choice in MapValueType)}."
        )
        raise TengoMapError(msg) from exc


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

    if pyproject_version := _read_pyproject_version(root):
        return pyproject_version

    try:
        return metadata.version(PACKAGE_NAME)
    except metadata.PackageNotFoundError:
        return "0.0.0+unknown"


def _discover_style_names(styles_root: Path, explicit: list[str] | None) -> list[str]:
    if explicit:
        unique = sorted(dict.fromkeys(explicit))
        missing = [name for name in unique if not (styles_root / name).is_dir()]
        if missing:
            missing_list = ", ".join(missing)
            msg = f"Styles not found under {styles_root}: {missing_list}"
            raise FileNotFoundError(msg)
        return unique

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
    return names[0] if len(names) == 1 else None


def _build_ini(
    styles_path_entry: str,
    vocabulary: str | None,
) -> str:
    lines = [f"StylesPath = {styles_path_entry}"]
    if vocabulary:
        lines.append(f"Vocab = {vocabulary}")
    # Preserve a trailing newline for readability and Vale compatibility.
    lines.append("")
    return "\n".join(lines)


def _add_styles_to_archive(
    zip_file: ZipFile,
    styles_root: Path,
    archive_root: Path,
    styles: list[str],
) -> None:
    if archive_root.is_absolute():
        msg = "StylesPath inside the archive must be a relative directory"
        raise ValueError(msg)

    include_dirs = [styles_root / name for name in styles]
    config_dir = styles_root / "config"
    if config_dir.exists():
        include_dirs.append(config_dir)

    for directory in include_dirs:
        for path in sorted(directory.rglob("*")):
            if path.is_dir():
                continue
            archive_path = archive_root / path.relative_to(styles_root)
            zip_file.write(path, arcname=str(archive_path))


def package_styles(
    *,
    project_root: Path,
    styles_path: Path,
    output_dir: Path,
    version: str,
    explicit_styles: list[str] | None,
    vocabulary: str | None,
    ini_styles_path: str = "styles",
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
    ini_contents = _build_ini(ini_styles_path, vocab)

    resolved_output = _resolve_project_path(resolved_root, output_dir)
    resolved_output.mkdir(parents=True, exist_ok=True)
    filename_stem = "-".join(styles)
    archive_path = resolved_output / f"{filename_stem}-{version}.zip"
    if archive_path.exists() and not force:
        msg = f"Archive {archive_path} already exists; rerun with --force to overwrite"
        raise FileExistsError(msg)

    archive_dir = Path(f"{filename_stem}-{version}")
    ini_member = archive_dir / ".vale.ini"
    archive_root = archive_dir / Path(ini_styles_path)
    with ZipFile(archive_path, mode="w", compression=ZIP_DEFLATED) as archive:
        archive.writestr(str(ini_member), ini_contents)
        _add_styles_to_archive(
            archive,
            resolved_styles,
            archive_root,
            styles,
        )

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
    ini_styles_path: typ.Annotated[
        str,
        Parameter(
            help="Directory name recorded in StylesPath inside the archive.",
            env_var="STILYAGI_INI_STYLES_PATH",
        ),
    ] = "styles",
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
        ini_styles_path=ini_styles_path,
        force=force,
    )
    print(archive_path)
    # Keep returning the string for programmatic callers.
    return str(archive_path)


@app.command(name="update-tengo-map")
def update_tengo_map_command(
    source: typ.Annotated[Path, Parameter(help="Path to the source entries file.")],
    dest: typ.Annotated[
        str,
        Parameter(
            help=(
                "Tengo script path; append ::mapname to target a different map."
                f" When no suffix is provided, the {DEFAULT_MAP_NAME!r} map"
                " is used."
            )
        ),
    ],
    project_root: typ.Annotated[
        Path, Parameter(help="Root directory for resolving relative paths.")
    ] = Path(),
    value_type: typ.Annotated[
        str,
        Parameter(
            name="type",
            help="Value parsing mode: true, =, =b, or =n.",
        ),
    ] = MapValueType.TRUE.value,
) -> str:
    """Update a Tengo map with entries from a source list.

    Parameters
    ----------
    source : Path
        Path to the input file containing map entries (one per line).
    dest : str
        Destination Tengo script path, optionally suffixed with ``::mapname``;
        defaults to the ``allow`` map when no suffix is provided.
    project_root : Path, optional
        Root directory used to resolve relative ``source`` and ``dest`` paths.
    value_type : str, optional
        Value parsing mode: ``true`` (keys only), ``=``, ``=b``, or ``=n``;
        defaults to ``true``.

    Returns
    -------
    str
        Summary message reporting entries provided and updated counts.

    Raises
    ------
    SystemExit
        If inputs are missing, malformed, or I/O operations fail.
    """
    resolved_root = project_root.expanduser().resolve()
    resolved_source = _resolve_project_path(resolved_root, source)

    try:
        dest_path, map_name = _split_dest(dest)
        resolved_dest = _resolve_project_path(resolved_root, dest_path)
        map_value_type = _coerce_value_type(value_type)

        entries_provided, entries = parse_source_entries(
            resolved_source, map_value_type
        )
        result = update_tengo_map(resolved_dest, map_name, entries)
    except (FileNotFoundError, TengoMapError, ValueError, OSError) as exc:
        raise SystemExit(str(exc)) from exc

    message = f"{entries_provided} entries provided, {result.updated} updated"

    print(message)
    return message


def main() -> None:
    """Invoke the Cyclopts application."""
    app()


if __name__ == "__main__":
    main()
