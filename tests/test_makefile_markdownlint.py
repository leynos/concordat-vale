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


def _run_make(tmp_path: Path, *, with_linter: bool) -> subprocess.CompletedProcess[str]:
    """Run `make markdownlint` in a scratch copy with a one-tool `PATH`."""
    assert _MAKE, "make must be installed to run these tests"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "make").symlink_to(_MAKE)
    if with_linter:
        stub = bin_dir / "markdownlint-cli2"
        stub.write_text(
            '#!/bin/sh\nprintf "%s\\n" "$*" > "$ARGS_FILE"\n', encoding="utf-8"
        )
        stub.chmod(0o755)
    shutil.copy(_ROOT / "Makefile", tmp_path / "Makefile")
    return subprocess.run(  # noqa: S603 - fixed argv, no shell
        [str(bin_dir / "make"), "markdownlint"],
        cwd=tmp_path,
        env={"PATH": str(bin_dir), "ARGS_FILE": str(tmp_path / "args")},
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )


def test_a_missing_linter_fails_with_its_name(tmp_path: Path) -> None:
    """Without the tool, `make markdownlint` stops and names it."""
    result = _run_make(tmp_path, with_linter=False)

    assert result.returncode != 0, "a missing linter did not fail the target"
    assert "'markdownlint-cli2' is required, but not installed" in result.stderr, (
        result.stderr
    )


def test_a_present_linter_is_run_over_every_markdown_file(tmp_path: Path) -> None:
    """With the tool on `PATH`, it receives the repository-wide glob."""
    result = _run_make(tmp_path, with_linter=True)

    assert result.returncode == 0, result.stderr
    assert (tmp_path / "args").read_text(encoding="utf-8").strip() == "**/*.md"


def test_mdlint_is_a_literal_command_name() -> None:
    """`MDLINT` must not be a `$(shell ...)` lookup that can expand to nothing."""
    first = [
        line
        for line in (_ROOT / "Makefile").read_text(encoding="utf-8").splitlines()
        if line.startswith("MDLINT")
    ]

    assert first == ["MDLINT ?= markdownlint-cli2"], first


@pytest.mark.parametrize("target", ["fmt"])
def test_fmt_runs_the_linter_with_fix_directly(target: str) -> None:
    """The recipe calls `$(MDLINT) --fix`, the command the literal name protects."""
    text = (_ROOT / "Makefile").read_text(encoding="utf-8")

    assert f"{target}:" in text
    assert '$(MDLINT) --fix "**/*.md"' in text
