"""Regression tests for the PreferOur Vale rule."""

from __future__ import annotations

import textwrap
import typing as typ

if typ.TYPE_CHECKING:
    from test_helpers.valedate import Valedate


def test_prefer_our_flags_american_spelling(concordat_vale: Valedate) -> None:
    """Vale should flag lone -or spellings that need -our."""
    text = "The odor lingered in the hallway."

    diags = concordat_vale.lint(text)

    assert len(diags) == 1, "expected a diagnostic for the American spelling"
    diag = diags[0]
    assert diag.check == "concordat.PreferOur", "unexpected rule triggered"
    assert diag.message.startswith("Use British '-our' spelling:"), (
        "diagnostic should direct writers to use -our spellings"
    )
    assert diag.severity == "error", "PreferOur should raise an error"
    assert diag.line == 1, "single-line match should report line 1"


def test_prefer_our_allows_british_spellings(concordat_vale: Valedate) -> None:
    """Correct -our spellings must not trigger diagnostics."""
    text = textwrap.dedent(
        """\
        The harbour's colour reflected off the armour.
        Local neighbours praised the flavourful savoury pies and their honourable hosts.
        """
    )

    diags = concordat_vale.lint(text)

    assert diags == [], "expected no diagnostics for canonical -our spellings"


def test_prefer_our_allows_latin_suffix_derivatives(
    concordat_vale: Valedate,
) -> None:
    """Latinate derivatives like elaborate or honorary should pass."""
    text = textwrap.dedent(
        """\
        Their elaborate collaboration transformed the laboratory's workflows.
        The most laborious phase still finished on time.
        Honorary collaborators described the humorous and glamorous motifs.
        They also logged the odorous and vigorous failures.
        """
    )

    diags = concordat_vale.lint(text)

    assert diags == [], "expected no diagnostics for Latin-stem derivatives"


def test_prefer_our_allows_scientific_color_terms(concordat_vale: Valedate) -> None:
    """Scientific color- forms such as colorimeter should be accepted."""
    text = (
        "Colorimeter data supported the colorimetry report and the coloration appendix."
    )

    diags = concordat_vale.lint(text)

    assert diags == [], (
        "color- scientific terms circulate internationally and should pass"
    )


def test_prefer_our_ignores_embedded_labor_stems(concordat_vale: Valedate) -> None:
    """Word-boundary handling should avoid flagging collaborate/elaborate."""
    text = "Teams collaborate to elaborate plans before any deodorising steps."

    diags = concordat_vale.lint(text)

    assert diags == [], "embedded 'labor' stems should not be treated as labour"


def test_prefer_our_reports_each_offence_in_files(
    concordat_vale: Valedate,
) -> None:
    """lint_path should emit every -or spelling found in a file."""
    doc_path = concordat_vale.root / "spellings.md"
    doc_path.write_text(
        textwrap.dedent(
            """\
            Color charts feel incomplete.
            The neighbor called earlier.
            Their armor rusted quickly.
            Favorite desserts rotate weekly.
            """
        ),
        encoding="utf-8",
    )

    results = concordat_vale.lint_path(doc_path)

    assert str(doc_path) in results, "expected lint_path to key diagnostics by file"
    alerts = results[str(doc_path)]
    assert len(alerts) == 4, "each American spelling should raise a diagnostic"
    assert {alert.line for alert in alerts} == {1, 2, 3, 4}, (
        "each offending line should be reported once"
    )
    assert {alert.check for alert in alerts} == {"concordat.PreferOur"}, (
        "unexpected rule triggered"
    )


def test_prefer_our_matches_case_insensitively(concordat_vale: Valedate) -> None:
    """Uppercase -or spellings should still be rewritten."""
    text = textwrap.dedent(
        """\
        COLOR charts stay pinned to the wall.
        HUMOR columns recap the day.
        """
    )

    diags = concordat_vale.lint(text)

    prefer_our_diags = [diag for diag in diags if diag.check == "concordat.PreferOur"]
    assert len(prefer_our_diags) == 2, (
        "expected PreferOur to flag both uppercase spellings"
    )
    assert {diag.line for diag in prefer_our_diags} == {1, 2}, (
        "each uppercase spelling should be reported on its own line"
    )
