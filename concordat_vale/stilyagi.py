#!/usr/bin/env -S uv run python
# /// script
# requires-python = ">=3.13"
# dependencies = ["cyclopts>=2.9"]
# ///

"""Cyclopts-powered CLI for packaging and installing Concordat Vale styles."""

from __future__ import annotations

import json
import os
import tomllib
import typing as typ
import urllib.error
import urllib.parse
import urllib.request
from importlib import metadata
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import cyclopts
from cyclopts import App, Parameter

DEFAULT_OUTPUT_DIR = Path("dist")
DEFAULT_STYLES_PATH = Path("styles")
DEFAULT_CONFIG_PATH = Path(".vale.ini")
ENV_PREFIX = "STILYAGI_"
PACKAGE_NAME = "concordat-vale"
DEFAULT_GITHUB_API_BASE = "https://api.github.com"
DEFAULT_INSTALL_STYLES_PATH = ".vale/styles"

app = App()
app.help = "Utilities for packaging and distributing Vale styles."
app.config = cyclopts.config.Env(ENV_PREFIX, command=False)
# Disable Cyclopts' auto-print (which wraps long lines) and print manually instead.
app.result_action = "return_value"


class ReleaseInfo(typ.NamedTuple):
    """Minimal release metadata required to update Vale configs."""

    tag: str
    version: str
    asset_url: str


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


def _strip_tag_prefix(tag: str) -> str:
    """Drop a leading ``v`` or ``V`` from a release tag when present."""
    return tag[1:] if tag.lower().startswith("v") else tag


def _latest_release_url(api_base: str, repo: str) -> str:
    """Construct the releases/latest endpoint for the supplied repository."""
    owner_repo = repo.strip().strip("/")
    if owner_repo.count("/") != 1:
        msg = "Repository reference must look like '<owner>/<repo>'"
        raise ValueError(msg)

    base = api_base.rstrip("/")
    return f"{base}/repos/{owner_repo}/releases/latest"


def _select_zip_asset(assets: list[dict[str, typ.Any]], version: str) -> str:
    """Pick the Concordat ZIP download URL from the release assets."""
    expected_suffix = f"concordat-{version}.zip"
    for asset in assets:
        name = str(asset.get("name", ""))
        url = asset.get("browser_download_url")
        if name.endswith(expected_suffix) and isinstance(url, str) and url.strip():
            return url

    for asset in assets:
        name = str(asset.get("name", ""))
        url = asset.get("browser_download_url")
        if name.lower().endswith(".zip") and isinstance(url, str) and url.strip():
            return url

    msg = "Latest release does not expose a downloadable ZIP asset"
    raise RuntimeError(msg)


def _fetch_latest_release(
    repo: str,
    *,
    api_base: str = DEFAULT_GITHUB_API_BASE,
    token: str | None = None,
    opener: typ.Callable[[urllib.request.Request, int], typ.Any] | None = None,
) -> ReleaseInfo:
    """Read release metadata for *repo* and locate the Concordat ZIP asset."""
    target = _latest_release_url(api_base, repo)
    parsed_target = urllib.parse.urlparse(target)
    if parsed_target.scheme not in {"http", "https"}:
        msg = (
            "GitHub API URL must use http or https; got "
            f"{parsed_target.scheme or '<empty>'}"
        )
        raise ValueError(msg)

    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "stilyagi/; concordat-vale",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    request = urllib.request.Request(  # noqa: S310 - validated http/https URL
        target, headers=headers
    )
    http_open = opener or urllib.request.urlopen
    try:
        with http_open(request, timeout=10) as response:  # type: ignore[call-arg]
            status = response.getcode()
            if status >= 400:
                msg = f"GitHub API request failed with HTTP {status}"
                raise RuntimeError(msg)
            payload = response.read()
    except urllib.error.HTTPError as exc:
        msg = f"GitHub API request failed: HTTP {exc.code} {exc.reason}"
        raise RuntimeError(msg) from exc
    except urllib.error.URLError as exc:  # pragma: no cover - network instability
        msg = f"GitHub API request failed: {exc.reason}"
        raise RuntimeError(msg) from exc

    try:
        data = json.loads(payload.decode("utf-8"))
    except json.JSONDecodeError as exc:  # pragma: no cover - defensive path
        msg = "GitHub API responded with invalid JSON"
        raise ValueError(msg) from exc

    tag = str(data.get("tag_name", "")).strip()
    if not tag:
        msg = "Latest release payload is missing tag_name"
        raise ValueError(msg)

    assets = data.get("assets")
    if not isinstance(assets, list):
        msg = "Latest release payload is missing assets"
        raise TypeError(msg)

    version = _strip_tag_prefix(tag)
    package_url = _select_zip_asset(assets, version)
    return ReleaseInfo(tag=tag, version=version, asset_url=package_url)


