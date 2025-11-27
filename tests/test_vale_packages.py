"""Integration tests that ensure packaged archives work with `vale sync`."""

from __future__ import annotations

import http.server
import os
import shutil
import subprocess
import textwrap
import threading
import typing as typ
from functools import partial
from pathlib import Path

import pytest

from concordat_vale.stilyagi_packaging import (
    PackagingPaths,
    StyleConfig,
    package_styles,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
VALE_BIN = shutil.which("vale")


def _run_vale_command(
    args: list[str], env: dict[str, str], cwd: Path
) -> subprocess.CompletedProcess[str]:
    """Run a vale command with common configuration."""
    assert VALE_BIN is not None, "vale binary must be available to run this test"
    return subprocess.run(  # noqa: S603 - repository-controlled command invocation
        [VALE_BIN, *args],
        cwd=str(cwd),
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def _verify_synced_files(workspace: Path) -> None:
    synced_style = workspace / "styles" / "simple-style" / "SimpleSpelling.yml"
    assert synced_style.exists(), (
        f"vale sync did not install the packaged style at {synced_style}"
    )
    synced_vocab = (
        workspace / "styles" / "config" / "vocabularies" / "simple" / "accept.txt"
    )
    assert synced_vocab.exists(), (
        f"vale sync did not unpack the vocabulary file at {synced_vocab}"
    )


def _run_vale_sync(env: dict[str, str], cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run vale sync command."""
    return _run_vale_command(["sync"], env, cwd)


def _run_vale_lint(
    target: Path, env: dict[str, str], cwd: Path
) -> subprocess.CompletedProcess[str]:
    """Run vale lint command on a target file."""
    return _run_vale_command([str(target)], env, cwd)


@pytest.fixture
def http_server(
    tmp_path_factory: pytest.TempPathFactory,
) -> typ.Iterator[tuple[str, Path]]:
    """Serve files out of a temporary directory for the duration of the test."""
    serve_dir = tmp_path_factory.mktemp("serve")

    class QuietHandler(http.server.SimpleHTTPRequestHandler):
        def log_message(  # type: ignore[override]
            self, msg_format: str, *args: object
        ) -> None:
            return  # suppress noisy stderr logging during tests

    server = http.server.ThreadingHTTPServer(
        ("127.0.0.1", 0),
        partial(QuietHandler, directory=str(serve_dir)),
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", serve_dir
    finally:
        server.shutdown()
        thread.join()


@pytest.mark.slow
def test_vale_sync_accepts_packaged_archive(
    tmp_path: Path, http_server: tuple[str, Path]
) -> None:
    """Package Concordat, host it over HTTP, and verify `vale sync` downloads it."""
    if VALE_BIN is None:
        pytest.skip("vale CLI not installed")

    base_url, serve_dir = http_server
    version = "sync-test"
    archive_path = package_styles(
        paths=PackagingPaths(
            project_root=REPO_ROOT,
            styles_path=Path("styles"),
            output_dir=tmp_path,
        ),
        config=StyleConfig(),
        version=version,
        force=True,
    )
    served_archive = serve_dir / archive_path.name
    shutil.copy2(archive_path, served_archive)

    vale_ini = tmp_path / ".vale.ini"
    vale_ini.write_text(
        f"""StylesPath = styles
Packages = {base_url}/{archive_path.name}

[*.md]
BasedOnStyles = concordat
""",
        encoding="utf-8",
    )

    env = os.environ.copy()
    env["VALE_CONFIG_PATH"] = str(vale_ini)
    vale_home = tmp_path / ".vale-home"
    env["VALE_HOME"] = str(vale_home)

    result = _run_vale_sync(env, tmp_path)
    assert result.returncode == 0, (
        f"vale sync failed:\nSTDOUT:\n{result.stdout}\n\nSTDERR:\n{result.stderr}"
    )


def _create_test_style_and_vocab(styles_root: Path) -> tuple[Path, Path]:
    style_dir = styles_root / "simple-style"
    style_dir.mkdir(parents=True)
    style_path = style_dir / "SimpleSpelling.yml"
    style_path.write_text(
        textwrap.dedent(
            """
            extends: spelling
            message: "Spell-check project-specific words."
            level: error
            locale: en-US
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )

    vocab_dir = styles_root / "config" / "vocabularies" / "simple"
    vocab_dir.mkdir(parents=True)
    vocab_path = vocab_dir / "accept.txt"
    vocab_path.write_text("foobarium\n", encoding="utf-8")
    return style_path, vocab_path


def _setup_vale_environment(
    workspace: Path, base_url: str, archive_name: str, tmp_path: Path
) -> dict[str, str]:
    vale_ini = workspace / ".vale.ini"
    vale_ini.write_text(
        textwrap.dedent(
            f"""
            StylesPath = styles
            Packages = {base_url}/{archive_name}
            Vocab = simple

            [*.md]
            BasedOnStyles = simple-style
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )

    env = os.environ.copy()
    vale_home = tmp_path / ".vale-home"
    env["VALE_HOME"] = str(vale_home)
    env["VALE_CONFIG_PATH"] = str(vale_ini)
    return env


@pytest.mark.slow
def test_vale_lint_succeeds_after_installing_packaged_style(
    tmp_path: Path, http_server: tuple[str, Path]
) -> None:
    """Build a minimal style + vocab package, sync it, and lint successfully."""
    if VALE_BIN is None:
        pytest.skip("vale CLI not installed")

    base_url, serve_dir = http_server
    project_root = tmp_path / "package-src"
    workspace = tmp_path / "workspace"
    project_root.mkdir()
    workspace.mkdir()

    styles_root = project_root / "styles"
    _create_test_style_and_vocab(styles_root)

    archive_path = package_styles(
        paths=PackagingPaths(
            project_root=project_root,
            styles_path=Path("styles"),
            output_dir=tmp_path,
        ),
        config=StyleConfig(),
        version="lint-test",
        force=True,
    )
    served_archive = serve_dir / archive_path.name
    shutil.copy2(archive_path, served_archive)

    env = _setup_vale_environment(workspace, base_url, archive_path.name, tmp_path)
    sample_doc = workspace / "doc.md"
    sample_doc.write_text("Our codename is foobarium.\n", encoding="utf-8")

    sync_result = _run_vale_sync(env, workspace)
    assert sync_result.returncode == 0, (
        "vale sync failed:\n"
        f"STDOUT:\n{sync_result.stdout}\n\nSTDERR:\n{sync_result.stderr}"
    )

    _verify_synced_files(workspace)

    lint_result = _run_vale_lint(sample_doc, env, workspace)
    assert lint_result.returncode == 0, (
        "vale lint failed:\n"
        f"STDOUT:\n{lint_result.stdout}\n\nSTDERR:\n{lint_result.stderr}"
    )
