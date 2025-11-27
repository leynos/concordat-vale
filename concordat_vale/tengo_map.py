"""Utilities for updating Tengo map literals.

This module provides helpers for parsing flat Tengo map entries, merging new
entries into existing maps, and preserving raw literal formatting when values
are unchanged. It is used by the stilyagi CLI and unit tests to keep packaged
Vale scripts up to date with project-specific allow lists. The helpers expect
simple, flat maps where each entry ends with a trailing comma and braces do not
appear inside string values or comments; more complex Tengo structures are not
supported.

Examples
--------
    from pathlib import Path
    from concordat_vale.tengo_map import (
        MapValueType,
        parse_source_entries,
        update_tengo_map,
    )

    entries_provided, entries = parse_source_entries(
        Path("acronyms.txt"),
        MapValueType.TRUE,
    )
    result = update_tengo_map(
        Path("AcronymsFirstUse.tengo"),
        "allow",
        entries,
    )
    # AcronymsFirstUse.tengo rewritten with provided entries; result.updated
    # reports how many items changed.
"""

from __future__ import annotations

import dataclasses as dc
import enum
import json
import re
import typing as typ

if typ.TYPE_CHECKING:
    import collections.abc as cabc
    from pathlib import Path

MIN_QUOTED_VALUE_LENGTH: int = 2

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
    """Parse a source file into key/value pairs.

    Parameters
    ----------
    source : Path
        Path to the input file containing map entries.
    value_type : MapValueType
        Parsing mode that controls how values are coerced.

    Returns
    -------
    tuple[int, dict[str, object]]
        entries_provided is the number of parsed lines; parsed maps keys to
        their parsed values.

    Raises
    ------
    FileNotFoundError
        If the source file does not exist.
    TengoMapError
        For malformed tokens or unsupported value types.
    OSError
        If reading the source file fails.
    """
    if not source.exists():
        msg = f"Missing input file: {source}"
        raise FileNotFoundError(msg)

    entries_provided = 0
    parsed: dict[str, object] = {}
    for raw_line in source.read_text(encoding="utf-8").splitlines():
        processed = _process_source_line(raw_line, value_type)
        if processed is None:
            continue
        key, value = processed
        entries_provided += 1
        parsed[key] = value

    return entries_provided, parsed


def _process_source_line(
    raw_line: str, value_type: MapValueType
) -> tuple[str, object] | None:
    """Process a single source line, returning parsed key/value or None."""
    if not raw_line.strip():
        return None
    if re.match(r"^\s*#", raw_line):
        return None

    stripped = re.sub(r"\s+(#.*)?$", "", raw_line)
    token = stripped.strip()
    if not token:
        return None

    return _parse_token(token, value_type)


def update_tengo_map(
    tengo_path: Path,
    map_name: str,
    entries: cabc.Mapping[str, object],
) -> MapUpdateResult:
    """Update or append map entries inside a Tengo script.

    Parameters
    ----------
    tengo_path
        Path to the Tengo script containing the target map literal.
    map_name
        Name of the map binding to update (for example, ``allow``).
    entries
        Mapping of keys to values that should be merged into the map.

    Returns
    -------
    MapUpdateResult
        Summary of how many entries were updated and whether the file was
        rewritten.

    Raises
    ------
    FileNotFoundError
        If ``tengo_path`` does not exist.
    TengoMapError
        If the map cannot be located or the inputs cannot be parsed.

    Notes
    -----
    Expects a flat map where every entry sits on its own line, ends with a
    trailing comma, and does not contain braces inside values or comments. The
    brace matching is naive (counts all "{" and "}" characters), so braces
    embedded in strings or comments will break detection. Entries without a
    trailing comma are ignored and can lead to duplicate keys if updated.
    """
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

    context = _MapUpdateContext(
        lines=lines,
        entry_indent=entry_indent,
        closing_idx=end_idx,
    )
    updated = _apply_entries(context, existing, entries)
    lines = context.lines

    new_text = "\n".join(lines) + "\n"
    wrote_file = new_text != text
    if wrote_file:
        tengo_path.write_text(new_text, encoding="utf-8")
    return MapUpdateResult(updated=updated, wrote_file=wrote_file)


def _apply_entries(
    context: _MapUpdateContext,
    existing: dict[str, _Entry],
    entries: cabc.Mapping[str, object],
) -> int:
    """Update existing entries or insert new ones into the map lines."""
    entry_ctx = _EntryUpdateContext(
        lines=context.lines,
        existing=existing,
        entry_indent=context.entry_indent,
    )
    updated = 0
    current_closing_idx = context.closing_idx
    for key, value in entries.items():
        delta, current_closing_idx = _apply_single_entry(
            entry_ctx,
            key,
            value,
            current_closing_idx,
        )
        updated += delta
    context.closing_idx = current_closing_idx
    return updated


