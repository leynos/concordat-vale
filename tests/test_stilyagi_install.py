"""Unit tests for the stilyagi install helpers."""

from __future__ import annotations

import typing as typ

from concordat_vale import stilyagi

if typ.TYPE_CHECKING:
    from pathlib import Path


def test_update_vale_ini_merges_existing_values(tmp_path: Path) -> None:
    """Ensure required entries are inserted while preserving existing ones."""
    ini_path = tmp_path / ".vale.ini"
    ini_path.write_text(
        """StylesPath = styles

[legacy]
BasedOnStyles = Vale
""",
        encoding="utf-8",
    )

    stilyagi._update_vale_ini(  # type: ignore[attr-defined]
        ini_path=ini_path,
        style_name="concordat",
        packages_url="https://example.test/v9.9.9/concordat-9.9.9.zip",
    )

    body = ini_path.read_text(encoding="utf-8")
    assert "Packages = https://example.test/v9.9.9/concordat-9.9.9.zip" in body
    assert "MinAlertLevel = warning" in body
    assert "Vocab = concordat" in body
    assert "StylesPath = styles" in body, "Existing root option should be preserved"
    assert "[legacy]" in body, "Existing sections should be retained"
    assert "BlockIgnores = (?m)^\\[\\^\\d+\\]:" in body


def test_update_makefile_adds_phony_and_target(tmp_path: Path) -> None:
    """Replace any existing vale target and merge .PHONY entries."""
    makefile = tmp_path / "Makefile"
    makefile.write_text(
        """.PHONY: test

vale: ## old target
\t@echo outdated

lint:
\t@echo lint
""",
        encoding="utf-8",
    )

    stilyagi._update_makefile(makefile)  # type: ignore[attr-defined]

    contents = makefile.read_text(encoding="utf-8")
    assert ".PHONY: test vale" in contents
    assert "vale: $(VALE) $(ACRONYM_SCRIPT) ## Check prose" in contents
    assert "\t$(VALE) sync" in contents
    assert "\t$(VALE) --no-global ." in contents
    assert "lint:" in contents, "Other targets should remain intact"
