"""Regression tests for the OxfordComma Vale rule."""

from __future__ import annotations

import textwrap
import typing as typ

if typ.TYPE_CHECKING:
    from valedate import Valedate


def test_oxford_comma_flags_serial_comma_omission(
    concordat_vale: Valedate,
) -> None:
    """Vale should flag three-item lists missing the serial comma."""
    text = "The crate held apples, bananas and cherries."

    diags = concordat_vale.lint(text)

    assert len(diags) == 1, "expected one diagnostic for missing serial comma"
    diag = diags[0]
    assert diag.check == "concordat.OxfordComma", "unexpected rule triggered"
    assert diag.message == "Use the Oxford comma in lists of three or more items.", (
        "unexpected diagnostic message"
    )
    assert diag.severity == "warning", "rule should warn rather than error"
    assert diag.line == 1, "issue should be reported on the only line"


def test_oxford_comma_allows_serial_comma(
    concordat_vale: Valedate,
) -> None:
    """Proper Oxford comma usage must not raise diagnostics."""
    text = "The crate held apples, bananas, and cherries."

    diags = concordat_vale.lint(text)

    assert diags == [], "expected no diagnostics for correct serial comma"


def test_oxford_comma_reports_every_sentence_in_files(
    concordat_vale: Valedate,
) -> None:
    """lint_path should return an alert for each offending sentence in a file."""
    doc_path = concordat_vale.root / "lists.md"
    doc_path.write_text(
        textwrap.dedent(
            """\
            The checklist covers power, cooling and networking.

            The summary references design, delivery and adoption.
            """
        ),
        encoding="utf-8",
    )

    results = concordat_vale.lint_path(doc_path)

    assert str(doc_path) in results, "expected lint_path to key by document path"
    alerts = results[str(doc_path)]
    assert len(alerts) == 2, "expected two diagnostics for the two sentences"
    assert {alert.line for alert in alerts} == {1, 3}, "incorrect lines flagged"
    assert {alert.check for alert in alerts} == {"concordat.OxfordComma"}, (
        "unexpected rule triggered for file-based linting"
    )


def test_oxford_comma_ignores_code_fenced_examples(
    concordat_vale: Valedate,
) -> None:
    """Code fences should not be linted for prose-only rules."""
    text = textwrap.dedent(
        """\
        ```
        apples, bananas and cherries
        ```

        Reference output only.
        """
    )

    diags = concordat_vale.lint(text)

    assert diags == [], "expected no diagnostics from code-fenced content"


def test_oxford_comma_handles_em_dash_series(
    concordat_vale: Valedate,
) -> None:
    """Lists that trail into an em dash should still be validated."""
    text = "The menu lists soup, salad and bread—classic fare."

    diags = concordat_vale.lint(text)

    assert len(diags) == 1, "missing comma before em dash should be flagged"
    assert diags[0].check == "concordat.OxfordComma", "unexpected rule triggered"


def test_oxford_comma_flags_parenthetical_series(
    concordat_vale: Valedate,
) -> None:
    """Parenthetical clauses should not suppress missing serial comma alerts."""
    text = "The report tracks design, delivery and adoption (all quarterly)."

    diags = concordat_vale.lint(text)

    assert len(diags) == 1, "expected diagnostic for parenthetical list"
    assert diags[0].check == "concordat.OxfordComma", "unexpected rule triggered"


def test_oxford_comma_allows_parenthetical_with_serial_comma(
    concordat_vale: Valedate,
) -> None:
    """Parenthetical lists with the Oxford comma should be allowed."""
    text = "The report tracks design, delivery, and adoption (all quarterly)."

    diags = concordat_vale.lint(text)

    assert diags == [], "expected no diagnostics when comma precedes the conjunction"


def test_oxford_comma_ignores_with_or_without_clause(
    concordat_vale: Valedate,
) -> None:
    """Phrases like 'with or without fee' are not serial lists."""
    text = textwrap.dedent(
        """
        ISC Licence — because that’s how we roll. You’re free to use, copy, modify, and
        distribute this software for any purpose, with or without fee, and provided
        that the copyright notice and this permission notice are included in all
        copies.
        """
    )

    diags = concordat_vale.lint(text)

    assert all(diag.check != "concordat.OxfordComma" for diag in diags), (
        "with/without clause should not be treated as a three-item list"
    )


def test_oxford_comma_ignores_capitalized_with_or_without(
    concordat_vale: Valedate,
) -> None:
    """Capitalized subordinator clauses must also be exempt from the rule."""
    text = "With or without fee, and provided notice remains, distribution is fine."

    diags = concordat_vale.lint(text)

    assert all(diag.check != "concordat.OxfordComma" for diag in diags), (
        "Capitalized 'With or without' clause should not trigger OxfordComma"
    )


def test_oxford_comma_ignores_because_clauses_without_serial_comma(
    concordat_vale: Valedate,
) -> None:
    """Clauses starting with subordinators shouldn't be treated as lists."""
    text = "We paused, because of outages, and because of staffing."

    diags = concordat_vale.lint(text)

    assert all(diag.check != "concordat.OxfordComma" for diag in diags), (
        "Subordinator-led clause should not be flagged as a missing Oxford comma"
    )


def test_oxford_comma_ignores_relative_clause_after_comma(
    concordat_vale: Valedate,
) -> None:
    """Relative clauses like ', which ... and ...' should not be treated as lists."""
    text = textwrap.dedent(
        """
        The primary goal of this phase is to validate the core architectural decision:
        using `inventory` for link-time collection of step definitions, which are then
        discovered and executed by a procedural macro at runtime.
        """
    )

    diags = concordat_vale.lint(text)

    assert all(diag.check != "concordat.OxfordComma" for diag in diags), (
        "Relative clauses starting with 'which' should not trigger OxfordComma"
    )
