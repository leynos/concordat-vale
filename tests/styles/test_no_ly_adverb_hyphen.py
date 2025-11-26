"""Regression tests for vale rule authored to catch hyphenated -ly adverbs.

These tests cover the NoLyAdverbHyphen Concordat rule, which warns writers
when an adverb ending in ``-ly`` is incorrectly hyphenated before an adjective
(for example, ``highly-available``). The suite exercises both linting entry
points—direct strings and file-based runs—to prove that hyphenated adverbs are
flagged, documented exceptions and correctly spaced pairs are accepted, and
false positives such as nouns ending in ``-ly`` remain untouched. Execute
``make test`` (preferred) or ``pytest tests/styles/test_no_ly_adverb_hyphen.py``
to run the regression coverage locally.
"""

from __future__ import annotations

import textwrap
import typing as typ

if typ.TYPE_CHECKING:
    from valedate import Valedate


def test_no_ly_adverb_hyphen_flags_hyphenated_adverbs(
    concordat_vale: Valedate,
) -> None:
    """Ensure hyphenated -ly adverbs produce NoLyAdverbHyphen diagnostics.

    Parameters
    ----------
    concordat_vale : Valedate
        Vale sandbox configured with the Concordat styles.

    Returns
    -------
    None
        The assertions verify that Vale reports the expected diagnostic fields.
    """
    text = "Ensure the service remains highly-available during failover."

    diags = concordat_vale.lint(text)

    assert len(diags) == 1, "expected exactly one diagnostic per hyphenated adverb"
    diag = diags[0]
    assert diag.check == "concordat.NoLyAdverbHyphen", "unexpected rule triggered"
    assert diag.severity == "warning", "rule should warn to drop the hyphen"
    assert diag.line == 1, "issue should be reported on the only line"
    assert diag.match == "highly-available", (
        "diagnostic should highlight the hyphenated term"
    )
    assert diag.message.startswith("Don\u2019t hyphenate an -ly adverb + adjective"), (
        "unexpected diagnostic message"
    )


def test_no_ly_adverb_hyphen_allows_spaced_pairs(
    concordat_vale: Valedate,
) -> None:
    """Verify spaced adverb-adjective pairs pass the Vale rule.

    Parameters
    ----------
    concordat_vale : Valedate
        Vale sandbox configured with the Concordat styles.

    Returns
    -------
    None
        The assertions confirm that correctly spaced phrases raise no alerts.
    """
    text = "The cluster stays highly available and clearly documented."

    diags = concordat_vale.lint(text)

    assert diags == [], "expected no diagnostics without the hyphen"


def test_no_ly_adverb_hyphen_honors_documented_exceptions(
    concordat_vale: Valedate,
) -> None:
    """Ensure documented exceptions are not flagged by NoLyAdverbHyphen.

    Parameters
    ----------
    concordat_vale : Valedate
        Vale sandbox configured with the Concordat styles.

    Returns
    -------
    None
        The assertions verify that allowlisted prefixes bypass diagnostics.
    """
    text = "Launch the early-access beta to a family-friendly cohort."

    diags = concordat_vale.lint(text)

    assert diags == [], "expected exceptions to bypass the rule"


def test_no_ly_adverb_hyphen_reports_each_violation_in_files(
    concordat_vale: Valedate,
) -> None:
    """Confirm file-based linting reports every hyphenated adverb instance.

    Parameters
    ----------
    concordat_vale : Valedate
        Vale sandbox configured with the Concordat styles.

    Returns
    -------
    None
        The assertions ensure both diagnostics surface via ``lint_path``.
    """
    doc_path = concordat_vale.root / "availability.md"
    doc_path.write_text(
        textwrap.dedent(
            """\
            Maintain a closely-held secret key.

            Publish a nearly-complete overview before launch.
            """
        ),
        encoding="utf-8",
    )

    results = concordat_vale.lint_path(doc_path)

    assert str(doc_path) in results, "expected lint_path to return document diagnostics"
    alerts = results[str(doc_path)]
    assert len(alerts) == 2, "expected both hyphenated adverbs to be flagged"
    assert {alert.line for alert in alerts} == {1, 3}, "incorrect lines flagged"
    assert {alert.check for alert in alerts} == {"concordat.NoLyAdverbHyphen"}, (
        "unexpected rule triggered in file lint"
    )


def test_no_ly_adverb_hyphen_avoids_false_positive_on_non_adverbs(
    concordat_vale: Valedate,
) -> None:
    """Check that non-adverb '-ly' adjectives do not trigger false positives.

    Parameters
    ----------
    concordat_vale : Valedate
        Vale sandbox configured with the Concordat styles.

    Returns
    -------
    None
        The assertions confirm adjectives ending in '-ly' are ignored.
    """
    text = textwrap.dedent(
        """\
        The curly-haired developer debugged an ugly-looking prototype beside
        a lonely-planet guide.
        """
    )

    diags = concordat_vale.lint(text)

    assert diags == [], "expected no diagnostics for non-adverb '-ly' prefixes"


def test_no_ly_adverb_hyphen_handles_capitalized_and_punctuated_matches(
    concordat_vale: Valedate,
) -> None:
    """Validate capitalized or punctuated hyphenations still alert.

    Parameters
    ----------
    concordat_vale : Valedate
        Vale sandbox configured with the Concordat styles.

    Returns
    -------
    None
        The assertions ensure each capitalized, punctuated match is reported.
    """
    text = "Deploy a Highly-Available, Publicly-Accessible endpoint."

    diags = concordat_vale.lint(text)

    assert len(diags) == 2, "expected each hyphenated adverb to be reported"
    assert {diag.match for diag in diags} == {
        "Highly-Available",
        "Publicly-Accessible",
    }, "unexpected matches were flagged"
