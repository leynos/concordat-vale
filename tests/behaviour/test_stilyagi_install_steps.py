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


@pytest.fixture
def scenario_state() -> dict[str, object]:
    """Provide mutable per-scenario storage across steps."""
    return {}


@given("an external repository without Vale wiring")
def given_external_repo(external_repo: Path) -> Path:
    """Expose the consumer repository to subsequent steps."""
    return external_repo


@when("I run stilyagi install with an explicit version")
def run_install(
    repo_root: Path, external_repo: Path, scenario_state: dict[str, object]
) -> None:
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
    scenario_state["result"] = result
    assert result.returncode == 0, result.stderr


@when("I run stilyagi install with an auto-discovered version")
def run_install_auto(
    repo_root: Path,
    external_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    scenario_state: dict[str, object],
) -> None:
    """Invoke install without explicit version, relying on release discovery."""
    import concordat_vale.stilyagi as stilyagi_module
    import concordat_vale.stilyagi_install as install_module

    def fake_fetch_latest_release(repo: str) -> dict[str, object]:
        return {
            "tag_name": "v9.9.9-auto",
            "assets": [
                {"name": "concordat-9.9.9-auto.zip"},
            ],
        }

    monkeypatch.setattr(
        install_module, "_fetch_latest_release", fake_fetch_latest_release, raising=True
    )

    owner, repo_name, style_name = stilyagi_module._parse_repo_reference(  # type: ignore[attr-defined]
        "leynos/concordat-vale"
    )
    _, ini_path, makefile_path = install_module._resolve_install_paths(  # type: ignore[attr-defined]
        cwd=repo_root,
        project_root=external_repo,
        vale_ini=Path(".vale.ini"),
        makefile=Path("Makefile"),
    )
    config = install_module.InstallConfig(  # type: ignore[attr-defined]
        owner=owner,
        repo_name=repo_name,
        style_name=style_name,
        ini_path=ini_path,
        makefile_path=makefile_path,
    )
    install_module._perform_install(config=config)  # type: ignore[attr-defined]
    scenario_state["expected_version"] = "9.9.9-auto"


@when("I run stilyagi install with a failing release lookup")
def run_install_failure(
    repo_root: Path,
    external_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    scenario_state: dict[str, object],
) -> None:
    """Invoke install where release lookup fails to ensure errors surface."""
    import concordat_vale.stilyagi as stilyagi_module
    import concordat_vale.stilyagi_install as install_module

    def fake_fetch_latest_release(repo: str) -> dict[str, object]:
        raise RuntimeError("simulated release lookup failure")  # noqa: TRY003

    monkeypatch.setattr(
        install_module, "_fetch_latest_release", fake_fetch_latest_release, raising=True
    )

    owner, repo_name, style_name = stilyagi_module._parse_repo_reference(  # type: ignore[attr-defined]
        "leynos/concordat-vale"
    )
    _, ini_path, makefile_path = install_module._resolve_install_paths(  # type: ignore[attr-defined]
        cwd=repo_root,
        project_root=external_repo,
        vale_ini=Path(".vale.ini"),
        makefile=Path("Makefile"),
    )
    config = install_module.InstallConfig(  # type: ignore[attr-defined]
        owner=owner,
        repo_name=repo_name,
        style_name=style_name,
        ini_path=ini_path,
        makefile_path=makefile_path,
    )

    try:
        install_module._perform_install(config=config)  # type: ignore[attr-defined]
    except Exception as exc:  # noqa: BLE001
        scenario_state["error"] = exc
    else:
        scenario_state["error"] = None


@then("the external repository has a configured .vale.ini")
def verify_vale_ini(external_repo: Path, scenario_state: dict[str, object]) -> None:
    """Assert that required sections and entries were written."""
    ini_body = (external_repo / ".vale.ini").read_text(encoding="utf-8")
    version = scenario_state.get("expected_version", "9.9.9-test")
    expected_url = (
        "https://github.com/leynos/concordat-vale/releases/download/"
        f"v{version}/concordat-{version}.zip"
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


@then("the install command fails with a release error")
def verify_failure(scenario_state: dict[str, object]) -> None:
    """Assert the CLI surfaces release lookup failures."""
    error = scenario_state.get("error")
    assert error is not None
    assert "release" in str(error).lower()
