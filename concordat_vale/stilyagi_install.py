"""Installation helpers for wiring Concordat into external repositories."""

from __future__ import annotations

import dataclasses as dc
import io
import json
import logging
import os
import re
import shlex
import tomllib
import typing as typ
from urllib import error as urlerror
from urllib import request as urlrequest
from zipfile import ZipFile

from .stilyagi_packaging import _resolve_project_path

if typ.TYPE_CHECKING:
    from pathlib import Path


logger = logging.getLogger(__name__)

FOOTNOTE_REGEX = r"(?m)^\[\^\d+\]:[^\n]*(?:\n[ \t]+[^\n]*)*"
VALID_TENGO_VALUE_TYPES: tuple[str, ...] = ("true", "=", "=b", "=n")


def _strip_version_prefix(tag: str) -> str:
    """Return *tag* without a leading ``v``/``V`` prefix."""
    return tag[1:] if tag.lower().startswith("v") else tag


def _style_name_for_repo(repo_name: str) -> str:
    """Derive a style name from *repo_name* while keeping things predictable."""
    return repo_name.removesuffix("-vale") or repo_name


def _fetch_latest_release(repo: str) -> dict[str, typ.Any]:
    """Fetch the latest GitHub release payload for *repo*."""
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

    request = urlrequest.Request(  # noqa: S310 - controlled https URL with optional token
        url,
        headers=headers,
    )
    try:
        with urlrequest.urlopen(  # noqa: S310 - bounded timeout over https
            request, timeout=10
        ) as response:
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


def _find_asset_by_name(assets: list[typ.Any], expected_name: str) -> str | None:
    """Find an asset matching the expected name exactly."""
    for asset in assets:
        name = asset.get("name") if isinstance(asset, dict) else None
        if name == expected_name:
            return expected_name
    return None


def _find_zip_asset(assets: list[typ.Any]) -> str | None:
    """Find any asset with a .zip extension."""
    for asset in assets:
        name = asset.get("name") if isinstance(asset, dict) else None
        if isinstance(name, str) and name.endswith(".zip"):
            return name
    return None


def _pick_asset_name(
    *,
    payload: dict[str, typ.Any],
    expected_name: str,
) -> str:
    """Prefer *expected_name* when present, otherwise fall back to any .zip asset."""
    assets = payload.get("assets")
    if not isinstance(assets, list):
        return expected_name

    found = _find_asset_by_name(assets, expected_name)
    if found:
        return found

    found = _find_zip_asset(assets)
    return found if found else expected_name


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


@dc.dataclass(frozen=True)
class InstallManifest:
    """Configuration extracted from a packaged stilyagi.toml."""

    style_name: str
    vocab_name: str
    min_alert_level: str
    post_sync_steps: tuple[str, ...] = dc.field(default_factory=tuple)


def _parse_install_manifest(
    *, raw: dict[str, typ.Any] | None, default_style_name: str
) -> InstallManifest:
    """Return manifest values with sensible defaults and whitespace trimmed."""
    install_section_raw = raw.get("install", {}) if isinstance(raw, dict) else {}
    install_section = (
        install_section_raw if isinstance(install_section_raw, dict) else {}
    )

    def _pick(value: object, fallback: str) -> str:
        return value.strip() if isinstance(value, str) and value.strip() else fallback

    style_name = _pick(install_section.get("style_name"), default_style_name)
    vocab_name = _pick(install_section.get("vocab"), style_name)
    min_alert_level = _pick(install_section.get("min_alert_level"), "warning")

    raw_steps = install_section.get("post_sync_steps")
    steps: list[str] = []
    if raw_steps is None:
        pass
    elif isinstance(raw_steps, list):
        steps = _parse_post_sync_steps_list(raw_steps)
    else:
        msg = (
            "install.post_sync_steps must be a list of tables; "
            f"got {type(raw_steps).__name__}"
        )
        raise TypeError(msg)

    return InstallManifest(
        style_name=style_name,
        vocab_name=vocab_name,
        min_alert_level=min_alert_level,
        post_sync_steps=tuple(steps),
    )


