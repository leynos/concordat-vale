#!/usr/bin/env -S uv run python
# /// script
# requires-python = ">=3.13"
# dependencies = ["cyclopts>=2.9"]
# ///

"""Cyclopts-powered CLI for packaging and installing Concordat Vale styles.

The ``zip`` sub-command packages styles into distributable ZIP archives, and
the ``install`` sub-command wires a packaged Concordat style into an external
repository by updating its ``.vale.ini`` and Makefile.
"""

from __future__ import annotations

import os
import typing as typ
from pathlib import Path

import cyclopts
from cyclopts import App, Parameter

from .stilyagi_install import (
    InstallConfig,
    _parse_repo_reference,
    _perform_install,
    _resolve_install_paths,
    _update_makefile,
    _update_vale_ini,
)
from .stilyagi_packaging import (
    DEFAULT_OUTPUT_DIR,
    DEFAULT_STYLES_PATH,
    PackagingPaths,
    StyleConfig,
    _resolve_version,
    package_styles,
)
from .tengo_map import (
    MapValueType,
    TengoMapError,
    parse_source_entries,
    update_tengo_map,
)

DEFAULT_MAP_NAME = "allow"
ENV_PREFIX = "STILYAGI_"

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


def _split_dest(dest: str) -> tuple[Path, str]:
    """Split ``dest`` into a filesystem path and map name."""
    path_part, _, map_suffix = dest.partition("::")
    if not path_part:
        msg = "Destination must include a Tengo script path."
        raise ValueError(msg)
    map_name = map_suffix or DEFAULT_MAP_NAME
    return Path(path_part), map_name


def _validate_path_input(user_path: Path | str) -> Path:
    """Validate user-supplied path is non-empty and relative."""
    path_str = str(user_path).strip()
    if not path_str:
        msg = "Missing file"
        raise ValueError(msg)

    candidate = Path(path_str)
    if candidate.is_absolute():
        msg = "Absolute paths are not allowed"
        raise ValueError(msg)
    return candidate


def _validate_within_base_dir(target: Path, base_dir: Path) -> None:
    """Ensure resolved path remains inside base_dir."""
    base_only = os.path.commonpath([str(base_dir)])
    base_and_target = os.path.commonpath([str(base_dir), str(target)])
    if base_only != base_and_target:
        msg = "Attempt to escape base directory"
        raise ValueError(msg)


def _validate_extension(target: Path, allowed_exts: tuple[str, ...]) -> None:
    """Check target suffix is allowed when a whitelist is provided."""
    if allowed_exts:
        suffix = target.suffix.lower()
        if suffix not in allowed_exts:
            msg = "File type not allowed"
            raise ValueError(msg)


def _validate_file_exists(target: Path) -> None:
    """Ensure the target exists and is a regular file."""
    if not target.exists() or not target.is_file():
        msg = "File not found"
        raise FileNotFoundError(msg)


def _safe_resolve(
    user_path: Path | str,
    *,
    base_dir: Path,
    allowed_exts: tuple[str, ...] = (),
) -> Path:
    """Resolve *user_path* safely within *base_dir*.

    Guards against traversal by rejecting absolute paths, collapsing any ``..``
    segments, ensuring the resolved path stays under *base_dir*, and verifying
    the path exists as a file. When *allowed_exts* is provided, the suffix must
    match (case-insensitive).
    """
    candidate = _validate_path_input(user_path)
    target = (base_dir / candidate).resolve()
    _validate_within_base_dir(target, base_dir)
    _validate_extension(target, allowed_exts)
    _validate_file_exists(target)
    return target


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


@app.command(name="zip")
def zip_command(  # noqa: PLR0913 - CLI command exposes explicit flags for clarity
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
    paths = PackagingPaths(
        project_root=project_root,
        styles_path=styles_path,
        output_dir=output_dir,
    )
    config = StyleConfig(
        explicit_styles=style,
        vocabulary=vocabulary,
        ini_styles_path=ini_styles_path,
    )
    archive_path = package_styles(
        paths=paths,
        config=config,
        version=_resolve_version(project_root.expanduser().resolve(), archive_version),
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
                "Tengo script path; append ::mapname to target a different map. "
                f"When no suffix is provided, the {DEFAULT_MAP_NAME!r} map is"
                " used."
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
    """Update a Tengo map with entries from a source list."""
    resolved_root = project_root.expanduser().resolve()
    resolved_source = _safe_resolve(source, base_dir=resolved_root)

    try:
        dest_path, map_name = _split_dest(dest)
        resolved_dest = _safe_resolve(
            dest_path, base_dir=resolved_root, allowed_exts=(".tengo",)
        )
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


@app.command(name="install")
def install_command(  # noqa: PLR0913 - CLI command exposes explicit flags for clarity
    repo: typ.Annotated[
        str, Parameter(help="GitHub repository reference in owner/name form.")
    ],
    *,
    project_root: typ.Annotated[
        Path,
        Parameter(
            help=(
                "External repository root whose .vale.ini and Makefile will be updated."
            ),
            env_var="STILYAGI_PROJECT_ROOT",
        ),
    ] = Path(),
    vale_ini: typ.Annotated[
        Path,
        Parameter(
            help="Path to the Vale configuration file to update.",
            env_var="STILYAGI_VALE_INI",
        ),
    ] = Path(".vale.ini"),
    makefile: typ.Annotated[
        Path,
        Parameter(
            help="Path to the Makefile that should expose the vale target.",
            env_var="STILYAGI_MAKEFILE",
        ),
    ] = Path("Makefile"),
    release_version: typ.Annotated[
        str | None,
        Parameter(
            help=(
                "Override the release version instead of discovering it from GitHub. "
                "A matching tag of the form v<version> will be used unless"
                " --tag is provided."
            ),
            env_var="STILYAGI_RELEASE_VERSION",
        ),
    ] = None,
    tag: typ.Annotated[
        str | None,
        Parameter(
            help="Override the release tag used in download URLs.",
            env_var="STILYAGI_RELEASE_TAG",
        ),
    ] = None,
) -> str:
    """Install the Concordat style into an external repository."""
    owner, repo_name, style_name = _parse_repo_reference(repo)

    _, ini_path, makefile_path = _resolve_install_paths(
        cwd=Path.cwd(),
        project_root=project_root,
        vale_ini=vale_ini,
        makefile=makefile,
    )
    config = InstallConfig(
        owner=owner,
        repo_name=repo_name,
        style_name=style_name,
        ini_path=ini_path,
        makefile_path=makefile_path,
        override_version=release_version,
        override_tag=tag,
    )
    return _perform_install(config=config)


def main() -> None:
    """Invoke the Cyclopts application."""
    app()


__all__ = [
    "PackagingPaths",
    "StyleConfig",
    "_update_makefile",
    "_update_vale_ini",
    "app",
    "install_command",
    "main",
    "package_styles",
    "update_tengo_map_command",
    "zip_command",
]


if __name__ == "__main__":
    main()
