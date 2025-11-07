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

    assert archive_path.exists()
    with ZipFile(archive_path) as archive:
        namelist = set(archive.namelist())
        assert ".vale.ini" in namelist
        assert "styles/concordat/Rule.yml" in namelist
        ini_body = archive.read(".vale.ini").decode("utf-8")
        assert "BasedOnStyles = concordat" in ini_body
        assert "Vocab = concordat" in ini_body


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

    assert first.exists()

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
