#!/usr/bin/env -S uv run python
# /// script
# requires-python = ">=3.13"
# dependencies = ["cyclopts>=2.9"]
# ///

"""Cyclopts-powered CLI for packaging Concordat Vale styles into ZIPs."""

from __future__ import annotations

import json
import os
import re
import tomllib
import typing as typ
from importlib import metadata
from pathlib import Path
from urllib import error as urlerror
from urllib import request as urlrequest
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
FOOTNOTE_REGEX = r"(?m)^\[\^\d+\]:[^\n]*(?:\n[ \t]+[^\n]*)*"
PACKAGE_NAME = "concordat-vale"

app = App()
app.help = "Utilities for packaging and distributing Vale styles."
app.config = cyclopts.config.Env(ENV_PREFIX, command=False)
# Disable Cyclopts' auto-print (which wraps long lines) and print manually instead.
app.result_action = "return_value"


def _strip_version_prefix(tag: str) -> str:
    """Return *tag* without a leading ``v``/``V`` prefix."""
    return tag[1:] if tag.lower().startswith("v") else tag


def _style_name_for_repo(repo_name: str) -> str:
    """Derive a style name from *repo_name* while keeping things predictable."""
    return repo_name.removesuffix("-vale") or repo_name


def _fetch_latest_release(repo: str) -> dict[str, typ.Any]:
    """Fetch the latest GitHub release payload for *repo*.

    A minimal User-Agent header keeps GitHub happy, and an optional
    ``GITHUB_TOKEN`` avoids low unauthenticated rate limits when present.
    """
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    if not url.startswith("https://"):
        msg = "Release URL must use https://"
        raise ValueError(msg)
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "stilyagi/1.0",
    }
    if token := os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"

    request = urlrequest.Request(url, headers=headers)  # noqa: S310
    try:
        with urlrequest.urlopen(request, timeout=10) as response:  # noqa: S310
            body = response.read().decode("utf-8")
    except urlerror.HTTPError as exc:  # pragma: no cover - network edge cases
        msg = f"Failed to read latest release for {repo}: {exc.reason}"
        raise RuntimeError(msg) from exc
    except urlerror.URLError as exc:  # pragma: no cover - network edge cases
        msg = f"Network error talking to GitHub releases for {repo}: {exc.reason}"
        raise RuntimeError(msg) from exc

    payload: dict[str, typ.Any] = json.loads(body)
    return payload


def _select_tag_and_version(payload: dict[str, typ.Any]) -> tuple[str, str]:
    """Return (tag, version) from a GitHub release payload."""
    tag = payload.get("tag_name")
    if not isinstance(tag, str) or not tag.strip():
        msg = "Release payload missing tag_name"
        raise RuntimeError(msg)
    clean_tag = tag.strip()
    return clean_tag, _strip_version_prefix(clean_tag)


def _pick_asset_name(
    *,
    payload: dict[str, typ.Any],
    expected_name: str,
) -> str:
    """Prefer *expected_name* when present, otherwise fall back to any .zip asset."""
    assets = payload.get("assets")
    if isinstance(assets, list):
        for asset in assets:
            name = asset.get("name") if isinstance(asset, dict) else None
            if name == expected_name:
                return expected_name
        for asset in assets:
            name = asset.get("name") if isinstance(asset, dict) else None
            if isinstance(name, str) and name.endswith(".zip"):
                return name
    return expected_name


def _build_packages_url(repo: str, tag: str, asset: str) -> str:
    """Construct the release download URL for *repo*, *tag*, and *asset*."""
    return f"https://github.com/{repo}/releases/download/{tag}/{asset}"


def _resolve_release(
    *,
    repo: str,
    style_name: str,
    override_version: str | None,
    override_tag: str | None,
) -> tuple[str, str, str]:
    """Return ``(version, tag, packages_url)`` for a GitHub-hosted style."""
    if override_version:
        version = override_version
        tag = override_tag or f"v{version}"
        asset_name = f"{style_name}-{version}.zip"
    else:
        payload = _fetch_latest_release(repo)
        tag, version = _select_tag_and_version(payload)
        asset_name = _pick_asset_name(
            payload=payload,
            expected_name=f"{style_name}-{version}.zip",
        )

    packages_url = _build_packages_url(repo, tag, asset_name)
    return version, tag, packages_url


