"""Unit tests for the generic Tengo map updater."""

from __future__ import annotations

import textwrap
import typing as typ

import pytest

from concordat_vale.tengo_map import (
    MapValueType,
    TengoMapError,
    parse_source_entries,
    update_tengo_map,
)

if typ.TYPE_CHECKING:
    from pathlib import Path

if __name__ == "__main__":  # pragma: no cover - defensive
    raise SystemExit


def _fmt(text: str) -> str:
    """Normalise snippets for file writes."""
    return textwrap.dedent(text).strip() + "\n"


def test_parse_source_entries_handles_comments_and_duplicates(tmp_path: Path) -> None:
    """Inline comments are stripped and later duplicates override earlier."""
    source = tmp_path / "entries.txt"
    source.write_text(
        _fmt(
            """
            # heading comment
            alpha    # trailing
            beta
            alpha
            """
        ),
        encoding="utf-8",
    )

    entries_provided, entries = parse_source_entries(source, MapValueType.TRUE)

    assert entries_provided == 3
    assert entries == {"alpha": True, "beta": True}


def test_parse_source_entries_supports_numeric_values(tmp_path: Path) -> None:
    """Numeric parsing accepts integers and keeps only the final value per key."""
    source = tmp_path / "entries.txt"
    source.write_text(
        _fmt(
            """
            alpha=1
            beta=2
            alpha=3 # override
            """
        ),
        encoding="utf-8",
    )

    entries_provided, entries = parse_source_entries(source, MapValueType.NUMBER)

    assert entries_provided == 3
    assert entries == {"alpha": 3, "beta": 2}


def test_parse_source_entries_rejects_invalid_boolean(tmp_path: Path) -> None:
    """Boolean parsing rejects non true/false tokens."""
    source = tmp_path / "entries.txt"
    source.write_text("maybe=perhaps\n", encoding="utf-8")

    with pytest.raises(TengoMapError):
        parse_source_entries(source, MapValueType.BOOLEAN)


def test_update_tengo_map_updates_existing_and_appends_new(tmp_path: Path) -> None:
    """Existing values are updated and new keys appended ahead of the closing brace."""
    tengo = tmp_path / "script.tengo"
    tengo.write_text(
        _fmt(
            """
            allow := {
              "EXISTING": false,
            }
            """
        ),
        encoding="utf-8",
    )

    result = update_tengo_map(
        tengo,
        "allow",
        {"EXISTING": True, "NEW": "added"},
    )

    expected = _fmt(
        """
        allow := {
          "EXISTING": true,
          "NEW": "added",
        }
        """
    )

    assert tengo.read_text(encoding="utf-8") == expected
    assert result.updated == 2
    assert result.wrote_file is True


def test_update_tengo_map_raises_when_map_missing(tmp_path: Path) -> None:
    """An explicit error is raised when the named map is absent."""
    tengo = tmp_path / "script.tengo"
    tengo.write_text("allow := {}\n", encoding="utf-8")

    with pytest.raises(TengoMapError):
        update_tengo_map(tengo, "missing", {"key": True})
