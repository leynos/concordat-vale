"""Behavioural tests for stilyagi's update-tengo-map command."""

from __future__ import annotations

import subprocess
import sys
import typing as typ
from pathlib import Path

import pytest
from pytest_bdd import given, scenarios, then, when

FEATURE_PATH = (
    Path(__file__).resolve().parents[2]
    / "features"
    / "stilyagi_update_tengo_map.feature"
)


class ScenarioState(typ.TypedDict, total=False):
    """Mutable cross-step storage used by pytest-bdd scenarios."""

    project_root: Path
    tengo_path: Path
    source_path: Path
    stdout: str


scenarios(str(FEATURE_PATH))


@pytest.fixture
def repo_root() -> Path:
    """Return the repository root so the CLI can run via python -m."""
    return Path(__file__).resolve().parents[2]


@pytest.fixture
def scenario_state() -> ScenarioState:
    """Provide mutable per-scenario storage across step functions."""
    return {}


@given("a staging Tengo script with allow and exceptions maps")
def staging_tengo_script(tmp_path: Path, scenario_state: ScenarioState) -> Path:
    """Create a temporary Tengo script containing two maps."""
    project_root = tmp_path / "staging"
    project_root.mkdir()
    tengo_path = project_root / "script.tengo"
    tengo_path.write_text(
        ('allow := {\n  "EXISTING": true,\n}\n\nexceptions := {\n  "value": 10,\n}\n'),
        encoding="utf-8",
    )
    scenario_state["project_root"] = project_root
    scenario_state["tengo_path"] = tengo_path
    return project_root


@given("a source list containing boolean entries")
def boolean_source_list(scenario_state: ScenarioState) -> Path:
    """Write a source file listing boolean map keys."""
    project_root = scenario_state["project_root"]
    source_path = project_root / "entries.txt"
    source_path.write_text("ALPHA\nBETA   # trailing\n", encoding="utf-8")
    scenario_state["source_path"] = source_path
    return source_path


@given("a source list containing numeric entries")
def numeric_source_list(scenario_state: ScenarioState) -> Path:
    """Write a source file listing numeric map entries."""
    project_root = scenario_state["project_root"]
    source_path = project_root / "entries.txt"
    source_path.write_text("value=10\nfresh=3\n", encoding="utf-8")
    scenario_state["source_path"] = source_path
    return source_path


@when("I run stilyagi update-tengo-map for the allow map")
def run_update_tengo_map_allow(
    repo_root: Path, scenario_state: ScenarioState
) -> subprocess.CompletedProcess[str]:
    """Invoke the CLI with the default allow map."""
    return _run_update_tengo_map(
        repo_root=repo_root,
        scenario_state=scenario_state,
        dest_argument=str(scenario_state["tengo_path"]),
        extra_args=[],
    )


@when("I run stilyagi update-tengo-map for the exceptions map with numeric values")
def run_update_tengo_map_named_map(
    repo_root: Path, scenario_state: ScenarioState
) -> subprocess.CompletedProcess[str]:
    """Invoke the CLI for the exceptions map and numeric parsing."""
    dest_argument = f"{scenario_state['tengo_path']}::exceptions"
    return _run_update_tengo_map(
        repo_root=repo_root,
        scenario_state=scenario_state,
        dest_argument=dest_argument,
        extra_args=["--type", "=n"],
    )


def _run_update_tengo_map(
    *,
    repo_root: Path,
    scenario_state: ScenarioState,
    dest_argument: str,
    extra_args: list[str],
) -> subprocess.CompletedProcess[str]:
    project_root = scenario_state["project_root"]
    source_path = scenario_state["source_path"]
    command = [
        sys.executable,
        "-m",
        "concordat_vale.stilyagi",
        "update-tengo-map",
        "--project-root",
        str(project_root),
        "--source",
        str(source_path),
        "--dest",
        dest_argument,
        *extra_args,
    ]
    result = subprocess.run(  # noqa: S603
        command,
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    stdout_lines = [line for line in result.stdout.splitlines() if line.strip()]
    scenario_state["stdout"] = stdout_lines[-1] if stdout_lines else ""
    return result


@then("the allow map contains the boolean entries")
def allow_map_contains_entries(scenario_state: ScenarioState) -> None:
    """Verify that the allow map was updated."""
    contents = scenario_state["tengo_path"].read_text(encoding="utf-8")
    assert '"ALPHA": true,' in contents
    assert '"BETA": true,' in contents


@then("the exceptions map contains the numeric entries")
def exceptions_map_contains_entries(scenario_state: ScenarioState) -> None:
    """Verify that the exceptions map was updated with numeric values."""
    contents = scenario_state["tengo_path"].read_text(encoding="utf-8")
    assert '"value": 10,' in contents
    assert '"fresh": 3,' in contents


@then('the command reports "2 entries provided, 2 updated"')
def command_reports_two_updates(scenario_state: ScenarioState) -> None:
    """Assert the CLI reported the expected update count."""
    assert scenario_state["stdout"] == "2 entries provided, 2 updated"


@then('the command reports "2 entries provided, 1 updated"')
def command_reports_single_update(scenario_state: ScenarioState) -> None:
    """Assert the CLI reported a single update."""
    assert scenario_state["stdout"] == "2 entries provided, 1 updated"