def _download_packages_archive(packages_url: str) -> bytes:
    """Download the packaged archive bytes for inspection."""
    request = urlrequest.Request(  # noqa: S310 - URL is user-provided CLI input
        packages_url,
        headers={"User-Agent": "stilyagi/1.0"},
    )
    try:
        with urlrequest.urlopen(request, timeout=15) as response:  # noqa: S310
            return response.read()
    except urlerror.HTTPError as exc:  # pragma: no cover - network edge cases
        msg = f"Failed to download archive {packages_url}: {exc.reason}"
        raise RuntimeError(msg) from exc
    except urlerror.URLError as exc:  # pragma: no cover - network edge cases
        msg = f"Network error downloading {packages_url}: {exc.reason}"
        raise RuntimeError(msg) from exc


def _extract_stilyagi_toml(archive_bytes: bytes) -> bytes | None:
    """Extract stilyagi.toml from archive bytes when present."""
    with ZipFile(io.BytesIO(archive_bytes)) as archive:
        try:
            member = next(
                name for name in archive.namelist() if name.endswith("stilyagi.toml")
            )
        except StopIteration:
            return None
        return archive.read(member)


def _load_install_manifest(
    *, packages_url: str, default_style_name: str
) -> InstallManifest:
    """Load the install manifest from the packaged archive if available."""
    raw_manifest: dict[str, typ.Any] | None = None
    manifest_bytes: bytes | None = None

    if not os.environ.get("STILYAGI_SKIP_MANIFEST_DOWNLOAD"):
        try:
            archive_bytes = _download_packages_archive(packages_url)
            manifest_bytes = _extract_stilyagi_toml(archive_bytes)
            if manifest_bytes is not None:
                raw_manifest = tomllib.loads(manifest_bytes.decode("utf-8"))
        except Exception as exc:  # noqa: BLE001 - fallback is intentional for robustness
            logger.debug(
                "Failed to load stilyagi.toml from %s (manifest_found=%s)",
                packages_url,
                manifest_bytes is not None,
                exc_info=exc,
            )

    return _parse_install_manifest(
        raw=raw_manifest, default_style_name=default_style_name
    )


def _validate_update_tengo_map_step(step: dict[str, object]) -> tuple[str, str, str]:
    """Validate and extract fields for an update-tengo-map action.

    Parameters
    ----------
    step
        Table entry from ``install.post_sync_steps``.

    Returns
    -------
    tuple[str, str, str]
        The (source, dest, value_type) strings used when rendering commands.

    Raises
    ------
    ValueError
        If the action or value type is invalid.
    TypeError
        If any required field is not a string.
    """
    action = step.get("action")
    if action != "update-tengo-map":
        msg = (
            "install.post_sync_steps action must be 'update-tengo-map' "
            f"(got {action!r})"
        )
        raise ValueError(msg)

    source = step.get("source")
    dest = step.get("dest")
    value_type = step.get("type", "true")

    for key, value in {"source": source, "dest": dest, "type": value_type}.items():
        if not isinstance(value, str):
            msg = f"install.post_sync_steps.{key} must be a string"
            raise TypeError(msg)

    source_str = typ.cast("str", source)
    dest_str = typ.cast("str", dest)
    value_type_str = typ.cast("str", value_type)

    if value_type_str not in VALID_TENGO_VALUE_TYPES:
        msg = (
            "install.post_sync_steps.type must be one of "
            f"{', '.join(VALID_TENGO_VALUE_TYPES)}"
        )
        raise ValueError(msg)

    return source_str, dest_str, value_type_str