def _existing_styles_path(config_path: Path) -> str | None:
    """Return the StylesPath already recorded in the Vale config, if any."""
    if not config_path.exists():
        return None

    for line in config_path.read_text(encoding="utf-8").splitlines():
        if not line.strip().startswith("StylesPath"):
            continue
        _, _, value = line.partition("=")
        stripped = value.strip()
        if stripped:
            return stripped
    return None


def _render_install_ini(styles_path: str, packages_url: str) -> str:
    """Render the Concordat-focused Vale configuration snippet."""
    lines = [
        f"StylesPath = {styles_path}",
        f"Packages = {packages_url}",
        "MinAlertLevel = warning",
        "Vocab = concordat",
        "",
        "[docs/**/*.{md,markdown,mdx}]",
        "BasedOnStyles = concordat",
        "# Ignore for footnotes",
        r"BlockIgnores = (?m)^\[\^\d+\]:[^\n]*(?:\n[ \t]+[^\n]*)*",
        "",
        "[AGENTS.md]",
        "BasedOnStyles = concordat",
        "",
        "[*.{rs,ts,js,sh,py}]",
        "BasedOnStyles = concordat",
        "concordat.RustNoRun = NO",
        "concordat.Acronyms = NO",
        "",
        "# README.md may use first/second person pronouns",
        "[README.md]",
        "BasedOnStyles = concordat",
        "concordat.Pronouns = NO",
        "",
    ]
    return "\n".join(lines)


def install_styles(
    *,
    repo: str,
    config_path: Path = DEFAULT_CONFIG_PATH,
    api_base: str = DEFAULT_GITHUB_API_BASE,
    styles_path: str | None = None,
    token: str | None = None,
) -> Path:
    """Update a Vale config to point at the latest Concordat release package."""
    resolved_config = _resolve_project_path(Path.cwd(), config_path)
    resolved_config.parent.mkdir(parents=True, exist_ok=True)

    release = _fetch_latest_release(repo, api_base=api_base, token=token)
    styles_entry = (
        styles_path
        or _existing_styles_path(resolved_config)
        or DEFAULT_INSTALL_STYLES_PATH
    )
    body = _render_install_ini(styles_entry, release.asset_url)
    resolved_config.write_text(body, encoding="utf-8")
    return resolved_config


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


@app.command(name="install")
def install_command(
    repo: typ.Annotated[
        str,
        Parameter(help="GitHub repo reference (for example, leynos/concordat-vale)."),
    ],
    config_path: typ.Annotated[
        Path,
        Parameter(
            help="Path to the .vale.ini file to update.", env_var="STILYAGI_CONFIG_PATH"
        ),
    ] = DEFAULT_CONFIG_PATH,
    api_base: typ.Annotated[
        str,
        Parameter(
            help="GitHub API base URL used to resolve releases.",
            env_var="STILYAGI_API_BASE",
        ),
    ] = DEFAULT_GITHUB_API_BASE,
    styles_path: typ.Annotated[
        str | None,
        Parameter(
            help="Override the StylesPath recorded in .vale.ini.",
            env_var="STILYAGI_STYLES_PATH",
        ),
    ] = None,
    token: typ.Annotated[
        str | None,
        Parameter(
            help=(
                "GitHub token for authenticated API access (defaults to GITHUB_TOKEN)."
            ),
            env_var="STILYAGI_TOKEN",
        ),
    ] = None,
) -> str:
    """Record Concordat packages and defaults into the Vale config."""
    resolved_token = token or os.environ.get("GITHUB_TOKEN")
    updated_config = install_styles(
        repo=repo,
        config_path=config_path,
        api_base=api_base,
        styles_path=styles_path,
        token=resolved_token,
    )
    print(updated_config)
    return str(updated_config)


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


def main() -> None:
    """Invoke the Cyclopts application."""
    app()


if __name__ == "__main__":
    main()