def _apply_single_entry(
    ctx: _EntryUpdateContext,
    key: str,
    value: object,
    closing_idx: int,
) -> tuple[int, int]:
    """Apply an update for a single key, returning delta-updated and new index."""
    lines = ctx.lines
    if key in ctx.existing:
        entry = ctx.existing[key]
        if _values_equal(entry.value, value):
            return 0, closing_idx
        lines[entry.index] = _render_entry(
            key=key,
            value=value,
            indent=entry.indent,
            comment=entry.comment,
        )
        return 1, closing_idx

    rendered_line = _render_entry(key, value, ctx.entry_indent, "")
    lines.insert(closing_idx, rendered_line)
    return 1, closing_idx + 1


@dc.dataclass(frozen=True)
class _Entry:
    index: int
    indent: str
    comment: str
    raw_value: str
    value: object


@dc.dataclass()
class _EntryUpdateContext:
    """Context for updating individual Tengo map entries."""

    lines: list[str]
    existing: dict[str, _Entry]
    entry_indent: str


@dc.dataclass()
class _MapUpdateContext:
    """Context for applying updates to Tengo map entries."""

    lines: list[str]
    entry_indent: str
    closing_idx: int


def _find_map_header(lines: list[str], map_name: str) -> tuple[int, str]:
    """Locate the map header line and return its index and indentation.

    Assumes a flat map layout without nested braces inside strings or comments.
    """
    pattern = re.compile(rf"^(?P<indent>\s*){re.escape(map_name)}\s*:=\s*\{{\s*$")
    for idx, line in enumerate(lines):
        if match := pattern.match(line):
            return idx, match.group("indent")
    msg = f"Could not find map {map_name!r} in Tengo script."
    raise TengoMapError(msg)


def _find_map_end(lines: list[str], start_idx: int) -> int:
    """Find the closing brace index by tracking brace depth from the start."""
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
    """Parse existing map entries and determine entry indentation.

    Expects each entry to end with a trailing comma and avoids nested maps.
    Braces inside values or comments are unsupported.
    """
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
    """Parse a source token into a key/value pair according to the value type."""
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

    parser = {
        MapValueType.STRING: _parse_string_value,
        MapValueType.BOOLEAN: _parse_boolean_value,
        MapValueType.NUMBER: _parse_numeric_value,
    }.get(value_type)

    if parser is None:  # pragma: no cover - defensive
        msg = f"Unsupported map value type: {value_type}"
        raise TengoMapError(msg)

    return key, parser(value)


def _parse_string_value(value: str) -> str:
    """Parse a string value, handling JSON-quoted and unquoted formats."""
    value = value.strip()
    if len(value) >= MIN_QUOTED_VALUE_LENGTH and value[0] == value[-1] == '"':
        try:
            return typ.cast("str", json.loads(value))
        except json.JSONDecodeError:
            return value.strip('"')
    return value


def _parse_boolean_value(value: str) -> bool:
    """Parse a boolean value from case-insensitive true or false."""
    lowered = value.strip().lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    msg = f"Expected true or false, got {value!r}"
    raise TengoMapError(msg)


def _parse_numeric_value(value: str) -> int | float:
    """Parse a numeric value, attempting integer then float."""
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
    """Parse an existing map value from Tengo syntax into a Python type."""
    stripped = raw.strip()
    parsers = [
        _try_parse_boolean,
        _try_parse_json_string,
        _try_parse_int,
        _try_parse_float,
    ]
    for parser in parsers:
        parsed = parser(stripped)
        if parsed is not None:
            return parsed
    return stripped


def _try_parse_boolean(value: str) -> bool | None:
    """Return True/False for boolean literals, otherwise None."""
    lowered = value.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    return None


def _try_parse_json_string(value: str) -> str | None:
    """Return decoded JSON string literal when surrounded by quotes."""
    if len(value) >= MIN_QUOTED_VALUE_LENGTH and value[0] == value[-1] == '"':
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value.strip('"')
    return None


def _try_parse_int(value: str) -> int | None:
    """Return int(value) if possible, else None."""
    try:
        return int(value)
    except ValueError:
        return None


def _try_parse_float(value: str) -> float | None:
    """Return float(value) if possible, else None."""
    try:
        return float(value)
    except ValueError:
        return None


def _values_equal(existing: object, new_value: object) -> bool:
    """Check semantic equality between existing and new values."""
    match (existing, new_value):
        case (int() | float(), int() | float()):
            return float(existing) == float(new_value)  # type: ignore[arg-type]
        case _:
            return existing == new_value


def _render_entry(key: str, value: object, indent: str, comment: str) -> str:
    """Render a complete map entry line with key, value, and optional comment."""
    rendered_value = _render_value(value)
    suffix = comment or ""
    return f'{indent}"{key}": {rendered_value},{suffix}'


def _render_value(value: object) -> str:
    """Render a Python value into Tengo literal syntax."""
    match value:
        case bool():
            return "true" if value else "false"
        case int() | float():
            return str(value)
        case _:
            return json.dumps(str(value))


__all__ = [
    "MapUpdateResult",
    "MapValueType",
    "TengoMapError",
    "parse_source_entries",
    "update_tengo_map",
]
