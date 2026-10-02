"""Wiring checks for the workflow that runs this repository's test suite."""

from __future__ import annotations

import re
from pathlib import Path

WORKFLOW = Path(".github/workflows/tests.yml")


def _text() -> str:
    return WORKFLOW.read_text()


def test_the_suite_is_run_through_make_test() -> None:
    """CI must run the suite with the Makefile's own entry point.

    A step that only mentions pytest, or a different target, would let the
    workflow stay green while the suite the developers run goes unrun.
    """
    assert re.search(r"^\s+run: make test$", _text(), re.MULTILINE)


def test_vale_is_pinned_and_verified_by_checksum() -> None:
    """The Vale binary must be a fixed release whose digest is checked.

    The style tests exercise a real Vale, so an unpinned download would let an
    upstream release change what passes. The `sha256sum -c` step is what turns a
    mismatch into a failure, so it is asserted as a command, not as a name.
    """
    text = _text()

    assert re.search(r"VALE_VERSION: '\d+\.\d+\.\d+'", text)
    assert re.search(r"VALE_SHA256: '[0-9a-f]{64}'", text)
    assert "sha256sum -c -" in text
    assert 'echo "${VALE_SHA256}  ${archive}" | sha256sum -c -' in text


def test_vale_is_installed_before_the_tests_run() -> None:
    """The install step must precede `make test`, or the harness finds no Vale."""
    text = _text()

    assert text.index("sha256sum -c -") < text.index("run: make test")


def test_the_job_has_a_timeout_and_pinned_actions() -> None:
    """The job needs a ceiling, and every action must be pinned to a commit."""
    text = _text()

    assert re.search(r"^\s+timeout-minutes: \d+$", text, re.MULTILINE)
    for use in re.findall(r"uses: (\S+)", text):
        assert re.fullmatch(r"[\w./-]+@[0-9a-f]{40}", use), f"unpinned: {use}"
