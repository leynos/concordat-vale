"""Lightweight wiring checks for the release workflow."""

from __future__ import annotations

from pathlib import Path


def test_release_workflow_uses_pinned_stilyagi_source() -> None:
    """Packaging step should use a pinned stilyagi source via uvx."""
    workflow = Path(".github/workflows/release.yml").read_text()

    assert "STILYAGI_SOURCE" in workflow
    assert "stilyagi.git@" in workflow, "stilyagi source should be pinned"
    assert 'uvx --from "${STILYAGI_SOURCE}" stilyagi zip' in workflow
