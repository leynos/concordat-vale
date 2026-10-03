"""Regression tests for how the Makefile finds the Markdown linter.

`MDLINT` was `$(shell which markdownlint-cli2)`, which expands to nothing when
the tool is missing. Make then read the leading `--` of `$(MDLINT) --fix` as
recipe prefix characters and `make fmt` could report success without linting.
These tests run the real Makefile with a controlled `PATH`, so the missing-tool
path and the present-tool path are both exercised.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_MAKE = shutil.which("make")


def _run_make(
    tmp_path: Path, target: str, *, with_linter: bool
) -> subprocess.CompletedProcess[str]:
    """Run `make <target>` in a scratch copy with a stub-only `PATH`.

    Every tool the target calls is a recording stub that appends its name and
    arguments to `$LOG`; the linter stub is left out when `with_linter` is false.
    """
    assert _MAKE, "make must be installed to run these tests"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "make").symlink_to(_MAKE)
    tools = ["ruff", "mdtablefix", "uv"] + (
        ["markdownlint-cli2"] if with_linter else []
    )
    for tool in tools:
        stub = bin_dir / tool
        stub.write_text(
            f'#!/bin/sh\nprintf "%s\\n" "{tool} $*" >> "$LOG"\n', encoding="utf-8"
        )
        stub.chmod(0o755)
    shutil.copy(_ROOT / "Makefile", tmp_path / "Makefile")
    return subprocess.run(  # noqa: S603 - fixed argv, no shell
        [str(bin_dir / "make"), target],
        cwd=tmp_path,
        env={"PATH": str(bin_dir), "LOG": str(tmp_path / "log")},
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )


def _calls(tmp_path: Path) -> list[str]:
    """Return the recorded tool invocations, in order."""
    log = tmp_path / "log"
    return log.read_text(encoding="utf-8").splitlines() if log.exists() else []


@pytest.mark.parametrize("target", ["markdownlint", "fmt"])
def test_a_missing_linter_fails_with_its_name(tmp_path: Path, target: str) -> None:
    """Without the tool, the target stops and names it, and the linter never runs."""
    result = _run_make(tmp_path, target, with_linter=False)

    assert result.returncode != 0, f"a missing linter did not fail make {target}"
    assert "'markdownlint-cli2' is required, but not installed" in result.stderr, (
        result.stderr
    )
    assert not any(c.startswith("markdownlint-cli2") for c in _calls(tmp_path))


def test_markdownlint_runs_the_linter_over_every_markdown_file(tmp_path: Path) -> None:
    """With the tool on `PATH`, `make markdownlint` passes it the repository glob."""
    result = _run_make(tmp_path, "markdownlint", with_linter=True)

    assert result.returncode == 0, result.stderr
    assert _calls(tmp_path) == ["markdownlint-cli2 **/*.md"]


def test_fmt_rewrites_with_mdtablefix_then_runs_the_linter_with_fix(
    tmp_path: Path,
) -> None:
    """With the tool on `PATH`, `make fmt` runs the linter with `--fix`, last."""
    result = _run_make(tmp_path, "fmt", with_linter=True)

    assert result.returncode == 0, result.stderr
    calls = _calls(tmp_path)
    assert calls[-1] == "markdownlint-cli2 --fix **/*.md", calls
    assert any(c.startswith("mdtablefix --in-place") for c in calls[:-1]), calls


def test_mdlint_is_a_literal_command_name() -> None:
    """`MDLINT` must not be a `$(shell ...)` lookup that can expand to nothing."""
    first = [
        line
        for line in (_ROOT / "Makefile").read_text(encoding="utf-8").splitlines()
        if line.startswith("MDLINT")
    ]

    assert first == ["MDLINT ?= markdownlint-cli2"], first
