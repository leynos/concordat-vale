"""Unit tests for the generic Tengo map updater."""

from __future__ import annotations

import dataclasses as dc
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


@dc.dataclass(frozen=True)
class _ParseTestCase:
    """Test case for parse_source_entries."""

    contents: str
    value_type: MapValueType
    expected_count: int
    expected_entries: dict[str, object]


@pytest.mark.parametrize(
    "test_case",
    [
        _ParseTestCase(
            contents=_fmt(
                """
                # heading comment
                alpha    # trailing
                beta
                alpha
                """
            ),
            value_type=MapValueType.TRUE,
            expected_count=3,
            expected_entries={"alpha": True, "beta": True},
        ),
        _ParseTestCase(
            contents=_fmt(
                """
                alpha=1
                beta=2
                alpha=3 # override
                """
            ),
            value_type=MapValueType.NUMBER,
            expected_count=3,
            expected_entries={"alpha": 3, "beta": 2},
        ),
    ],
)
def test_parse_source_entries_basic_modes(
    tmp_path: Path,
    test_case: _ParseTestCase,
) -> None:
    """Parse entries for TRUE and NUMBER modes with comments and overrides."""
    source = tmp_path / "entries.txt"
    source.write_text(test_case.contents, encoding="utf-8")

    entries_provided, entries = parse_source_entries(source, test_case.value_type)

    assert entries_provided == test_case.expected_count, (
        "entries_provided should match input lines"
    )
    assert entries == test_case.expected_entries, (
        "entries mapping should match expected values"
    )


def test_parse_source_entries_supports_float_values(tmp_path: Path) -> None:
    """Numeric parsing accepts floating-point values."""
    source = tmp_path / "entries.txt"
    source.write_text(
        _fmt(
            """
            alpha=1.5
            beta=2.25
            """
        ),
        encoding="utf-8",
    )

    entries_provided, entries = parse_source_entries(source, MapValueType.NUMBER)

    assert entries_provided == 2
    assert entries["alpha"] == pytest.approx(1.5)
    assert entries["beta"] == pytest.approx(2.25)


def test_parse_source_entries_rejects_invalid_boolean(tmp_path: Path) -> None:
    """Boolean parsing rejects non true/false tokens."""
    source = tmp_path / "entries.txt"
    source.write_text("maybe=perhaps\n", encoding="utf-8")

    with pytest.raises(TengoMapError):
        parse_source_entries(source, MapValueType.BOOLEAN)


def test_parse_source_entries_invalid_numeric_raises(tmp_path: Path) -> None:
    """Non-numeric values with numeric parsing raise TengoMapError."""
    source = tmp_path / "entries.txt"
    source.write_text(
        _fmt(
            """
            alpha=abc
            """
        ),
        encoding="utf-8",
    )

    with pytest.raises(TengoMapError):
        parse_source_entries(source, MapValueType.NUMBER)


def test_parse_source_entries_string_values_with_quoted_and_unquoted(
    tmp_path: Path,
) -> None:
    """STRING values support unquoted, quoted, and escaped-quote values."""
    source = tmp_path / "entries_string.txt"
    source.write_text(
        _fmt(
            r"""
            key_unquoted=foo
            key_double_quoted="bar baz"
            key_single_quoted="qux"
            key_escaped="a \"quoted\" value"
            """
        ),
        encoding="utf-8",
    )

    entries_provided, entries = parse_source_entries(source, MapValueType.STRING)

    assert entries_provided == 4
    assert entries == {
        "key_unquoted": "foo",
        "key_double_quoted": "bar baz",
        "key_single_quoted": "qux",
        "key_escaped": 'a "quoted" value',
    }


def test_parse_source_entries_boolean_values_various_casings(tmp_path: Path) -> None:
    """BOOLEAN values accept true/false in various casings."""
    source = tmp_path / "entries_bool.txt"
    source.write_text(
        _fmt(
            """
            alpha=true
            beta=FALSE
            gamma=True
            delta=false
            """
        ),
        encoding="utf-8",
    )

    entries_provided, entries = parse_source_entries(source, MapValueType.BOOLEAN)

    assert entries_provided == 4
    assert entries == {
        "alpha": True,
        "beta": False,
        "gamma": True,
        "delta": False,
    }


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

    assert tengo.read_text(encoding="utf-8") == expected, (
        "script.tengo contents should match the updated map"
    )
    assert result.updated == 2, (
        "result.updated should count both updated and newly inserted entries"
    )
    assert result.wrote_file is True, (
        "result.wrote_file should indicate the script was rewritten"
    )


def test_update_tengo_map_noop_when_values_unchanged(tmp_path: Path) -> None:
    """No-op when existing map matches new entries exactly."""
    tengo = tmp_path / "script.tengo"
    tengo.write_text(
        _fmt(
            """
            allow := {
              "BOOL": true,
              "INT_AS_INT": 10,
              "INT_AS_FLOAT": 10,
              "FLOAT_AS_FLOAT": 10.0,
              "STRING": "value",
            }
            """
        ),
        encoding="utf-8",
    )

    result = update_tengo_map(
        tengo,
        "allow",
        {
            "BOOL": True,
            "INT_AS_INT": 10,
            "INT_AS_FLOAT": 10.0,
            "FLOAT_AS_FLOAT": 10.0,
            "STRING": "value",
        },
    )

    expected = _fmt(
        """
        allow := {
          "BOOL": true,
          "INT_AS_INT": 10,
          "INT_AS_FLOAT": 10,
          "FLOAT_AS_FLOAT": 10.0,
          "STRING": "value",
        }
        """
    )

    assert tengo.read_text(encoding="utf-8") == expected
    assert result.updated == 0, "result.updated should be zero for no-op"
    assert result.wrote_file is False, "result.wrote_file should indicate no write"


def test_update_tengo_map_raises_when_map_missing(tmp_path: Path) -> None:
    """An explicit error is raised when the named map is absent."""
    tengo = tmp_path / "script.tengo"
    tengo.write_text("allow := {}\n", encoding="utf-8")

    with pytest.raises(TengoMapError):
        update_tengo_map(tengo, "missing", {"key": True})


def test_update_tengo_map_inserts_into_empty_map(tmp_path: Path) -> None:
    """Entries are inserted with fallback indentation when map is empty."""
    tengo = tmp_path / "script.tengo"
    tengo.write_text(
        _fmt(
            """
            allow := {
            }
            """
        ),
        encoding="utf-8",
    )

    result = update_tengo_map(tengo, "allow", {"NEW": True})

    expected = _fmt(
        """
        allow := {
          "NEW": true,
        }
        """
    )

    assert tengo.read_text(encoding="utf-8") == expected, "entry should be inserted"
    assert result.updated == 1, "result.updated should count the inserted entry"
    assert result.wrote_file is True, "result.wrote_file should reflect the change"
