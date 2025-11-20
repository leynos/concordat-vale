"""Behavioural tests for installing Concordat into another repository."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from pytest_bdd import given, scenarios, then, when

FEATURE_PATH = (
    Path(__file__).resolve().parents[2] / "features" / "stilyagi_install.feature"
)


scenarios(str(FEATURE_PATH))


@pytest.fixture
def repo_root() -> Path:
    """Return the repository root for invoking the CLI via python -m."""
    return Path(__file__).resolve().parents[2]


@pytest.fixture
def external_repo(tmp_path: Path) -> Path:
    """Create a skeleton consumer repository without Vale wiring."""
    root = tmp_path / "consumer"
    root.mkdir()
    (root / ".vale.ini").write_text("StylesPath = styles\n", encoding="utf-8")
    (root / "Makefile").write_text(".PHONY: test\n\n", encoding="utf-8")
    return root


@given("an external repository without Vale wiring")
def given_external_repo(external_repo: Path) -> Path:
    """Expose the consumer repository to subsequent steps."""
    return external_repo


@when("I run stilyagi install with an explicit version")
def run_install(repo_root: Path, external_repo: Path) -> None:
    """Invoke the install sub-command with overrides to avoid network calls."""
    command = [
        sys.executable,
        "-m",
        "concordat_vale.stilyagi",
        "install",
        "leynos/concordat-vale",
        "--project-root",
        str(external_repo),
        "--release-version",
        "9.9.9-test",
        "--tag",
        "v9.9.9-test",
    ]

    result = subprocess.run(  # noqa: S603 - arguments are repository-controlled
        command,
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.returncode == 0, result.stderr


@then("the external repository has a configured .vale.ini")
def verify_vale_ini(external_repo: Path) -> None:
    """Assert that required sections and entries were written."""
    ini_body = (external_repo / ".vale.ini").read_text(encoding="utf-8")
    expected_url = (
        "https://github.com/leynos/concordat-vale/releases/download/"
        "v9.9.9-test/concordat-9.9.9-test.zip"
    )
    assert f"Packages = {expected_url}" in ini_body
    assert "MinAlertLevel = warning" in ini_body
    assert "Vocab = concordat" in ini_body
    assert "[docs/**/*.{md,markdown,mdx}]" in ini_body
    assert "BlockIgnores = (?m)^\\[\\^\\d+\\]:" in ini_body
    assert "concordat.Pronouns = NO" in ini_body


@then("the Makefile exposes a vale target")
def verify_makefile(external_repo: Path) -> None:
    """Check the Makefile wiring that orchestrates vale."""
    makefile = (external_repo / "Makefile").read_text(encoding="utf-8")
    assert ".PHONY: test vale" in makefile or ".PHONY: vale test" in makefile
    assert "vale: $(VALE) $(ACRONYM_SCRIPT) ## Check prose" in makefile
    assert "\t$(VALE) sync" in makefile
    assert "\t$(VALE) --no-global ." in makefile
