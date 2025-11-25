r"""Packaging helpers for the stilyagi CLI.

This module builds distributable ZIP archives of Concordat Vale styles.
It exposes:

- ``PackagingPaths``: filesystem locations for the project, styles, and output
  directory.
- ``StyleConfig``: style selection, vocabulary, and StylesPath configuration.
- ``package_styles``: orchestrates resolution, INI rendering, and archive
  creation.

Example
-------
>>> paths = PackagingPaths(Path(\".\"), Path(\"styles\"), Path(\"dist\"))
>>> config = StyleConfig()
>>> package_styles(paths=paths, config=config, version=\"1.0.0\", force=False)
PosixPath('.../dist/concordat-vale-1.0.0.zip')
"""

from __future__ import annotations

import dataclasses as dc
import tomllib
from importlib import metadata
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


@dc.dataclass
class PackagingPaths:
    """Encapsulates file system paths for packaging operation.

    Parameters
    ----------
    project_root:
        Root directory of the project containing styles.
    styles_path:
        Relative or absolute path to the styles directory.
    output_dir:
        Directory where the packaged archive will be written.
    """

    project_root: Path
    styles_path: Path
    output_dir: Path


@dc.dataclass
class StyleConfig:
    """Encapsulates style selection and configuration options.

    Parameters
    ----------
    explicit_styles:
        Optional list of styles to include; discover all if absent.
    vocabulary:
        Optional vocabulary name to embed in the generated .vale.ini.
    ini_styles_path:
        Path written to StylesPath within the packaged .vale.ini.
    """

    explicit_styles: list[str] | None = None
    vocabulary: str | None = None
    ini_styles_path: str = "styles"


PACKAGE_NAME = "concordat-vale"
DEFAULT_OUTPUT_DIR = Path("dist")
DEFAULT_STYLES_PATH = Path("styles")


def _resolve_project_path(root: Path, candidate: Path) -> Path:
    """Return an absolute path for *candidate* anchored at *root* when needed."""
    return (
        candidate.expanduser().resolve()
        if candidate.is_absolute()
        else (root / candidate).resolve()
    )


def _read_pyproject_version(root: Path) -> str | None:
    """Read the version from pyproject.toml if present."""
    pyproject_path = root / "pyproject.toml"
    if not pyproject_path.exists():
        return None
    data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    project = data.get("project", {})
    raw_version = project.get("version")
    match raw_version:
        case str(v) if v.strip():
            return v.strip()
        case _:
            return None


def _resolve_version(root: Path, override: str | None) -> str:
    """Resolve archive version from override, pyproject, or installed metadata."""
    if override:
        return override

    if pyproject_version := _read_pyproject_version(root):
        return pyproject_version

    try:
        return metadata.version(PACKAGE_NAME)
    except metadata.PackageNotFoundError:
        return "0.0.0+unknown"


def _validate_explicit_styles(styles_root: Path, explicit: list[str]) -> list[str]:
    """Validate that explicitly requested styles exist."""
    unique = sorted(dict.fromkeys(explicit))
    if missing := [name for name in unique if not (styles_root / name).is_dir()]:
        missing_list = ", ".join(missing)
        msg = f"Styles not found under {styles_root}: {missing_list}"
        raise FileNotFoundError(msg)
    return unique


def _discover_available_styles(styles_root: Path) -> list[str]:
    """Discover all available styles by scanning the styles directory."""
    discovered = [
        entry.name
        for entry in sorted(styles_root.iterdir())
        if entry.is_dir() and entry.name != "config"
    ]

    if not discovered:
        msg = f"No styles found under {styles_root}"
        raise RuntimeError(msg)

    return discovered


def _discover_style_names(styles_root: Path, explicit: list[str] | None) -> list[str]:
    """Return explicit styles if provided, otherwise discover all available styles."""
    if explicit:
        return _validate_explicit_styles(styles_root, explicit)
    return _discover_available_styles(styles_root)


def _select_vocabulary(styles_root: Path, override: str | None) -> str | None:
    """Select vocabulary to embed, preferring explicit override when provided."""
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
    """Build .vale.ini content with StylesPath and optional Vocab entries."""
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
    """Add selected style directories (and config) to the zip archive."""
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
    paths: PackagingPaths,
    config: StyleConfig,
    version: str,
    force: bool,
) -> Path:
    """Create a Vale-ready ZIP archive containing styles and config.

    Parameters
    ----------
    paths:
        File-system locations for the project, styles, and output directory.
    config:
        Style selection and vocab configuration options.
    version:
        Version string used to name the archive and embedded files.
    force:
        When True, allow overwriting an existing archive.

    Returns
    -------
    Path
        Absolute path to the generated archive.

    Raises
    ------
    FileNotFoundError
        If the styles directory does not exist.
    ValueError
        If an absolute StylesPath is provided.
    """
    resolved_root = paths.project_root.expanduser().resolve()
    resolved_styles = _resolve_project_path(resolved_root, paths.styles_path)
    if not resolved_styles.exists():
        msg = f"Styles directory {resolved_styles} does not exist"
        raise FileNotFoundError(msg)

    styles = _discover_style_names(resolved_styles, config.explicit_styles)
    vocab = _select_vocabulary(resolved_styles, config.vocabulary)
    ini_contents = _build_ini(config.ini_styles_path, vocab)

    resolved_output = _resolve_project_path(resolved_root, paths.output_dir)
    resolved_output.mkdir(parents=True, exist_ok=True)
    filename_stem = "-".join(styles)
    archive_path = resolved_output / f"{filename_stem}-{version}.zip"
    if archive_path.exists() and not force:
        msg = f"Archive {archive_path} already exists; rerun with --force to overwrite"
        raise FileExistsError(msg)

    archive_dir = Path(f"{filename_stem}-{version}")
    ini_member = archive_dir / ".vale.ini"
    archive_root = archive_dir / Path(config.ini_styles_path)
    with ZipFile(archive_path, mode="w", compression=ZIP_DEFLATED) as archive:
        archive.writestr(str(ini_member), ini_contents)
        manifest_path = resolved_root / "stilyagi.toml"
        if manifest_path.exists():
            archive.write(manifest_path, arcname=str(archive_dir / "stilyagi.toml"))
        _add_styles_to_archive(
            archive,
            resolved_styles,
            archive_root,
            styles,
        )

    return archive_path


__all__ = [
    "DEFAULT_OUTPUT_DIR",
    "DEFAULT_STYLES_PATH",
    "PACKAGE_NAME",
    "PackagingPaths",
    "StyleConfig",
    "_resolve_project_path",
    "_resolve_version",
    "package_styles",
]
