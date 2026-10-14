"""Regression tests for the AcronymsFirstUse Vale rule."""

from __future__ import annotations

import typing as typ

import pytest

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    from valedate import Valedate, ValeDiagnostic


def _acronym_diagnostics(concordat_vale: Valedate, text: str) -> list[ValeDiagnostic]:
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


def test_acronyms_first_use_flags_mid_sentence_acronym(
    concordat_vale: Valedate,
) -> None:
    """Acronyms following words should still require expansion."""
    diags = _acronym_diagnostics(
        concordat_vale,
        "Visit NASA headquarters for a tour.",
    )

    assert len(diags) == 1, "expected NASA to require an expansion mid-sentence"
    assert diags[0].line == 1, "mid-sentence acronym should still report on line 1"


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


@pytest.mark.parametrize(
    ("prefix", "expected_span"),
    [
        pytest.param("a" * 2048, (2050, 2053), id="plain2048"),
        pytest.param("[" * 2048, (2050, 2053), id="brackets2048"),
        pytest.param("a" * 4096, (4098, 4101), id="plain4096"),
        pytest.param("[" * 4096, (4098, 4101), id="brackets4096"),
    ],
)
def test_acronyms_first_use_completes_dense_prefixes(
    concordat_vale: Valedate,
    prefix: str,
    expected_span: tuple[int, int],
) -> None:
    """Dense unmatched brackets must retain a reachable first-use warning."""
    diags = _acronym_diagnostics(concordat_vale, f"{prefix} NASA")

    actual = [(diag.match, diag.severity, diag.line, diag.span) for diag in diags]
    assert actual == [("NASA", "warning", 1, expected_span)], (
        "the dense prefix must finish without changing the NASA diagnostic"
    )


@pytest.mark.parametrize(
    "text",
    [
        pytest.param(
            "[[ <https://example.org/ESA> NASA",
            id="later-autolink-after-exhausted-search",
        ),
        pytest.param("[[ `] ESA` NASA", id="closing-bracket-masked-in-code"),
        pytest.param(
            "[[ `] ESA` label](https://example.org/JAXA) NASA",
            id="later-eligible-closing-bracket",
        ),
        pytest.param(
            "[label](https://example.org/JAXA_(ESA)) NASA",
            id="nested-parentheses-in-link-target",
        ),
    ],
)
def test_acronyms_first_use_preserves_link_masking(
    concordat_vale: Valedate,
    text: str,
) -> None:
    """Link and code masking must leave the outside acronym reachable."""
    diags = _acronym_diagnostics(concordat_vale, text)

    start = text.index("NASA") + 1
    actual = [(diag.match, diag.severity, diag.line, diag.span) for diag in diags]
    assert actual == [("NASA", "warning", 1, (start, start + 3))], (
        "only the outside NASA must be reported at its original ASCII span"
    )


def test_acronyms_first_use_preserves_prior_definitions(
    concordat_vale: Valedate,
) -> None:
    """An earlier expansion must continue to silence subsequent uses."""
    diags = _acronym_diagnostics(
        concordat_vale,
        "National Aeronautics and Space Administration (NASA) uses NASA.",
    )

    assert diags == [], "the prior NASA expansion must remain effective"


def test_acronyms_first_use_reports_only_the_first_repeated_use(
    concordat_vale: Valedate,
) -> None:
    """Repeated undefined acronyms must retain the first occurrence's span."""
    diags = _acronym_diagnostics(concordat_vale, "NASA revisits NASA.")

    actual = [(diag.match, diag.severity, diag.line, diag.span) for diag in diags]
    assert actual == [("NASA", "warning", 1, (1, 4))], (
        "only the first undefined NASA must be reported"
    )


def test_acronyms_first_use_preserves_warning_before_later_definition(
    concordat_vale: Valedate,
) -> None:
    """A later expansion must not erase an earlier first-use warning."""
    diags = _acronym_diagnostics(
        concordat_vale,
        "NASA meets National Aeronautics and Space Administration (NASA).",
    )

    actual = [(diag.match, diag.severity, diag.line, diag.span) for diag in diags]
    assert actual == [("NASA", "warning", 1, (1, 4))], (
        "the earlier undefined NASA must retain its original diagnostic"
    )


def test_acronyms_first_use_records_span_after_multibyte_prefix(
    concordat_vale: Valedate,
    record_property: cabc.Callable[[str, object], None],
) -> None:
    """A multibyte prefix must retain the measured diagnostic span."""
    diags = _acronym_diagnostics(concordat_vale, "Élan NASA")

    actual = [(diag.match, diag.severity, diag.line, diag.span) for diag in diags]
    assert actual == [("NASA", "warning", 1, (6, 9))], (
        "the multibyte prefix must preserve the measured NASA diagnostic span"
    )
    record_property("vale_multibyte_span", diags[0].span)
