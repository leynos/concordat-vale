"""Utilities for updating Tengo map literals."""

from __future__ import annotations

import dataclasses as dc
import enum
import json
import re
import typing as typ

if typ.TYPE_CHECKING:
    import collections.abc as cabc
    from pathlib import Path

ENTRY_PATTERN = re.compile(
    r'^(?P<indent>\s*)"(?P<key>(?:[^"\\]|\\.)+)"\s*:\s*(?P<value>.*),'
    r"(?P<comment>\s*//.*)?\s*$"
)


class TengoMapError(RuntimeError):
    """Raised when Tengo maps or inputs cannot be parsed."""


class MapValueType(enum.StrEnum):
    """Supported coercions for source entries."""

    TRUE = "true"
    STRING = "="
    BOOLEAN = "=b"
    NUMBER = "=n"


@dc.dataclass(frozen=True)
class MapUpdateResult:
    """Summarises the outcome of a Tengo map update."""

    updated: int
    wrote_file: bool


def parse_source_entries(
    source: Path, value_type: MapValueType
) -> tuple[int, dict[str, object]]:
    """Parse source lines into key/value pairs honouring inline comments."""
    if not source.exists():
        msg = f"Missing input file: {source}"
        raise FileNotFoundError(msg)

    entries_provided = 0
    parsed: dict[str, object] = {}
    for raw_line in source.read_text(encoding="utf-8").splitlines():
        if not raw_line.strip():
            continue
        if re.match(r"^\s*#", raw_line):
            continue

        stripped = re.sub(r"\s+(#.*)?$", "", raw_line)
        token = stripped.strip()
        if not token:
            continue

        entries_provided += 1
        key, value = _parse_token(token, value_type)
        parsed[key] = value

    return entries_provided, parsed


def update_tengo_map(
    tengo_path: Path,
    map_name: str,
    entries: cabc.Mapping[str, object],
) -> MapUpdateResult:
    """Update or append map entries inside a Tengo script."""
    if not tengo_path.exists():
        msg = f"Missing Tengo script: {tengo_path}"
        raise FileNotFoundError(msg)
    if not map_name:
        msg = "Map name must be provided."
        raise TengoMapError(msg)

    text = tengo_path.read_text(encoding="utf-8")
    lines = text.splitlines()

    start_idx, map_indent = _find_map_header(lines, map_name)
    end_idx = _find_map_end(lines, start_idx)
    existing, entry_indent = _collect_entries(
        lines,
        start_idx + 1,
        end_idx,
        map_indent,
    )

    updated, lines = _apply_entries(
        lines=lines,
        existing=existing,
        entries=entries,
        entry_indent=entry_indent,
        closing_idx=end_idx,
    )

    new_text = "\n".join(lines) + "\n"
    wrote_file = new_text != text
    if wrote_file:
        tengo_path.write_text(new_text, encoding="utf-8")
    return MapUpdateResult(updated=updated, wrote_file=wrote_file)


def _apply_entries(
    lines: list[str],
    existing: dict[str, _Entry],
    entries: cabc.Mapping[str, object],
    entry_indent: str,
    closing_idx: int,
) -> tuple[int, list[str]]:
    updated = 0
    current_closing_idx = closing_idx
    for key, value in entries.items():
        if key in existing:
            entry = existing[key]
            if _values_equal(entry.value, value):
                continue
            lines[entry.index] = _render_entry(
                key=key,
                value=value,
                indent=entry.indent,
                comment=entry.comment,
            )
            updated += 1
        else:
            rendered_line = _render_entry(key, value, entry_indent, "")
            lines.insert(current_closing_idx, rendered_line)
            current_closing_idx += 1
            updated += 1
    return updated, lines


@dc.dataclass(frozen=True)
class _Entry:
    index: int
    indent: str
    comment: str
    raw_value: str
    value: object


