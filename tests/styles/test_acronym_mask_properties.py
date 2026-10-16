"""Check the real acronym rule against generated Markdown segment semantics.

The private segment records, builders, and oracle belong only to this module.
They describe intended visible tokens, definitions, and masked content without
reimplementing the rule's interval searches or parsing its generated Markdown.
"""

from __future__ import annotations

import dataclasses as dc
import enum
from pathlib import Path

from hypothesis import example, given, settings
from hypothesis import strategies as st
from valedate import ValeAction, Valedate, ValeDiagnostic


class _Effect(enum.Enum):
    """Describe a segment's intended effect on first-use diagnostics."""

    MASKED = enum.auto()
    VISIBLE = enum.auto()
    DEFINED = enum.auto()


@dc.dataclass(frozen=True)
class _Segment:
    """Keep rendered text with its independently declared token semantics."""

    text: str
    token: str
    column: int
    effect: _Effect


def _visible_segment(token: str, prefix: str) -> _Segment:
    """Place an unexpanded acronym after a known prose prefix."""
    return _Segment(prefix + token + "\n", token, len(prefix) + 1, _Effect.VISIBLE)


def _masked_segment(token: str, template: str) -> _Segment:
    """Render a known mask without exposing its token to the oracle."""
    return _Segment(template.format(token=token), token, 0, _Effect.MASKED)


def _definition_segment(token: str) -> _Segment:
    """Declare an expansion whose later visible uses need no warning."""
    return _Segment("space agency (" + token + ")\n", token, 0, _Effect.DEFINED)


def _expected_diagnostics(segments: list[_Segment]) -> list[ValeDiagnostic]:
    """Derive complete warnings from segment declarations and line offsets."""
    expected = []
    defined: set[str] = set()
    reported: set[str] = set()
    line = 1
    for segment in segments:
        token = segment.token
        if segment.effect is _Effect.DEFINED:
            defined.add(token)
        elif segment.effect is _Effect.VISIBLE and token not in defined | reported:
            expected.append(
                ValeDiagnostic(
                    check="concordat.AcronymsFirstUse",
                    message=(
                        "Expand uncommon acronyms on first use (e.g., 'Continuous "
                        f"Integration (CI)'). Found '{token}' with no prior expansion."
                    ),
                    severity="warning",
                    line=line,
                    span=(segment.column, segment.column + len(token) - 1),
                    link="House style: expand acronyms on first use.",
                    description="",
                    match=token,
                    action=ValeAction(name="", params=None),
                )
            )
            reported.add(token)
        line += segment.text.count("\n")
    return expected


_TOKENS = st.sampled_from(("NASA", "ESA", "JAXA"))
_MASKS = (
    "`{token}`\n",
    "[label](https://example.org/{token})\n",
    "~~~text\n{token}\n~~~\n",
    "[label](prefix`{token}`suffix)\n",
    "[label](`{token}`)\n",
    "`{token}` [label](https://example.org/{token})\n",
    "[plain] `{token}`\n",
)
_SEGMENTS = st.lists(
    st.one_of(
        st.builds(
            _visible_segment,
            token=_TOKENS,
            prefix=st.sampled_from(("", "Élan ", "[plain] ", "[plain] Élan ")),
        ),
        st.builds(_masked_segment, token=_TOKENS, template=st.sampled_from(_MASKS)),
        st.builds(_definition_segment, token=_TOKENS),
    ),
    min_size=1,
    max_size=12,
)


@settings(max_examples=64, deadline=None)
@example(
    segments=[
        _visible_segment("NASA", "[plain] Élan "),
        *[_masked_segment("ESA", template) for template in _MASKS],
        _visible_segment("ESA", ""),
        _definition_segment("JAXA"),
        _visible_segment("JAXA", ""),
        _visible_segment("NASA", ""),
    ]
)
@example(segments=[_masked_segment("NASA", "`{token}`\n")])
@given(segments=_SEGMENTS)
def test_generated_masks_preserve_first_visible_diagnostics(
    segments: list[_Segment],
) -> None:
    """Generated semantic segments retain all and only intended diagnostics."""
    styles = Path(__file__).resolve().parents[2] / "styles"
    ini = {
        "__root__": {"MinAlertLevel": "suggestion"},
        "[*.md]": {"BasedOnStyles": "concordat"},
    }
    text = "".join(segment.text for segment in segments)
    expected = _expected_diagnostics(segments)

    with Valedate(ini, styles=styles) as environment:
        actual = list(environment.lint(text))

    assert actual == expected, "native diagnostics must match the segment semantics"
