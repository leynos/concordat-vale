"""Behavioural tests for the stilyagi install subcommand."""

from __future__ import annotations

import http.server
import json
import subprocess
import sys
import threading
import typing as typ
from pathlib import Path

import pytest
from pytest_bdd import given, scenarios, then, when

FEATURE_PATH = (
    Path(__file__).resolve().parents[2] / "features" / "stilyagi_install.feature"
)


class InstallState(typ.TypedDict, total=False):
    """Mutable cross-step storage for pytest-bdd scenarios."""

    workspace: Path
    config_path: Path
    api_base: str


scenarios(str(FEATURE_PATH))


@pytest.fixture
def repo_root() -> Path:
    """Return the repository root for executing the CLI via python -m."""
    return Path(__file__).resolve().parents[2]


@pytest.fixture
def scenario_state() -> InstallState:
    """Provide per-scenario state shared between steps."""
    return {}


@pytest.fixture
def fake_release_api(tmp_path_factory: pytest.TempPathFactory) -> typ.Iterator[str]:
    """Expose a minimal GitHub API stub that serves a latest-release payload."""
    payload = {
        "tag_name": "v9.9.9",
        "assets": [
            {
                "name": "concordat-9.9.9.zip",
                "browser_download_url": "http://example.invalid/releases/download/v9.9.9/concordat-9.9.9.zip",
            }
        ],
    }

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path == "/repos/leynos/concordat-vale/releases/latest":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(payload).encode("utf-8"))
                return

            self.send_response(404)
            self.end_headers()

        def log_message(self, _fmt: str, *_args: object) -> None:
            # Silence default logging during tests.
            return

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join()


@given("a working directory with a Vale config file")
def working_directory(tmp_path: Path, scenario_state: InstallState) -> None:
    """Create a temporary workspace with an existing .vale.ini."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    config_path = workspace / ".vale.ini"
    config_path.write_text(
        "StylesPath = .vale/styles\nMinAlertLevel = suggestion\n", encoding="utf-8"
    )
    scenario_state["workspace"] = workspace
    scenario_state["config_path"] = config_path


@given("a fake GitHub API reporting version 9.9.9")
def stub_api(fake_release_api: str, scenario_state: InstallState) -> None:
    """Record the base URL the CLI should target for release metadata."""
    scenario_state["api_base"] = fake_release_api


@when("I run stilyagi install for leynos/concordat-vale against that API")
def run_install(repo_root: Path, scenario_state: InstallState) -> None:
    """Execute the install subcommand against the stubbed API."""
    command = [
        sys.executable,
        "-m",
        "concordat_vale.stilyagi",
        "install",
        "leynos/concordat-vale",
        "--api-base",
        scenario_state["api_base"],
        "--config-path",
        str(scenario_state["config_path"]),
    ]

    # Arguments are repository-controlled inside the test suite.
    result = subprocess.run(  # noqa: S603
        command,
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, (
        "stilyagi install should succeed:\n"
        f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )


@then("the Vale config lists the Concordat package URL and settings")
def config_contains_expected_lines(scenario_state: InstallState) -> None:
    """Validate the config file now matches the Concordat defaults."""
    config_path = scenario_state["config_path"]
    contents = config_path.read_text(encoding="utf-8")

    assert (
        "Packages = http://example.invalid/releases/download/v9.9.9/concordat-9.9.9.zip"
        in contents
    )
    assert "MinAlertLevel = warning" in contents
    assert "Vocab = concordat" in contents
    assert "[docs/**/*.{md,markdown,mdx}]" in contents
    assert "BlockIgnores = (?m)^\\[\\^\\d+\\]:" in contents
    assert "concordat.Pronouns = NO" in contents
