"""Unit tests for the acronym allow-list updater."""

from __future__ import annotations

import textwrap
import typing as typ

import pytest

from concordat_vale import acronym_allowlist as al

if typ.TYPE_CHECKING:
    from pathlib import Path


def _fmt(text: str) -> str:
    """Normalise multi-line snippets for readability in tests."""
    return textwrap.dedent(text).strip() + "\n"


def test_load_project_acronyms_parses_tokens(tmp_path: Path) -> None:
    """Comments are ignored and tokens are uppercased/deduplicated."""
    source = tmp_path / "common-acronyms"
    source.write_text(
        _fmt(
            """
            # comment
            ci
            CD
            CI
            OKR
            """
        ),
        encoding="utf-8",
    )

    acronyms = al.load_project_acronyms(source)

    assert acronyms == ["CI", "CD", "OKR"]


def test_load_project_acronyms_rejects_invalid(tmp_path: Path) -> None:
    """Slash-delimited acronyms raise an error."""
    source = tmp_path / "common-acronyms"
    source.write_text("CI/CD\n", encoding="utf-8")

    with pytest.raises(al.AcronymAllowlistError):
        al.load_project_acronyms(source)


def test_update_allow_map_inserts_block(tmp_path: Path) -> None:
    """New acronyms are inserted ahead of the Roman numeral block."""
    tengo = tmp_path / "AcronymsFirstUse.tengo"
    tengo.write_text(
        _fmt(
            """
            allow := {
              "API": true,
              "YAML": true,

              // Roman numerals appearing in API names
              "II": true,
            }
            """
        ),
        encoding="utf-8",
    )

    result = al.update_allow_map(tengo, ["CI", "SLA"])

    expected = _fmt(
        """
        allow := {
          "API": true,
          "YAML": true,

          // Project-specific acronyms (imported from .config/common-acronyms)
          "CI": true,
          "SLA": true,

          // Roman numerals appearing in API names
          "II": true,
        }
        """
    )

    assert tengo.read_text(encoding="utf-8") == expected
    assert result.wrote_file is True
    assert result.managed_entries == ("CI", "SLA")


def test_update_allow_map_skips_existing_entries(tmp_path: Path) -> None:
    """Existing entries are not duplicated in the inserted block."""
    tengo = tmp_path / "AcronymsFirstUse.tengo"
    tengo.write_text(
        _fmt(
            """
            allow := {
              "CI": true,

              // Roman numerals appearing in API names
              "II": true,
            }
            """
        ),
        encoding="utf-8",
    )

    result = al.update_allow_map(tengo, ["CI", "SLO"])

    expected = _fmt(
        """
        allow := {
          "CI": true,

          // Project-specific acronyms (imported from .config/common-acronyms)
          "SLO": true,

          // Roman numerals appearing in API names
          "II": true,
        }
        """
    )
    assert tengo.read_text(encoding="utf-8") == expected
    assert result.managed_entries == ("SLO",)


def test_update_allow_map_removes_block_when_empty(tmp_path: Path) -> None:
    """Empty sources remove previously inserted allow-list entries."""
    tengo = tmp_path / "AcronymsFirstUse.tengo"
    tengo.write_text(
        _fmt(
            """
            allow := {
              "API": true,

              // Project-specific acronyms (imported from .config/common-acronyms)
              "CI": true,

              // Roman numerals appearing in API names
              "II": true,
            }
            """
        ),
        encoding="utf-8",
    )

    result = al.update_allow_map(tengo, [])

    expected = _fmt(
        """
        allow := {
          "API": true,

          // Roman numerals appearing in API names
          "II": true,
        }
        """
    )
    assert tengo.read_text(encoding="utf-8") == expected
    assert result.managed_entries == ()
    assert result.wrote_file is True
