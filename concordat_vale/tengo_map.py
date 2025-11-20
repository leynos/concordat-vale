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
    r'^(?P<indent>\s*)"(?P<key>[^"\\]+)"\s*:\s*(?P<value>[^,]+),'
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
    entry_indent = _determine_entry_indent(lines, start_idx + 1, end_idx, map_indent)
    existing = _collect_entries(lines, start_idx + 1, end_idx)

    updated = 0
    updated, lines = _process_entries(
        lines,
        entries,
        existing,
        entry_indent,
        end_idx,
    )

    new_text = "\n".join(lines) + "\n"
    wrote_file = new_text != text
    if wrote_file:
        tengo_path.write_text(new_text, encoding="utf-8")
    return MapUpdateResult(updated=updated, wrote_file=wrote_file)


def _process_entries(
    lines: list[str],
    entries: cabc.Mapping[str, object],
    existing: dict[str, _Entry],
    entry_indent: str,
    closing_idx: int,
) -> tuple[int, list[str]]:
    updated = 0
    current_closing_idx = closing_idx
    for key, value in entries.items():
        delta, current_closing_idx = _apply_entry_updates(
            lines,
            existing,
            key,
            value,
            entry_indent,
            current_closing_idx,
        )
        updated += delta
    return updated, lines


def _apply_entry_updates(
    lines: list[str],
    existing: dict[str, _Entry],
    key: str,
    value: object,
    entry_indent: str,
    closing_idx: int,
) -> tuple[int, int]:
    if key in existing:
        entry = existing[key]
        if _values_equal(entry.value, value):
            return 0, closing_idx
        _update_existing_entry(lines, entry, key, value)
        return 1, closing_idx

    _insert_new_entry(lines, closing_idx, key, value, entry_indent)
    return 1, closing_idx + 1


def _update_existing_entry(lines: list[str], entry: _Entry, key: str, value: object) -> None:
    lines[entry.index] = _render_entry(
        key,
        value,
        entry.indent,
        entry.comment,
    )


def _insert_new_entry(
    lines: list[str],
    position: int,
    key: str,
    value: object,
    indent: str,
) -> None:
    lines.insert(
        position,
        _render_entry(key, value, indent, ""),
    )


@dc.dataclass(frozen=True)
class _Entry:
    index: int
    indent: str
    comment: str
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


def _determine_entry_indent(
    lines: list[str], start: int, end: int, map_indent: str
) -> str:
    for idx in range(start, end):
        if match := ENTRY_PATTERN.match(lines[idx]):
            return match.group("indent")
    return f"{map_indent}  "


def _collect_entries(lines: list[str], start: int, end: int) -> dict[str, _Entry]:
    entries: dict[str, _Entry] = {}
    for idx in range(start, end):
        line = lines[idx]
        match = ENTRY_PATTERN.match(line)
        if not match:
            continue
        key = match.group("key")
        entries[key] = _Entry(
            index=idx,
            indent=match.group("indent"),
            comment=match.group("comment") or "",
            value=_parse_existing_value(match.group("value").strip()),
        )
    return entries


def _parse_token(token: str, value_type: MapValueType) -> tuple[str, object]:
    if value_type is MapValueType.TRUE:
        return token, True

    key, value = _extract_key_value(token)
    parser = _get_value_parser(value_type)
    return key, parser(value)


def _extract_key_value(token: str) -> tuple[str, str]:
    if "=" not in token:
        msg = "Source lines must include '=' when using typed modes."
        raise TengoMapError(msg)

    key, raw_value = token.split("=", 1)
    key = key.strip()
    value = raw_value.strip()
    if not key:
        msg = "Map keys may not be empty."
        raise TengoMapError(msg)

    return key, value


def _get_value_parser(value_type: MapValueType) -> cabc.Callable[[str], object]:
    parsers: dict[MapValueType, cabc.Callable[[str], object]] = {
        MapValueType.STRING: _parse_string_value,
        MapValueType.BOOLEAN: _parse_boolean_value,
        MapValueType.NUMBER: _parse_numeric_value,
    }

    try:
        return parsers[value_type]
    except KeyError as exc:  # pragma: no cover - defensive
        msg = f"Unsupported map value type: {value_type}"
        raise TengoMapError(msg) from exc


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
    parsers = [
        _try_parse_boolean,
        _try_parse_json_string,
        _try_parse_int,
        _try_parse_float,
    ]

    for parser in parsers:
        if parsed := parser(stripped):
            return parsed
    return stripped


def _try_parse_boolean(raw: str) -> bool | None:
    lowered = raw.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    return None


def _try_parse_json_string(raw: str) -> str | None:
    if len(raw) >= 2 and raw[0] == raw[-1] == '"':
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw.strip('"')
    return None


def _try_parse_int(raw: str) -> int | None:
    try:
        return int(raw)
    except ValueError:
        return None


def _try_parse_float(raw: str) -> float | None:
    try:
        return float(raw)
    except ValueError:
        return None


def _values_equal(existing: object, new_value: object) -> bool:
    if isinstance(existing, (int, float)) and isinstance(new_value, (int, float)):
        return float(existing) == float(new_value)
    return existing == new_value


def _render_entry(key: str, value: object, indent: str, comment: str) -> str:
    rendered_value = _render_value(value)
    suffix = comment if comment else ""
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