def _parse_ini(path: Path) -> tuple[dict[str, str], dict[str, dict[str, str]]]:
    """Parse a Vale ini file into (root_options, sections)."""
    if not path.exists():
        return {}, {}

    root_options: dict[str, str] = {}
    sections: dict[str, dict[str, str]] = {}
    current: dict[str, str] = root_options
    current_name: str | None = None

    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", ";")):
            continue
        if stripped.startswith("[") and stripped.endswith("]"):
            current_name = stripped[1:-1].strip()
            current = sections.setdefault(current_name, {})
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            current[key.strip()] = value.strip()

    return root_options, sections


def _merge_required_section(
    *, existing: dict[str, str], required: dict[str, str]
) -> dict[str, str]:
    merged = existing.copy()
    merged.update(required)
    return merged


def _render_root_options(
    root_options: dict[str, str], root_priority: tuple[str, ...]
) -> list[str]:
    lines: list[str] = [
        *(
            f"{key} = {root_options[key]}"
            for key in root_priority
            if key in root_options
        )
    ]
    lines.extend(
        f"{key} = {value}"
        for key, value in root_options.items()
        if key not in root_priority
    )
    if lines:
        lines.append("")
    return lines


def _emit_section(name: str, options: dict[str, str], lines: list[str]) -> None:
    lines.append(f"[{name}]")
    for key, value in options.items():
        if key == "BlockIgnores":
            lines.append("# Ignore for footnotes")
        lines.append(f"{key} = {value}")
    lines.append("")


def _emit_ordered_sections(
    section_order: list[str], sections: dict[str, dict[str, str]], lines: list[str]
) -> None:
    """Emit sections in the specified order if they exist."""
    for name in section_order:
        if name in sections:
            _emit_section(name, sections[name], lines)


def _emit_remaining_sections(
    section_order: list[str], sections: dict[str, dict[str, str]], lines: list[str]
) -> None:
    """Emit remaining sections not in the specified order, sorted alphabetically."""
    for name in sorted(sections):
        if name not in section_order:
            _emit_section(name, sections[name], lines)


def _render_ini(
    *,
    root_options: dict[str, str],
    sections: dict[str, dict[str, str]],
) -> str:
    """Render a deterministic .vale.ini from parsed sections."""
    root_priority = ("Packages", "MinAlertLevel", "Vocab")
    lines = _render_root_options(root_options, root_priority)

    section_order = [
        "docs/**/*.{md,markdown,mdx}",
        "AGENTS.md",
        "*.{rs,ts,js,sh,py}",
        "README.md",
    ]

    _emit_ordered_sections(section_order, sections, lines)
    _emit_remaining_sections(section_order, sections, lines)
    return "\n".join(lines).rstrip() + "\n"


def _update_vale_ini(
    *,
    ini_path: Path,
    style_name: str,
    packages_url: str,
) -> None:
    """Ensure ``.vale.ini`` advertises the Concordat package and sections."""
    root_options, sections = _parse_ini(ini_path)
    root_options.update(
        {
            "Packages": packages_url,
            "MinAlertLevel": "warning",
            "Vocab": style_name,
        }
    )

    required_sections: dict[str, dict[str, str]] = {
        "docs/**/*.{md,markdown,mdx}": {
            "BasedOnStyles": style_name,
            "BlockIgnores": FOOTNOTE_REGEX,
        },
        "AGENTS.md": {"BasedOnStyles": style_name},
        "*.{rs,ts,js,sh,py}": {
            "BasedOnStyles": style_name,
            f"{style_name}.RustNoRun": "NO",
            f"{style_name}.Acronyms": "NO",
        },
        "README.md": {
            "BasedOnStyles": style_name,
            f"{style_name}.Pronouns": "NO",
        },
    }

    for name, required in required_sections.items():
        existing = sections.get(name, {})
        merged = _merge_required_section(existing=existing, required=required)

        ordered: dict[str, str] = {}
        for key in required:
            if key in merged:
                ordered[key] = merged[key]
        for key, value in merged.items():
            if key not in ordered:
                ordered[key] = value

        sections[name] = ordered

    ini_path.write_text(
        _render_ini(root_options=root_options, sections=sections),
        encoding="utf-8",
    )


def _ensure_variable(lines: list[str], key: str, assignment: str) -> list[str]:
    """Insert ``key`` definition when missing."""
    pattern = re.compile(rf"^{re.escape(key)}\s*[?:]?=")
    if any(pattern.match(line) for line in lines):
        return lines
    return [assignment] + ([""] if lines else []) + lines


