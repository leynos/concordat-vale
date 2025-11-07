"""Behavioural tests for assembling Vale ZIPs via the stilyagi CLI."""

from __future__ import annotations

import shutil
import subprocess
import sys
import typing as typ
from pathlib import Path
from zipfile import ZipFile

import pytest
from pytest_bdd import given, scenarios, then, when

FEATURE_PATH = Path(__file__).resolve().parents[2] / "features" / "stilyagi_zip.feature"


class ScenarioState(typ.TypedDict, total=False):
    """Mutable cross-step storage used by pytest-bdd scenarios."""

    project_root: Path
    stdout: str
    archive_path: Path


scenarios(str(FEATURE_PATH))


@pytest.fixture
def repo_root() -> Path:
    """Return the repository root so the CLI can run via python -m."""
    return Path(__file__).resolve().parents[2]


@pytest.fixture
def scenario_state() -> ScenarioState:
    """Provide mutable per-scenario storage across step functions."""
    return {}


@given("a clean staging project containing the styles tree")
def staging_project(
    tmp_path: Path, repo_root: Path, scenario_state: ScenarioState
) -> Path:
    """Copy the repository styles directory into a temporary staging area."""
    staging = tmp_path / "staging"
    staging.mkdir()
    shutil.copytree(repo_root / "styles", staging / "styles")
    scenario_state["project_root"] = staging
    return staging


@when("I run stilyagi zip for that staging project")
def run_stilyagi_zip(repo_root: Path, scenario_state: ScenarioState) -> None:
    """Invoke the CLI with an explicit version and capture its output."""
    project_root = scenario_state["project_root"]
    dist_dir = project_root / "dist"
    command = [
        sys.executable,
        "-m",
        "concordat_vale.stilyagi",
        "zip",
        "--project-root",
        str(project_root),
        "--output-dir",
        str(dist_dir),
        "--archive-version",
        "9.9.9-test",
        "--force",
    ]
    result = subprocess.run(  # noqa: S603 - arguments are repository-controlled
        command,
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    scenario_state["stdout"] = result.stdout.strip()
    scenario_state["archive_path"] = dist_dir / "concordat-9.9.9-test.zip"


@then("a zip archive is emitted in its dist directory")
def archive_exists(scenario_state: ScenarioState) -> None:
    """Assert that the CLI produced a ZIP artefact in the expected folder."""
    archive_path = scenario_state["archive_path"]
    assert Path(archive_path).exists()


@then("the archive includes the concordat content and config")
def archive_has_content(scenario_state: ScenarioState) -> None:
    """Verify that the archive captured both rules and shared config assets."""
    archive_path = scenario_state["archive_path"]
    with ZipFile(archive_path) as archive:
        names = set(archive.namelist())
        assert "styles/concordat/OxfordComma.yml" in names
        assert any(name.startswith("styles/config/") for name in names)


@then("the archive contains a .vale.ini referencing the concordat style")
def archive_has_ini(scenario_state: ScenarioState) -> None:
    """Ensure the generated .vale.ini points at the concordat style list."""
    archive_path = scenario_state["archive_path"]
    with ZipFile(archive_path) as archive:
        ini_body = archive.read(".vale.ini").decode("utf-8")
    assert "StylesPath = styles" in ini_body
    assert "BasedOnStyles = concordat" in ini_body