def _find_map_header(lines: list[str], map_name: str) -> tuple[int, str]:
    pattern = re.compile(rf"^(?P<indent>\s*){re.escape(map_name)}\s*:=\s*\{{\s*$")
    for idx, line in enumerate(lines):
        if match := pattern.match(line):
            return idx, match.group("indent")
    msg = f"Could not find map {map_name!r} in Tengo script."
    raise TengoMapError(msg)


def _find_map_end(lines: list[str], start_idx: int) -> int:
    depth = 1
    for idx in range(start_idx + 1, len(lines)):
        line = lines[idx]
        depth += line.count("{")
        depth -= line.count("}")
        if depth == 0:
            return idx
    msg = "Failed to locate closing brace for map."
    raise TengoMapError(msg)


def _collect_entries(
    lines: list[str], start: int, end: int, map_indent: str
) -> tuple[dict[str, _Entry], str]:
    entries: dict[str, _Entry] = {}
    entry_indent: str | None = None
    for idx in range(start, end):
        line = lines[idx]
        match = ENTRY_PATTERN.match(line)
        if not match:
            continue
        indent = match.group("indent")
        if entry_indent is None:
            entry_indent = indent
        key = match.group("key")
        raw_value = match.group("value").strip()
        entries[key] = _Entry(
            index=idx,
            indent=indent,
            comment=match.group("comment") or "",
            raw_value=raw_value,
            value=_parse_existing_value(raw_value),
        )

    if entry_indent is None:
        entry_indent = f"{map_indent}  "

    return entries, entry_indent


def _parse_token(token: str, value_type: MapValueType) -> tuple[str, object]:
    if value_type is MapValueType.TRUE:
        return token, True

    if "=" not in token:
        msg = "Source lines must include '=' when using typed modes."
        raise TengoMapError(msg)

    key, raw_value = token.split("=", 1)
    key = key.strip()
    value = raw_value.strip()
    if not key:
        msg = "Map keys may not be empty."
        raise TengoMapError(msg)

    if value_type is MapValueType.STRING:
        return key, _parse_string_value(value)
    if value_type is MapValueType.BOOLEAN:
        return key, _parse_boolean_value(value)
    if value_type is MapValueType.NUMBER:
        return key, _parse_numeric_value(value)

    msg = f"Unsupported map value type: {value_type}"
    raise TengoMapError(msg)


def _parse_string_value(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] == '"':
        try:
            return typ.cast("str", json.loads(value))
        except json.JSONDecodeError:
            return value.strip('"')
    return value


def _parse_boolean_value(value: str) -> bool:
    lowered = value.strip().lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    msg = f"Expected true or false, got {value!r}"
    raise TengoMapError(msg)


def _parse_numeric_value(value: str) -> int | float:
    trimmed = value.strip()
    try:
        return int(trimmed)
    except ValueError:
        try:
            return float(trimmed)
        except ValueError as exc:  # pragma: no cover - defensive
            msg = f"Could not parse numeric value {trimmed!r}"
            raise TengoMapError(msg) from exc


def _parse_existing_value(raw: str) -> object:
    stripped = raw.strip()
    lowered = stripped.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False

    if len(stripped) >= 2 and stripped[0] == stripped[-1] == '"':
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            return stripped.strip('"')

    try:
        return int(stripped)
    except ValueError:
        pass

    try:
        return float(stripped)
    except ValueError:
        pass

    return stripped


def _values_equal(existing: object, new_value: object) -> bool:
    if isinstance(existing, (int, float)) and isinstance(new_value, (int, float)):
        return float(existing) == float(new_value)
    return existing == new_value


def _render_entry(key: str, value: object, indent: str, comment: str) -> str:
    rendered_value = _render_value(value)
    suffix = comment or ""
    return f'{indent}"{key}": {rendered_value},{suffix}'


def _render_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return json.dumps(str(value))


__all__ = [
    "MapUpdateResult",
    "MapValueType",
    "TengoMapError",
    "parse_source_entries",
    "update_tengo_map",
]