def _ensure_phony(lines: list[str], target: str) -> list[str]:
    """Add *target* to the first .PHONY line or create one."""
    for idx, line in enumerate(lines):
        if line.startswith(".PHONY"):
            if target in line.split():
                return lines
            updated = line.rstrip() + f" {target}"
            return [*lines[:idx], updated, *lines[idx + 1 :]]
    return [f".PHONY: {target}"] + ([""] if lines else []) + lines


def _find_target_start(lines: list[str], target_header: str) -> int | None:
    """Return the index of the first line starting with ``target_header``."""
    for idx, line in enumerate(lines):
        if line.startswith(target_header):
            return idx
    return None


def _find_target_end(lines: list[str], start_idx: int) -> int:
    """Locate the end of the target block beginning at ``start_idx``."""
    end_idx = start_idx + 1
    while end_idx < len(lines) and lines[end_idx].startswith("\t"):
        end_idx += 1
    while end_idx < len(lines) and lines[end_idx].strip() == "":
        end_idx += 1
    return end_idx


def _append_with_spacing(lines: list[str], recipe: list[str]) -> list[str]:
    """Append ``recipe`` to ``lines`` preserving a single blank separator."""
    if lines and lines[-1].strip():
        return [*lines, "", *recipe]
    return lines + recipe


def _parse_repo_reference(repo: str) -> tuple[str, str, str]:
    """Parse and validate a GitHub repository reference."""
    if repo.count("/") != 1:
        msg = "Repository reference must be in the form owner/name"
        raise ValueError(msg)

    owner, repo_name = (part.strip() for part in repo.split("/", maxsplit=1))
    if not owner or not repo_name:
        msg = "Repository reference must include both owner and name"
        raise ValueError(msg)

    style_name = _style_name_for_repo(repo_name)
    return owner, repo_name, style_name


def _resolve_install_paths(
    *, cwd: Path, project_root: Path, vale_ini: Path, makefile: Path
) -> tuple[Path, Path, Path]:
    """Resolve and prepare installation paths."""
    resolved_root = _resolve_project_path(cwd, project_root)
    ini_path = _resolve_project_path(resolved_root, vale_ini)
    makefile_path = _resolve_project_path(resolved_root, makefile)
    ini_path.parent.mkdir(parents=True, exist_ok=True)
    return resolved_root, ini_path, makefile_path


def _perform_install(
    *,
    owner: str,
    repo_name: str,
    style_name: str,
    ini_path: Path,
    makefile_path: Path,
    override_version: str | None,
    override_tag: str | None,
) -> str:
    """Perform the installation steps and return a status message."""
    version_str, _tag_str, packages_url = _resolve_release(
        repo=f"{owner}/{repo_name}",
        style_name=style_name,
        override_version=override_version,
        override_tag=override_tag,
    )

    _update_vale_ini(
        ini_path=ini_path,
        style_name=style_name,
        packages_url=packages_url,
    )
    _update_makefile(makefile_path)

    message = (
        f"Installed {style_name} {version_str} from {owner}/{repo_name} into "
        f"{ini_path} and {makefile_path}"
    )
    print(message)
    return message


def _replace_vale_target(lines: list[str]) -> list[str]:
    """Swap any existing vale target with the canonical recipe."""
    recipe = [
        "vale: $(VALE) $(ACRONYM_SCRIPT) ## Check prose",
        "\t$(VALE) sync",
        "\t$(VALE) --no-global .",
    ]
    start_idx = _find_target_start(lines, "vale:")
    if start_idx is None:
        return _append_with_spacing(lines, recipe)

    end_idx = _find_target_end(lines, start_idx)
    return lines[:start_idx] + recipe + lines[end_idx:]


def _update_makefile(makefile_path: Path) -> None:
    """Ensure the Makefile exposes a vale target that syncs Concordat."""
    if makefile_path.exists():
        lines = makefile_path.read_text(encoding="utf-8").splitlines()
    else:
        lines = []

    lines = _ensure_variable(lines, "VALE", "VALE ?= vale")
    lines = _ensure_phony(lines, "vale")
    lines = _replace_vale_target(lines)

    makefile_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


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


@app.command(name="install")
def install_command(
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

    _resolved_root, ini_path, makefile_path = _resolve_install_paths(
        cwd=Path.cwd(),
        project_root=project_root,
        vale_ini=vale_ini,
        makefile=makefile,
    )
    return _perform_install(
        owner=owner,
        repo_name=repo_name,
        style_name=style_name,
        ini_path=ini_path,
        makefile_path=makefile_path,
        override_version=release_version,
        override_tag=tag,
    )


def main() -> None:
    """Invoke the Cyclopts application."""
    app()


if __name__ == "__main__":
    main()
