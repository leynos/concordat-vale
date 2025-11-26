"""Validate the CommaBeforeCoordConj Vale rule.

These regression tests ensure Vale warns when the style detects two
independent clauses joined by ``nor``, ``but``, ``yet``, or ``so`` without an
intervening comma, while allowing constructions that share a subject, use
"so that" purpose clauses, or already include the punctuation. The suite mixes
positive matches, negative controls, and tricky bridge-word examples so the
regex heuristics remain stable across prose formats.

Run with ``pytest tests/styles/test_comma_before_coord_conj.py`` (or
``pytest -m styles`` if grouped) to lint synthetic paragraphs via the
``Valedate`` helper; a passing run reports six successful tests and zero
failures, confirming the rule catches true errors without false positives.
"""

from __future__ import annotations

import textwrap
import typing as typ

if typ.TYPE_CHECKING:
    from valedate import Valedate


def test_comma_before_coord_conj_flags_missing_comma_with_but(
    concordat_vale: Valedate,
) -> None:
    """Vale should flag independent clauses joined by "but" without a comma."""
    text = "The scheduler drained capacity but engineers maintained the batch schedule."

    diags = concordat_vale.lint(text)

    assert len(diags) == 1, "expected one diagnostic for missing comma"
    diag = diags[0]
    assert diag.check == "concordat.CommaBeforeCoordConj", "unexpected rule triggered"
    assert diag.message.startswith(
        "Add a comma before the coordinating conjunction:"
    ), "diagnostic should explain the missing comma"
    assert "but" in diag.message, "expected the conjunction to appear in the message"
    assert diag.message.endswith("joins two independent clauses."), (
        "diagnostic should describe the paired independent clauses"
    )
    assert diag.severity == "warning", "rule should warn rather than error"
    assert diag.line == 1, "issue should be reported on the first line"


def test_comma_before_coord_conj_allows_existing_comma(
    concordat_vale: Valedate,
) -> None:
    """Clauses already separated by a comma should not raise diagnostics."""
    text = "The cache warmed, yet the hit rate stayed low."

    diags = concordat_vale.lint(text)

    assert diags == [], "expected no diagnostics when comma precedes the conjunction"


def test_comma_before_coord_conj_reports_each_sentence_in_files(
    concordat_vale: Valedate,
) -> None:
    """lint_path should emit diagnostics for every offending sentence in a file."""
    doc_path = concordat_vale.root / "clauses.md"
    doc_path.write_text(
        textwrap.dedent(
            """\
            The shard rebuilt but operators ensured traffic compliance.

            The monitors stabilized so engineers started backups.
            """
        ),
        encoding="utf-8",
    )

    results = concordat_vale.lint_path(doc_path)

    assert str(doc_path) in results, "expected lint_path to include document path"
    alerts = results[str(doc_path)]
    assert len(alerts) == 2, "expected two diagnostics for the two sentences"
    assert {alert.line for alert in alerts} == {1, 3}, "incorrect lines flagged"
    assert {alert.check for alert in alerts} == {"concordat.CommaBeforeCoordConj"}, (
        "unexpected rule triggered in file-based linting"
    )


def test_comma_before_coord_conj_does_not_flag_shared_subject_clauses(
    concordat_vale: Valedate,
) -> None:
    """Clauses that reuse the subject should not trigger the rule."""
    text = "The pipeline failed but recovered gracefully."

    diags = concordat_vale.lint(text)

    assert diags == [], "expected no diagnostics when the second clause lacks a subject"


def test_comma_before_coord_conj_ignores_so_that_purpose_clause(
    concordat_vale: Valedate,
) -> None:
    """Purpose clauses introduced by "so that" are explicitly excluded."""
    text = "Enable caching so that responses remain warm."

    diags = concordat_vale.lint(text)

    assert diags == [], 'expected no diagnostics for "so that" constructions'


def test_comma_before_coord_conj_flags_bridge_words_before_subject(
    concordat_vale: Valedate,
) -> None:
    """Bridge words should not hide missing commas before coordinating conjunctions."""
    text = "The release stalled yet within minutes engineers started recovery."

    diags = concordat_vale.lint(text)

    assert len(diags) == 1, "expected a diagnostic despite bridge words"
    assert diags[0].check == "concordat.CommaBeforeCoordConj", (
        "unexpected rule triggered"
    )
