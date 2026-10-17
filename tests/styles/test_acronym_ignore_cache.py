"""Native ignored-range regressions for the acronym rule's miss-gap contract.

The bounded dense cases challenge repeated lookups between ignored ranges.
Expected public diagnostic records keep rule reachability and metadata binding;
successful execution alone cannot establish that masking remains correct.
"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

import pytest
from valedate import ValeAction, Valedate, ValeDiagnostic
from valedate.harness import ValeExecutionError

from concordat_vale.acronym_allowlist import update_allow_map

_STYLES = Path(__file__).resolve().parents[2] / "styles"
_VALE_INI = {
    "__root__": {"MinAlertLevel": "suggestion"},
    "[*.md]": {"BasedOnStyles": "concordat"},
}
_CANARY = (
    "NASA launches.\n"
    "[plain] `ESA` [label](https://example.org/JAXA)\n"
    "~~~text\n"
    "JAXA\n"
    "~~~\n"
    "`ESA` NASA.\n"
)


def _warning(token: str, line: int, span: tuple[int, int]) -> ValeDiagnostic:
    """Describe one complete public first-use diagnostic for this module."""
    return ValeDiagnostic(
        check="concordat.AcronymsFirstUse",
        message=(
            "Expand uncommon acronyms on first use (e.g., 'Continuous "
            f"Integration (CI)'). Found '{token}' with no prior expansion."
        ),
        severity="warning",
        line=line,
        span=span,
        link="House style: expand acronyms on first use.",
        description="",
        match=token,
        action=ValeAction(name="", params=None),
    )


@pytest.mark.parametrize(
    ("inline_count", "gap_size"),
    [
        pytest.param(256, 128 * 1024, id="256-ranges-128k-gap"),
        pytest.param(1024, 256 * 1024, id="1024-ranges-256k-gap"),
    ],
)
def test_dense_inline_ranges_leave_prose_gaps_reachable(
    concordat_vale: Valedate, inline_count: int, gap_size: int
) -> None:
    """Many inline masks must not prevent a later exact first-use warning."""
    prefix = "`ESA` " * inline_count
    gap = ("word " * (gap_size // 5 + 1))[:gap_size]
    text = prefix + gap + " NASA."
    start = len(prefix) + len(gap) + 2

    actual = list(concordat_vale.lint(text))

    assert actual == [_warning("NASA", 1, (start, start + 3))], (
        "the bounded dense input must finish with only the outside NASA warning"
    )


def test_cache_preserves_exact_canary_diagnostics(concordat_vale: Valedate) -> None:
    """Lookahead rewinds and mixed masks must retain the native canary record."""
    actual = list(concordat_vale.lint(_CANARY))

    assert actual == [_warning("NASA", 1, (1, 4))], (
        "ESA and JAXA must stay masked and repeated NASA must stay silent"
    )


def test_real_guide_retains_first_use_diagnostics(concordat_vale: Valedate) -> None:
    """The original budget failure must finish with early and late warnings."""
    fixture = (
        Path(__file__).resolve().parents[1] / "fixtures" / "acronym-real-guide.txt"
    )
    contents = fixture.read_bytes()
    assert hashlib.sha256(contents).hexdigest() == (
        "151a241e50bb871e9310eeb8c4b29f666a66b3475f511c4628ac3d06f5ae1242"
    ), "the real-guide regression must retain the measured original bytes"

    try:
        actual = list(concordat_vale.lint(contents.decode("utf-8")))
    except ValeExecutionError as error:
        error.add_note(error.stderr)
        raise

    assert _warning("XDG", 210, (21, 23)) in actual, (
        "the real guide must retain the early XDG first-use diagnostic"
    )
    assert _warning("ADR", 2374, (4, 6)) in actual, (
        "the real guide must retain the later ADR first-use diagnostic"
    )


@pytest.mark.parametrize(
    "text",
    [
        pytest.param("NASA `ESA` JAXA.", id="later-inline-range"),
        pytest.param(
            "NASA [label](https://example.org/ESA) JAXA.",
            id="later-link-destination-range",
        ),
    ],
)
def test_appended_masks_preserve_outside_acronyms(
    concordat_vale: Valedate, text: str
) -> None:
    """A newly appended mask must invalidate a miss covering the same bytes."""
    last_start = text.index("JAXA") + 1
    expected = [
        _warning("NASA", 1, (1, 4)),
        _warning("JAXA", 1, (last_start, last_start + 3)),
    ]

    actual = list(concordat_vale.lint(text))

    assert actual == expected, "only acronyms outside the appended mask may warn"


@pytest.mark.parametrize(
    "text",
    [
        pytest.param("`ESA` NASA.", id="mask-at-document-start"),
        pytest.param("NASA `ESA`", id="mask-at-document-end"),
        pytest.param("[plain] `ESA` NASA.", id="unlinked-lookahead-rewind"),
        pytest.param("[label](prefix`ESA`suffix) NASA.", id="overlapping-masks"),
        pytest.param("[label](`ESA`) NASA.", id="equal-start-masks"),
        pytest.param("Élan `ESA` NASA.", id="multibyte-prefix"),
    ],
)
def test_gap_boundaries_and_overlaps_preserve_full_diagnostics(
    concordat_vale: Valedate, text: str
) -> None:
    """Public masking layouts retain the outside warning's exact character span."""
    start = text.index("NASA") + 1

    actual = list(concordat_vale.lint(text))

    assert actual == [_warning("NASA", 1, (start, start + 3))], (
        "cache boundaries and overlapping masks must preserve complete diagnostics"
    )


def test_project_exceptions_change_only_the_copied_style(tmp_path: Path) -> None:
    """Project exceptions remain effective without altering the canonical map."""
    source = _STYLES / "config" / "scripts" / "AcronymsFirstUse.tengo"
    original = source.read_bytes()
    copied_styles = tmp_path / "styles"
    shutil.copytree(_STYLES, copied_styles)
    target = copied_styles / "config" / "scripts" / "AcronymsFirstUse.tengo"
    result = update_allow_map(target, ("ESA",))

    with Valedate(_VALE_INI, styles=copied_styles) as environment:
        actual = list(environment.lint("ESA NASA."))

    assert result.managed_entries == ("ESA",), "only the requested exception is added"
    assert actual == [_warning("NASA", 1, (5, 8))], (
        "the project exception must silence ESA without hiding NASA"
    )
    assert source.read_bytes() == original, "the canonical style must stay untouched"