def _parse_post_sync_steps_list(raw_steps: list[object]) -> list[str]:
    """Normalise trusted post-sync actions into Makefile-safe commands.

    Parameters
    ----------
    raw_steps
        Sequence of tables from ``install.post_sync_steps``.

    Returns
    -------
    list[str]
        Rendered commands for the supported actions.

    Raises
    ------
    TypeError
        If the list items or required fields are not strings.
    ValueError
        If an unsupported action or value type is supplied.
    """
    commands: list[str] = []
    for step in raw_steps:
        if not isinstance(step, dict):
            msg = (
                "install.post_sync_steps must be a list of tables; "
                f"got {type(step).__name__} element"
            )
            raise TypeError(msg)

        typed_step = typ.cast("dict[str, object]", step)
        source_str, dest_str, value_type_str = _validate_update_tengo_map_step(
            typed_step
        )

        command = " ".join(
            [
                "uv run stilyagi update-tengo-map",
                f"--source {shlex.quote(source_str)}",
                f"--dest {shlex.quote(dest_str)}",
                f"--type {shlex.quote(value_type_str)}",
            ]
        )
        commands.append(command)

    return commands


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
) -> set[str]:
    """Emit sections in order and return the emitted names."""
    seen: set[str] = set()
    for name in section_order:
        if name in sections:
            _emit_section(name, sections[name], lines)
            seen.add(name)
    return seen


def _emit_remaining_sections(
    sections: dict[str, dict[str, str]], seen: set[str], lines: list[str]
) -> None:
    """Emit remaining sections not already emitted, sorted alphabetically."""
    for name in sorted(sections):
        if name not in seen:
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
    seen = _emit_ordered_sections(section_order, sections, lines)
    _emit_remaining_sections(sections, seen, lines)
    return "\n".join(lines).rstrip() + "\n"


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


def _merge_and_order_section(
    existing: dict[str, str], required: dict[str, str]
) -> dict[str, str]:
    """Merge existing with required and order required keys first."""
    merged = existing.copy() | required
    ordered: dict[str, str] = {key: merged[key] for key in required if key in merged}
    ordered |= {key: value for key, value in merged.items() if key not in ordered}
    return ordered


def _update_vale_ini(
    *, ini_path: Path, packages_url: str, manifest: InstallManifest
) -> None:
    """Ensure ``.vale.ini`` advertises the Concordat package and sections."""
    root_options, sections = _parse_ini(ini_path)
    root_options.update(
        {
            "Packages": packages_url,
            "MinAlertLevel": manifest.min_alert_level,
            "Vocab": manifest.vocab_name,
        }
    )

    required_sections: dict[str, dict[str, str]] = {
        "docs/**/*.{md,markdown,mdx}": {
            "BasedOnStyles": manifest.style_name,
            "BlockIgnores": FOOTNOTE_REGEX,
        },
        "AGENTS.md": {"BasedOnStyles": manifest.style_name},
        "*.{rs,ts,js,sh,py}": {
            "BasedOnStyles": manifest.style_name,
            f"{manifest.style_name}.RustNoRun": "NO",
            f"{manifest.style_name}.Acronyms": "NO",
        },
        "README.md": {
            "BasedOnStyles": manifest.style_name,
            f"{manifest.style_name}.Pronouns": "NO",
        },
    }

    for name, required in required_sections.items():
        sections[name] = _merge_and_order_section(sections.get(name, {}), required)

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
        if line.lstrip().startswith(".PHONY"):
            if target in line.split():
                return lines
            updated = f"{line.rstrip()} {target}"
            return [*lines[:idx], updated, *lines[idx + 1 :]]
    return [f".PHONY: {target}"] + ([""] if lines else []) + lines


def _find_target_bounds(lines: list[str], target_header: str) -> tuple[int | None, int]:
    """Return (start_idx, end_idx) for target_header, or (None, len(lines))."""
    start_idx = next(
        (idx for idx, line in enumerate(lines) if line.startswith(target_header)),
        None,
    )
    if start_idx is None:
        return None, len(lines)

    end_idx = start_idx + 1
    while end_idx < len(lines) and lines[end_idx].startswith("\t"):
        end_idx += 1
    while end_idx < len(lines) and lines[end_idx].strip() == "":
        end_idx += 1
    return start_idx, end_idx


