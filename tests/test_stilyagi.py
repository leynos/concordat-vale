"""Unit tests for the stilyagi packaging helpers."""

from __future__ import annotations

from pathlib import Path
from zipfile import ZipFile

import pytest

from concordat_vale.stilyagi import package_styles


@pytest.fixture
def sample_project(tmp_path: Path) -> Path:
    """Create a temporary project tree with a single concordat style."""
    project_root = tmp_path / "project"
    (project_root / "styles" / "concordat").mkdir(parents=True)
    (project_root / "styles" / "concordat" / "Rule.yml").write_text(
        "extends: existence\n", encoding="utf-8"
    )
    (project_root / "styles" / "config" / "vocabularies" / "concordat").mkdir(
        parents=True
    )
    (
        project_root / "styles" / "config" / "vocabularies" / "concordat" / "accept.txt"
    ).write_text(
        "allowlist\n",
        encoding="utf-8",
    )
    return project_root


@pytest.fixture
def project_without_vocab(tmp_path: Path) -> Path:
    """Create a project tree that lacks shared vocabularies."""
    project_root = tmp_path / "project-no-vocab"
    (project_root / "styles" / "concordat").mkdir(parents=True)
    (project_root / "styles" / "concordat" / "Rule.yml").write_text(
        "extends: existence\n",
        encoding="utf-8",
    )
    return project_root


def test_package_styles_builds_archive_with_ini_and_files(sample_project: Path) -> None:
    """Verify that archives include .vale.ini metadata and style files."""
    archive_path = package_styles(
        project_root=sample_project,
        styles_path=Path("styles"),
        output_dir=Path("dist"),
        version="1.2.3",
        explicit_styles=None,
        vocabulary=None,
        target_glob="*.{md,txt}",
        force=False,
    )

    assert archive_path.exists(), f"Archive not created at {archive_path}"
    with ZipFile(archive_path) as archive:
        namelist = set(archive.namelist())
        assert ".vale.ini" in namelist, "Missing .vale.ini in archive"
        assert "styles/concordat/Rule.yml" in namelist, (
            "Missing styles/concordat/Rule.yml in archive"
        )
        ini_body = archive.read(".vale.ini").decode("utf-8")
        assert "BasedOnStyles = concordat" in ini_body, (
            "Expected 'BasedOnStyles = concordat' in .vale.ini"
        )
        assert "Vocab = concordat" in ini_body, (
            "Expected 'Vocab = concordat' in .vale.ini"
        )


def test_package_styles_refuses_to_overwrite_without_force(
    sample_project: Path,
) -> None:
    """Ensure existing archives are preserved unless --force is used."""
    first = package_styles(
        project_root=sample_project,
        styles_path=Path("styles"),
        output_dir=Path("dist"),
        version="1.2.3",
        explicit_styles=None,
        vocabulary=None,
        target_glob="*.{md,txt}",
        force=False,
    )

    assert first.exists(), f"Initial archive not created at {first}"

    with pytest.raises(FileExistsError):
        package_styles(
            project_root=sample_project,
            styles_path=Path("styles"),
            output_dir=Path("dist"),
            version="1.2.3",
            explicit_styles=None,
            vocabulary=None,
            target_glob="*.{md,txt}",
            force=False,
        )


def test_package_styles_overwrites_with_force(sample_project: Path) -> None:
    """Allow overwriting archives when --force is provided."""
    archive_path = package_styles(
        project_root=sample_project,
        styles_path=Path("styles"),
        output_dir=Path("dist"),
        version="1.2.3",
        explicit_styles=None,
        vocabulary=None,
        target_glob="*.md",
        force=False,
    )
    overwritten = package_styles(
        project_root=sample_project,
        styles_path=Path("styles"),
        output_dir=Path("dist"),
        version="1.2.3",
        explicit_styles=None,
        vocabulary=None,
        target_glob="*.txt",
        force=True,
    )
    assert overwritten == archive_path, (
        "Expected overwritten archive path to match the original"
    )
    with ZipFile(overwritten) as archive:
        ini_body = archive.read(".vale.ini").decode("utf-8")
    assert "[*.txt]" in ini_body, "Expected .vale.ini to contain [*.txt]"


def test_package_styles_missing_styles_dir_raises(tmp_path: Path) -> None:
    """Verify a helpful error is raised when the styles directory is absent."""
    with pytest.raises(FileNotFoundError):
        package_styles(
            project_root=tmp_path,
            styles_path=Path("does-not-exist"),
            output_dir=Path("dist"),
            version="0.0.1",
            explicit_styles=None,
            vocabulary=None,
            target_glob="*.{md,txt}",
            force=False,
        )


def test_package_styles_omits_vocab_when_unavailable(
    project_without_vocab: Path,
) -> None:
    """Ensure Vocab is omitted from .vale.ini when no vocabularies exist."""
    archive_path = package_styles(
        project_root=project_without_vocab,
        styles_path=Path("styles"),
        output_dir=Path("dist"),
        version="0.9.9",
        explicit_styles=None,
        vocabulary=None,
        target_glob="*.{md,txt}",
        force=False,
    )
    with ZipFile(archive_path) as archive:
        ini_body = archive.read(".vale.ini").decode("utf-8")
    assert "Vocab =" not in ini_body, "Expected .vale.ini to omit Vocab entries"


def test_package_styles_omits_vocab_when_multiple_present(
    sample_project: Path,
) -> None:
    """Do not guess when more than one vocabulary directory exists."""
    vocab_root = sample_project / "styles" / "config" / "vocabularies"
    extra_vocab = vocab_root / "alt"
    extra_vocab.mkdir(parents=True, exist_ok=True)
    (extra_vocab / "accept.txt").write_text("alt\n", encoding="utf-8")

    archive_path = package_styles(
        project_root=sample_project,
        styles_path=Path("styles"),
        output_dir=Path("dist"),
        version="1.2.3",
        explicit_styles=None,
        vocabulary=None,
        target_glob="*.{md,txt}",
        force=False,
    )

    with ZipFile(archive_path) as archive:
        ini_body = archive.read(".vale.ini").decode("utf-8")
    assert "Vocab =" not in ini_body, (
        "Expected .vale.ini to omit Vocab entries when multiple exist"
    )


def test_package_styles_respects_ini_styles_path(sample_project: Path) -> None:
    """Use the configured StylesPath entry inside the archive."""
    archive_path = package_styles(
        project_root=sample_project,
        styles_path=Path("styles"),
        output_dir=Path("dist"),
        version="1.2.3",
        explicit_styles=None,
        vocabulary=None,
        target_glob="*.{md,txt}",
        ini_styles_path="custom_styles",
        force=True,
    )

    with ZipFile(archive_path) as archive:
        names = archive.namelist()
        assert any(name.startswith("custom_styles/concordat/") for name in names), (
            "Expected archive to contain files under custom_styles/concordat/"
        )
        ini_body = archive.read(".vale.ini").decode("utf-8")
    assert "StylesPath = custom_styles" in ini_body, (
        "Expected .vale.ini to contain 'StylesPath = custom_styles'"
    )
