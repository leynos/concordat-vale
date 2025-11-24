"""Unit tests for release workflow configuration."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RELEASE_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "release.yml"


def test_release_workflow_includes_act_uv_isolation_steps() -> None:
    """Ensure act-specific uv path isolation steps are present."""
    contents = RELEASE_WORKFLOW.read_text(encoding="utf-8")

    assert "Isolate uv paths when running under act" in contents
    assert "env.ACT_CONTEXT == 'true'" in contents
    assert "RUNNER_TEMP:-/tmp" in contents
    assert "UV_CACHE_DIR=${TEMP_ROOT}/concordat-vale-uv-cache" in contents
    assert "UV_TOOL_DIR=${TEMP_ROOT}/concordat-vale-uv-tools" in contents
    assert "UV_PROJECT_ENVIRONMENT=${TEMP_ROOT}/concordat-vale-uv-venv" in contents
    assert "Expose uv env when running under act" in contents
