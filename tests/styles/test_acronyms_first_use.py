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


def test_acronyms_first_use_flags_unexpanded_acronyms(
    concordat_vale: Valedate,
) -> None:
    """Simple acronyms without definitions should still be reported."""
    diags = _acronym_diagnostics(
        concordat_vale,
        "NASA plans a launch window next month.",
    )

    assert len(diags) == 1, "expected NASA to require an expansion"
    diag = diags[0]
    assert diag.severity == "warning", "AcronymsFirstUse should warn on first use"
    assert diag.line == 1, "single-line acronym should report on line 1"


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


def test_acronyms_first_use_ignores_camelcase_technologies(
    concordat_vale: Valedate,
) -> None:
    """CamelCase technologies like GraphQL should avoid fragment flags."""
    diags = _acronym_diagnostics(
        concordat_vale,
        "GraphQL resolvers validate inputs before forwarding.",
    )

    assert diags == [], "expected GraphQL to be ignored by acronym detection"


def test_acronyms_first_use_ignores_joined_acronyms_split_by_slash(
    concordat_vale: Valedate,
) -> None:
    """Joined acronyms such as TLS/SSL should be treated as one token."""
    diags = _acronym_diagnostics(
        concordat_vale,
        "Renew TLS/SSL certificates before expiry.",
    )

    assert diags == [], "expected TLS/SSL fragments to be ignored"