def _append_with_spacing(lines: list[str], recipe: list[str]) -> list[str]:
    """Append ``recipe`` to ``lines`` preserving a single blank separator."""
    return [*lines, "", *recipe] if lines and lines[-1].strip() else lines + recipe


def _build_vale_recipe(manifest: InstallManifest) -> list[str]:
    """Construct the vale target recipe from the install manifest."""
    recipe = [
        "vale: $(VALE) ## Check prose",
        "\t$(VALE) sync",
    ]

    recipe.extend(f"\t{step}" for step in manifest.post_sync_steps)

    recipe.append("\t$(VALE) --no-global .")
    return recipe


def _replace_vale_target(lines: list[str], *, manifest: InstallManifest) -> list[str]:
    """Swap any existing vale target with the manifest-driven recipe."""
    recipe = _build_vale_recipe(manifest)
    start_idx, end_idx = _find_target_bounds(lines, "vale:")
    if start_idx is None:
        return _append_with_spacing(lines, recipe)
    return lines[:start_idx] + recipe + lines[end_idx:]


def _update_makefile(makefile_path: Path, *, manifest: InstallManifest) -> None:
    """Expose a vale target that syncs Concordat and runs manifest steps."""
    if makefile_path.exists():
        lines = makefile_path.read_text(encoding="utf-8").splitlines()
    else:
        lines = []

    lines = _ensure_variable(lines, "VALE", "VALE ?= vale")
    lines = _ensure_phony(lines, "vale")
    lines = _replace_vale_target(lines, manifest=manifest)

    makefile_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _parse_repo_reference(repo: str) -> tuple[str, str, str]:
    """Parse and validate a GitHub repository reference."""
    if repo.count("/") != 1:
        msg = "Repository reference must be in the form 'owner/name'."
        raise ValueError(msg)

    owner, repo_name = (part.strip() for part in repo.split("/", maxsplit=1))
    if not owner or not repo_name:
        msg = "Repository reference must be in the form 'owner/name'."
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
    for parent in {ini_path.parent, makefile_path.parent}:
        parent.mkdir(parents=True, exist_ok=True)
    return resolved_root, ini_path, makefile_path


@dc.dataclass(frozen=True)
class InstallConfig:
    """Configuration for installing a Concordat style."""

    owner: str
    repo_name: str
    style_name: str
    ini_path: Path
    makefile_path: Path
    override_version: str | None = None
    override_tag: str | None = None


def _perform_install(
    *,
    config: InstallConfig,
) -> str:
    """Perform the installation steps using the supplied configuration."""
    version_str, _tag_str, packages_url = _resolve_release(
        repo=f"{config.owner}/{config.repo_name}",
        style_name=config.style_name,
        override_version=config.override_version,
        override_tag=config.override_tag,
    )

    manifest = _load_install_manifest(
        packages_url=packages_url,
        default_style_name=config.style_name,
    )

    _update_vale_ini(
        ini_path=config.ini_path,
        packages_url=packages_url,
        manifest=manifest,
    )
    _update_makefile(config.makefile_path, manifest=manifest)

    message = (
        f"Installed {manifest.style_name} {version_str} from "
        f"{config.owner}/{config.repo_name} into {config.ini_path} and "
        f"{config.makefile_path}"
    )
    print(message)
    return message


__all__ = [
    "FOOTNOTE_REGEX",
    "InstallManifest",
    "_download_packages_archive",
    "_extract_stilyagi_toml",
    "_load_install_manifest",
    "_parse_install_manifest",
    "_parse_repo_reference",
    "_perform_install",
    "_resolve_install_paths",
    "_update_makefile",
    "_update_vale_ini",
]
