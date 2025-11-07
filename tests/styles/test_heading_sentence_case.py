"""Regression tests for the HeadingSentenceCase Vale rule."""

from __future__ import annotations

import textwrap
import typing as typ

if typ.TYPE_CHECKING:
    from tests.valedate import Valedate


def test_heading_sentence_case_flags_title_case_headings(
    concordat_vale: Valedate,
) -> None:
    """Vale raises a warning when a heading retains title case."""
    text = "# Overly Formal Title Case Heading\n\nBody text."

    diags = concordat_vale.lint(text)

    assert len(diags) == 1
    diag = diags[0]
    assert diag.check == "concordat.HeadingSentenceCase"
    assert diag.message == "Use sentence case for headings."
    assert diag.severity == "warning"
    assert diag.line == 1


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

    assert diags == []


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

    assert str(doc_path) in results
    alerts = results[str(doc_path)]
    assert len(alerts) == 2
    assert {alert.line for alert in alerts} == {1, 5}
    assert {alert.check for alert in alerts} == {"concordat.HeadingSentenceCase"}
