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
    expected_styles_path: str
    expected_style_name: str
    expected_target_glob: str


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


@given("STILYAGI_ environment variables are set")
def set_stilyagi_env_vars(
    monkeypatch: pytest.MonkeyPatch, scenario_state: ScenarioState
) -> None:
    """Configure CLI overrides that rely on environment variables."""
    project_root = scenario_state["project_root"]
    concordat = project_root / "styles" / "concordat"
    custom_style = project_root / "styles" / "custom_concordat"
    if not custom_style.exists():
        shutil.copytree(concordat, custom_style)

    scenario_state["expected_styles_path"] = "custom_styles"
    scenario_state["expected_style_name"] = "custom_concordat"
    scenario_state["expected_target_glob"] = "*.rst"

    monkeypatch.setenv("STILYAGI_INI_STYLES_PATH", "custom_styles")
    monkeypatch.setenv("STILYAGI_STYLE", "custom_concordat")
    monkeypatch.setenv("STILYAGI_TARGET_GLOB", "*.rst")


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
    # NOTE: arguments are repository-controlled in tests.
    result = subprocess.run(  # noqa: S603
        command,
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    stdout_lines = [line for line in result.stdout.splitlines() if line.strip()]
    scenario_state["stdout"] = stdout_lines[-1] if stdout_lines else ""

    produced_archives = sorted((dist_dir).glob("*.zip"))
    assert produced_archives, (
        f"stilyagi zip did not create an archive in {dist_dir}:\n{result.stderr}"
    )
    scenario_state["archive_path"] = produced_archives[-1]


@then("a zip archive is emitted in its dist directory")
def archive_exists(scenario_state: ScenarioState) -> None:
    """Assert that the CLI produced a ZIP artefact in the expected folder."""
    archive_path = scenario_state["archive_path"]
    assert Path(archive_path).exists(), "Expected the zip archive to exist"


@then("the archive includes the concordat content and config")
def archive_has_content(scenario_state: ScenarioState) -> None:
    """Verify that the archive captured both rules and shared config assets."""
    archive_path = scenario_state["archive_path"]
    style_name = scenario_state.get("expected_style_name", "concordat")
    expected_rule = f"{style_name}/OxfordComma.yml"
    with ZipFile(archive_path) as archive:
        names = set(archive.namelist())
        assert any(name.endswith(expected_rule) for name in names), (
            f"Archive missing {expected_rule}"
        )
        assert any("/config/" in name for name in names), (
            "Archive missing shared config"
        )


@then("the archive contains a .vale.ini referencing the concordat style")
def archive_has_ini(scenario_state: ScenarioState) -> None:
    """Ensure the generated .vale.ini points at the concordat style list."""
    archive_path = scenario_state["archive_path"]
    expected_styles_path = scenario_state.get("expected_styles_path", "styles")
    expected_style = scenario_state.get("expected_style_name", "concordat")
    with ZipFile(archive_path) as archive:
        ini_body = archive.read(".vale.ini").decode("utf-8")
    assert f"StylesPath = {expected_styles_path}" in ini_body, (
        f"Generated ini should point StylesPath at {expected_styles_path}/"
    )
    assert f"BasedOnStyles = {expected_style}" in ini_body, (
        f"Generated ini should enable the {expected_style} style"
    )


@then("the archive .vale.ini uses the STILYAGI_ environment variable values")
def archive_ini_uses_env_overrides(scenario_state: ScenarioState) -> None:
    """Confirm CLI picks up STILYAGI_ overrides for .vale.ini content."""
    archive_path = scenario_state["archive_path"]
    expected_styles_path = scenario_state["expected_styles_path"]
    expected_style = scenario_state["expected_style_name"]
    expected_glob = scenario_state["expected_target_glob"]

    with ZipFile(archive_path) as archive:
        ini_body = archive.read(".vale.ini").decode("utf-8")

    assert f"StylesPath = {expected_styles_path}" in ini_body, (
        f"Expected StylesPath {expected_styles_path}, got {ini_body!r}"
    )
    assert f"BasedOnStyles = {expected_style}" in ini_body, (
        f"Expected BasedOnStyles {expected_style}, got {ini_body!r}"
    )
    assert f"[{expected_glob}]" in ini_body, (
        f"Expected target glob [{expected_glob}], got {ini_body!r}"
    )


@pytest.mark.parametrize(
    "case",
    [
        pytest.param("missing-project", id="missing-project"),
        pytest.param("overwrite", id="overwrite-without-force"),
    ],
)
def test_stilyagi_zip_cli_errors(tmp_path: Path, repo_root: Path, case: str) -> None:
    """Validate CLI error handling for invalid inputs and overwrite attempts."""
    if case == "missing-project":
        project_root = tmp_path / "missing"
        args = ["--project-root", str(project_root)]
        expected_error = "does not exist"
    elif case == "overwrite":
        project_root = tmp_path / "staging"
        project_root.mkdir()
        shutil.copytree(repo_root / "styles", project_root / "styles")
        dist_dir = project_root / "dist"
        dist_dir.mkdir()
        (dist_dir / "concordat-0.1.0.zip").write_bytes(b"placeholder")
        args = [
            "--project-root",
            str(project_root),
            "--output-dir",
            str(dist_dir),
        ]
        expected_error = "already exists"
    else:  # pragma: no cover - defensive fallback
        pytest.fail(f"Unknown case {case}")

    command = [
        sys.executable,
        "-m",
        "concordat_vale.stilyagi",
        "zip",
        *args,
    ]
    # NOTE: arguments come from controlled fixtures in tests.
    result = subprocess.run(  # noqa: S603
        command,
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0, "CLI should fail for the parametrised error scenario"
    assert expected_error in result.stderr, (
        f"CLI stderr should contain {expected_error!r}"
    )
