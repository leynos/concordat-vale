"""Regression tests for the AcronymsFirstUse Vale rule."""

from __future__ import annotations

import typing as typ

if typ.TYPE_CHECKING:
    from valedate import Valedate


def _acronym_diagnostics(concordat_vale: Valedate, text: str) -> list:
    """Return AcronymsFirstUse diagnostics for the provided text."""
    return [
        diag
        for diag in concordat_vale.lint(text)
        if diag.check == "concordat.AcronymsFirstUse"
    ]


def test_acronyms_first_use_ignores_composite_tokens(
    concordat_vale: Valedate,
) -> None:
    """Composite uppercase words (for example, TL;DR) should pass silently."""
    diags = _acronym_diagnostics(
        concordat_vale,
        "TL;DR: Summarise the change at the top of the note.",
    )

    assert diags == [], "expected TL;DR to be ignored by acronym detection"


def test_acronyms_first_use_ignores_mixed_case_brand_names(
    concordat_vale: Valedate,
) -> None:
    """Mixed-case brand names such as PyPI should not trigger the rule."""
    diags = _acronym_diagnostics(
        concordat_vale,
        "Publish the package to PyPI after tagging.",
    )

    assert diags == [], "expected PyPI to be ignored by acronym detection"
