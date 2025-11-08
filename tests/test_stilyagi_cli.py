"""Integration-style tests that exercise the CLI entry point."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
STYLES_DIR = REPO_ROOT / "styles"


def _invoke_cli(
    *args: str,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run the CLI module with the provided arguments and environment."""
    full_env = os.environ.copy()
    if env:
        full_env.update(env)
    command = [
        sys.executable,
        "-m",
        "concordat_vale.stilyagi",
        "zip",
        *args,
    ]
    return subprocess.run(  # noqa: S603 - arguments are repository-controlled
        command,
        cwd=str(cwd or REPO_ROOT),
        text=True,
        capture_output=True,
    )


@pytest.fixture
def staged_project(tmp_path: Path) -> Path:
    """Copy the repository styles directory into a temporary staging tree."""
    project_root = tmp_path / "staging"
    shutil.copytree(STYLES_DIR, project_root / "styles")
    return project_root


def test_cli_errors_when_styles_directory_missing(tmp_path: Path) -> None:
    """Fail with a helpful message when the styles directory is absent."""
    result = _invoke_cli("--project-root", str(tmp_path))
    assert result.returncode != 0, (
        f"Expected non-zero exit when styles directory is missing: {result.stderr}"
    )
    assert "does not exist" in result.stderr, (
        "Missing-styles error message should mention 'does not exist'"
    )


def test_cli_refuses_to_overwrite_without_force(staged_project: Path) -> None:
    """Refuse to overwrite archives when --force is not provided."""
    base_args = [
        "--project-root",
        str(staged_project),
        "--archive-version",
        "7.7.7",
    ]
    first = _invoke_cli(*base_args)
    assert first.returncode == 0, (
        f"Initial packaging should succeed: {first.stderr or first.stdout}"
    )

    second = _invoke_cli(*base_args)
    assert second.returncode != 0, (
        "Second packaging should fail without --force: "
        f"{second.stderr or second.stdout}"
    )
    assert "already exists" in second.stderr, (
        f"Expected overwrite warning in stderr: {second.stderr}"
    )
