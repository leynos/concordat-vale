"""Black-box tests that drive the release workflow via ``act``.

These tests follow the guidance in
``docs/local-validation-of-github-actions-with-act-and-pytest.md``: invoke the
workflow as-is, capture artefacts/logs, and assert on the observable side
effects.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_FILE = REPO_ROOT / ".github" / "workflows" / "release.yml"
EVENT_FILE = REPO_ROOT / "tests" / "fixtures" / "workflow_dispatch_release.json"
DIST_DIR = REPO_ROOT / "dist"
ACT_IMAGE = os.environ.get("ACT_IMAGE", "catthehacker/ubuntu:act-latest")
ACT_JOB = "package-and-upload"
DEFAULT_ACT_CACHE = REPO_ROOT / ".act-cache"


def _require_act() -> None:
    """Skip if act is unavailable on the host."""
    if shutil.which("act") is None:
        pytest.skip(
            "act CLI is not installed; see "
            "docs/local-validation-of-github-actions-with-act-and-pytest.md",
        )
    _require_container_runtime()


def _require_container_runtime() -> None:
    """Ensure Docker/Podman is present and the daemon is reachable."""
    cli = shutil.which("docker") or shutil.which("podman")
    if cli is None:
        pytest.skip("Docker/Podman CLI is unavailable; cannot run act.")
    probe = subprocess.run(  # noqa: S603 - runs trusted docker/podman CLI for a health check
        [cli, "info"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    if probe.returncode != 0:
        summary = probe.stdout.strip().splitlines()[-1] if probe.stdout else ""
        pytest.skip(
            f"{cli} is not running or accessible ({summary}). "
            "Start the container runtime to run act tests."
        )


def _parse_json_logs(raw: str) -> list[dict[str, object]]:
    """Return structured entries from ``act --json`` output."""
    entries: list[dict[str, object]] = []
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped.startswith("{"):
            continue
        try:
            entries.append(json.loads(stripped))
        except json.JSONDecodeError:
            continue
    return entries


def _run_release_workflow(*, artifact_dir: Path) -> tuple[int, str]:
    """Invoke the release workflow with ``act workflow_dispatch``."""
    artifact_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        "act",
        "workflow_dispatch",
        "-j",
        ACT_JOB,
        "-W",
        str(WORKFLOW_FILE),
        "-e",
        str(EVENT_FILE),
        "-P",
        f"ubuntu-latest={ACT_IMAGE}",
        "--artifact-server-path",
        str(artifact_dir),
        "--json",
        "-b",
    ]
    env = os.environ.copy()
    env.setdefault("GITHUB_TOKEN", "dummy-token")
    cache_dir = Path(env.get("ACT_CACHE_DIR", DEFAULT_ACT_CACHE))
    cache_dir.mkdir(parents=True, exist_ok=True)
    env["ACT_CACHE_DIR"] = str(cache_dir)
    action_cache = cache_dir / "actions"
    action_cache.mkdir(parents=True, exist_ok=True)
    cache_server_path = cache_dir / "cache-server"
    cache_server_path.mkdir(parents=True, exist_ok=True)
    cmd.extend(
        [
            "--action-cache-path",
            str(action_cache),
            "--cache-server-path",
            str(cache_server_path),
        ]
    )
    completed = subprocess.run(  # noqa: S603 - executes the checked-in workflow via act
        cmd,
        cwd=str(REPO_ROOT),
        text=True,
        capture_output=True,
        check=False,
    )
    logs = completed.stdout + "\n" + completed.stderr
    return completed.returncode, logs


@pytest.mark.act
@pytest.mark.slow
@pytest.mark.timeout(300)
def test_release_workflow_packages_archive(tmp_path: Path) -> None:
    """Ensure the release workflow packages Concordat Vale locally."""
    _require_act()
    artifact_dir = tmp_path / "act-artifacts"
    existing_archives = {path.name for path in DIST_DIR.glob("*.zip")}
    start_ts = time.time()

    code, logs = _run_release_workflow(artifact_dir=artifact_dir)
    if code != 0:
        pytest.fail(f"act workflow_dispatch failed with exit code {code}:\n{logs}")

    archive = DIST_DIR / "concordat-0.1.0.zip"
    assert archive.exists(), f"release workflow did not emit archive:\n{logs}"
    assert archive.stat().st_size > 0, "archive should never be empty"
    assert archive.stat().st_mtime >= start_ts, (
        "archive timestamp predates the act run, so packaging likely failed"
    )

    # Validate the structured log stream contains the packaging step output.
    entries = _parse_json_logs(logs)
    packaging_outputs = []
    for entry in entries:
        haystack = " ".join(
            str(entry.get(key, ""))
            for key in (
                "name",
                "message",
                "Message",
                "msg",
                "Msg",
                "Output",
                "output",
            )
        )
        if "Package Concordat Vale style" in haystack:
            packaging_outputs.append(entry)
    assert packaging_outputs, f"Expected packaging step logs in the act stream:\n{logs}"

    # Clean up any archives created solely by this test.
    for path in DIST_DIR.glob("*.zip"):
        if path.name not in existing_archives:
            path.unlink()
