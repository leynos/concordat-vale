"""Regression tests for the HeadingSentenceCase Vale rule."""

from __future__ import annotations

import textwrap
import typing as typ

if typ.TYPE_CHECKING:
    from valedate import Valedate


def test_heading_sentence_case_flags_title_case_headings(
    concordat_vale: Valedate,
) -> None:
    """Vale raises a warning when a heading retains title case."""
    text = "# Overly Formal Title Case Heading\n\nBody text."

    diags = concordat_vale.lint(text)

    assert len(diags) == 1, "expected exactly one diagnostic in title-case heading"
    diag = diags[0]
    assert diag.check == "concordat.HeadingSentenceCase", (
        "unexpected rule triggered for title-case heading"
    )
    assert diag.message == "Use sentence case for headings.", (
        "unexpected diagnostic message"
    )
    assert diag.severity == "warning", "diagnostic should warn rather than error"
    assert diag.line == 1, "heading should be reported on the first line"


def test_heading_sentence_case_allows_sentence_case_headings(
    concordat_vale: Valedate,
) -> None:
    """Sentence-case headings, even with acronyms, should pass."""
    text = textwrap.dedent(
        """\
        # Keep headings in sentence case

        ## API gateway internals for maintainers

        Content paragraph.
        """
    )

    diags = concordat_vale.lint(text)

    assert diags == [], "expected no diagnostics for sentence-case headings"


def test_heading_sentence_case_reports_each_heading_in_files(
    concordat_vale: Valedate,
) -> None:
    """File-based linting should capture every offending heading."""
    doc_path = concordat_vale.root / "doc.md"
    doc_path.write_text(
        textwrap.dedent(
            """\
            # Totally Title Case Heading

            Leading paragraph.

            ## Another Improper Title
            """
        ),
        encoding="utf-8",
    )

    results = concordat_vale.lint_path(doc_path)

    assert str(doc_path) in results, "expected lint_path to return doc diagnostics"
    alerts = results[str(doc_path)]
    assert len(alerts) == 2, "expected both headings to raise diagnostics"
    assert {alert.line for alert in alerts} == {1, 5}, "incorrect lines flagged"
    assert {alert.check for alert in alerts} == {"concordat.HeadingSentenceCase"}, (
        "unexpected rule triggered"
    )


def test_heading_sentence_case_allows_body_only_files(
    concordat_vale: Valedate,
) -> None:
    """Body-only files should not produce heading diagnostics."""
    doc_path = concordat_vale.root / "body.md"
    doc_path.write_text(
        textwrap.dedent(
            """\
            Some paragraph text without headings.

            Another paragraph, still without heading markers.
            """
        ),
        encoding="utf-8",
    )

    results = concordat_vale.lint_path(doc_path)

    alerts = results.get(str(doc_path), [])
    assert alerts == [], "expected no diagnostics for body-only document"
