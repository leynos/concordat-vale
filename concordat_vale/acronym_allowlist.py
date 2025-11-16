"""Helpers for merging project acronyms into the Tengo allow map."""

from __future__ import annotations

import dataclasses as dc
import re
import typing as typ

if typ.TYPE_CHECKING:
    import collections.abc as cabc
    from pathlib import Path

MANAGED_COMMENT = "// Project-specific acronyms (imported from .config/common-acronyms)"
ROMAN_MARKER = "// Roman numerals appearing in API names"
ALLOW_ENTRY = re.compile(r'^\s*"([^"\\]+)":\s*true,\s*$')
VALID_TOKEN = re.compile(r"^[0-9A-Z]+$")


class AcronymAllowlistError(RuntimeError):
    """Raised when project acronyms cannot be parsed."""


@dc.dataclass(frozen=True)
class AllowlistUpdateResult:
    """Summarises the outcome of updating the Tengo allow map."""

    wrote_file: bool
    managed_entries: tuple[str, ...]


def load_project_acronyms(source: Path) -> list[str]:
    """Read `.config/common-acronyms` into an ordered, deduplicated list."""
    if not source.exists():
        msg = f"Missing {source}; create .config/common-acronyms before syncing."
        raise FileNotFoundError(msg)

    contents = source.read_text(encoding="utf-8").splitlines()
    seen: set[str] = set()
    acronyms: list[str] = []

    for idx, raw_line in enumerate(contents, 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        token = line.upper()
        if not VALID_TOKEN.fullmatch(token):
            msg = f"Line {idx} in {source} must be alphanumeric; got {line!r}."
            raise AcronymAllowlistError(msg)
        if token not in seen:
            seen.add(token)
            acronyms.append(token)

    return acronyms


def update_allow_map(
    tengo_path: Path, acronyms: cabc.Sequence[str]
) -> AllowlistUpdateResult:
    """Inject project acronyms into the allow map block."""
    if not tengo_path.exists():
        msg = (
            "AcronymsFirstUse.tengo has not been synced. Run `vale sync` first."
            f" Expected path: {tengo_path}"
        )
        raise FileNotFoundError(msg)

    original_text = tengo_path.read_text(encoding="utf-8")
    lines = original_text.splitlines()

    _remove_managed_block(lines)
    base_entries = _collect_allow_entries(lines)
    filtered = [token for token in acronyms if token not in base_entries]

    if filtered:
        block = _build_block(filtered)
        insert_idx = _find_insertion_index(lines)
        lines[insert_idx:insert_idx] = block

    new_text = "\n".join(lines) + "\n"
    changed = new_text != original_text
    if changed:
        tengo_path.write_text(new_text, encoding="utf-8")

    return AllowlistUpdateResult(changed, tuple(filtered))


def _collect_allow_entries(lines: cabc.Iterable[str]) -> set[str]:
    entries: set[str] = set()
    for line in lines:
        match = ALLOW_ENTRY.match(line)
        if match:
            entries.add(match.group(1))
    return entries


def _remove_managed_block(lines: list[str]) -> None:
    start = _find_comment_index(lines)
    if start is None:
        return

    idx = start + 1
    while idx < len(lines):
        stripped = lines[idx].strip()
        if not stripped:
            idx += 1
            break
        if not ALLOW_ENTRY.match(lines[idx]):
            break
        idx += 1

    del lines[start:idx]


def _find_comment_index(lines: list[str]) -> int | None:
    for idx, line in enumerate(lines):
        if line.strip() == MANAGED_COMMENT:
            return idx
    return None


def _build_block(acronyms: cabc.Sequence[str]) -> list[str]:
    block = [f"  {MANAGED_COMMENT}"]
    block.extend(f'  "{token}": true,' for token in acronyms)
    block.append("")
    return block


def _find_insertion_index(lines: list[str]) -> int:
    for idx, line in enumerate(lines):
        if line.strip() == ROMAN_MARKER:
            return idx
    for idx, line in enumerate(lines):
        if line.strip() == "}":
            return idx
    msg = "Unable to locate the allow map closing brace for insertion."
    raise AcronymAllowlistError(msg)


__all__ = [
    "AcronymAllowlistError",
    "AllowlistUpdateResult",
    "load_project_acronyms",
    "update_allow_map",
]
