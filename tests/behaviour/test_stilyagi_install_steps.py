"""Behavioural tests for installing Concordat into another repository."""

from __future__ import annotations

import dataclasses as dc
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse
from zipfile import ZipFile

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
        env={**os.environ, "STILYAGI_SKIP_MANIFEST_DOWNLOAD": "1"},
        check=True,
    )
    scenario_state["result"] = result
    assert result.returncode == 0, result.stderr


@dc.dataclass
class _TestPaths:
    """Encapsulates test directory paths for installation testing."""

    repo_root: Path
    external_repo: Path
    tmp_path: Path


def _run_install_with_mocked_release(
    *,
    paths: _TestPaths,
    monkeypatch: pytest.MonkeyPatch,
    fake_fetch_fn: object,
) -> dict[str, object]:
    """Run install with a mocked release fetch function."""
    import concordat_vale.stilyagi as stilyagi_module
    import concordat_vale.stilyagi_install as install_module

    monkeypatch.setenv("STILYAGI_SKIP_MANIFEST_DOWNLOAD", "1")
    monkeypatch.setattr(
        install_module, "_fetch_latest_release", fake_fetch_fn, raising=True
    )

    owner, repo_name, style_name = stilyagi_module._parse_repo_reference(  # type: ignore[attr-defined]
        "leynos/concordat-vale"
    )
    _, ini_path, makefile_path = install_module._resolve_install_paths(  # type: ignore[attr-defined]
        cwd=paths.repo_root,
        project_root=paths.external_repo,
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
    except Exception as exc:  # noqa: BLE001 - behavioural test captures any error to record scenario state
        return {"error": exc}
    return {"error": None}


@pytest.fixture
def test_paths(repo_root: Path, external_repo: Path, tmp_path: Path) -> _TestPaths:
    """Bundle shared paths for install behavioural scenarios."""
    return _TestPaths(
        repo_root=repo_root, external_repo=external_repo, tmp_path=tmp_path
    )


def _build_manifest_archive(path: Path, *, manifest_body: str) -> Path:
    """Create a minimal archive containing the supplied stilyagi.toml."""
    archive_path = path / "concordat-configured.zip"
    with ZipFile(archive_path, "w") as archive:
        archive.writestr("concordat-0.0.1/.vale.ini", "StylesPath = styles\n")
        archive.writestr("concordat-0.0.1/stilyagi.toml", manifest_body)

    return archive_path


@when("I run stilyagi install with an auto-discovered version")
def run_install_auto(
    test_paths: _TestPaths,
    monkeypatch: pytest.MonkeyPatch,
    scenario_state: dict[str, object],
) -> None:
    """Invoke install without explicit version, relying on release discovery."""

    def fake_fetch_latest_release(_repo: str) -> dict[str, object]:
        return {
            "tag_name": "v9.9.9-auto",
            "assets": [
                {"name": "concordat-9.9.9-auto.zip"},
            ],
        }

    _run_install_with_mocked_release(
        paths=test_paths,
        monkeypatch=monkeypatch,
        fake_fetch_fn=fake_fetch_latest_release,
    )
    scenario_state["expected_version"] = "9.9.9-auto"


@when("I run stilyagi install with a failing release lookup")
def run_install_failure(
    test_paths: _TestPaths,
    monkeypatch: pytest.MonkeyPatch,
    scenario_state: dict[str, object],
) -> None:
    """Invoke install where release lookup fails to ensure errors surface."""

    def fake_fetch_latest_release(_repo: str) -> dict[str, object]:
        raise RuntimeError("simulated release lookup failure")  # noqa: TRY003

    result = _run_install_with_mocked_release(
        paths=test_paths,
        monkeypatch=monkeypatch,
        fake_fetch_fn=fake_fetch_latest_release,
    )
    scenario_state["error"] = result.get("error")


@when("I run stilyagi install with a packaged configuration")
def run_install_with_manifest(
    test_paths: _TestPaths,
    monkeypatch: pytest.MonkeyPatch,
    scenario_state: dict[str, object],
) -> None:
    """Invoke install while supplying a stilyagi.toml from the archive."""
    manifest_body = """[install]
style_name = "concordat"
vocab = "manifest-vocab"
min_alert_level = "error"

[[install.post_sync_steps]]
action = "update-tengo-map"
type = "true"
source = ".config/common-acronyms"
dest = ".vale/styles/config/scripts/AcronymsFirstUse.tengo"
"""

    archive_path = _build_manifest_archive(
        test_paths.tmp_path, manifest_body=manifest_body
    )
    packages_url = archive_path.as_uri()

    import concordat_vale.stilyagi_install as install_module

    monkeypatch.setattr(
        install_module,
        "_resolve_release",
        lambda **_kwargs: ("0.0.1-config", "v0.0.1-config", packages_url),
        raising=True,
    )

    def _read_local_archive(url: str) -> bytes:
        parsed = urlparse(url)
        path = Path(parsed.path) if parsed.scheme == "file" else Path(url)
        return path.read_bytes()

    monkeypatch.setattr(
        install_module, "_download_packages_archive", _read_local_archive, raising=True
    )

    owner, repo_name, style_name = install_module._parse_repo_reference(  # type: ignore[attr-defined]
        "leynos/concordat-vale"
    )
    _, ini_path, makefile_path = install_module._resolve_install_paths(  # type: ignore[attr-defined]
        cwd=test_paths.repo_root,
        project_root=test_paths.external_repo,
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

    scenario_state["expected_version"] = "0.0.1-config"
    scenario_state["expected_packages_url"] = packages_url
    scenario_state["expected_vocab"] = "manifest-vocab"
    scenario_state["expected_min_alert_level"] = "error"
    scenario_state["expected_post_sync_steps"] = [
        (
            "uv run stilyagi update-tengo-map --source .config/common-acronyms "
            "--dest .vale/styles/config/scripts/AcronymsFirstUse.tengo --type true"
        )
    ]


@then("the external repository has a configured .vale.ini")
def verify_vale_ini(external_repo: Path, scenario_state: dict[str, object]) -> None:
    """Assert that required sections and entries were written."""
    ini_body = (external_repo / ".vale.ini").read_text(encoding="utf-8")
    version = scenario_state.get("expected_version", "9.9.9-test")
    expected_url = scenario_state.get(
        "expected_packages_url",
        (
            "https://github.com/leynos/concordat-vale/releases/download/"
            f"v{version}/concordat-{version}.zip"
        ),
    )
    expected_alert = scenario_state.get("expected_min_alert_level", "warning")
    expected_vocab = scenario_state.get("expected_vocab", "concordat")

    assert f"Packages = {expected_url}" in ini_body, "Packages URL should be present"
    assert f"MinAlertLevel = {expected_alert}" in ini_body, (
        "MinAlertLevel should reflect configuration"
    )
    assert f"Vocab = {expected_vocab}" in ini_body, "Vocab should match style"
    assert "[docs/**/*.{md,markdown,mdx}]" in ini_body, "Docs section should exist"
    assert "BlockIgnores = (?m)^\\[\\^\\d+\\]:" in ini_body, (
        "Footnote ignore pattern should be present"
    )
    assert "concordat.Pronouns = NO" in ini_body, "Pronouns override should be present"


@then("the Makefile exposes a vale target")
def verify_makefile(external_repo: Path) -> None:
    """Check the Makefile wiring that orchestrates vale."""
    makefile = (external_repo / "Makefile").read_text(encoding="utf-8")
    assert ".PHONY: test vale" in makefile or ".PHONY: vale test" in makefile, (
        ".PHONY line should include vale"
    )
    assert "vale: $(VALE) ## Check prose" in makefile, "vale target should be present"
    assert "\t$(VALE) sync" in makefile, "vale target should sync first"
    assert "\t$(VALE) --no-global ." in makefile, "vale target should lint workspace"


@then("the Makefile exposes manifest-defined post-sync steps")
def verify_post_sync_steps(
    external_repo: Path, scenario_state: dict[str, object]
) -> None:
    """Ensure manifest-defined shell snippets are included in the vale target."""
    raw_steps = scenario_state.get("expected_post_sync_steps")
    assert raw_steps, "expected_post_sync_steps must be provided for this step"
    assert isinstance(raw_steps, (list, tuple)), (
        "expected_post_sync_steps should be a list or tuple"
    )

    expected_steps = [step for step in raw_steps if isinstance(step, str) and step]
    assert expected_steps, "expected_post_sync_steps must contain string steps"

    lines = (external_repo / "Makefile").read_text(encoding="utf-8").splitlines()
    sync_idx = lines.index("\t$(VALE) sync")
    lint_idx = lines.index("\t$(VALE) --no-global .")

    for step in expected_steps:
        line = f"\t{step}"
        assert line in lines, "Manifest steps should be embedded in the target"
        step_idx = lines.index(line)
        assert sync_idx < step_idx < lint_idx, (
            "Steps should run after sync and before lint"
        )


@then("the install command fails with a release error")
def verify_failure(scenario_state: dict[str, object]) -> None:
    """Assert the CLI surfaces release lookup failures."""
    error = scenario_state.get("error")
    assert error is not None, "Expected an error to be recorded"
    assert "release" in str(error).lower(), (
        "Error message should mention release lookup failure"
    )


@then("the external repository reflects the stilyagi configuration")
def verify_repo_reflects_manifest(
    external_repo: Path, scenario_state: dict[str, object]
) -> None:
    """Validate that manifest-driven settings were applied during install."""
    verify_vale_ini(external_repo, scenario_state)
    verify_makefile(external_repo)
