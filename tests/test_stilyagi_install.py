"""Unit tests for the stilyagi install helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from concordat_vale import stilyagi, stilyagi_install


def test_update_vale_ini_merges_existing_values(tmp_path: Path) -> None:
    """Ensure required entries are inserted while preserving existing ones."""
    ini_path = tmp_path / ".vale.ini"
    ini_path.write_text(
        """StylesPath = styles

[legacy]
BasedOnStyles = Vale
""",
        encoding="utf-8",
    )

    stilyagi._update_vale_ini(  # type: ignore[attr-defined]
        ini_path=ini_path,
        packages_url="https://example.test/v9.9.9/concordat-9.9.9.zip",
        manifest=stilyagi_install.InstallManifest(
            style_name="concordat",
            vocab_name="concordat",
            min_alert_level="warning",
        ),
    )

    body = ini_path.read_text(encoding="utf-8")
    assert "Packages = https://example.test/v9.9.9/concordat-9.9.9.zip" in body, (
        "Packages URL should be written"
    )
    assert "MinAlertLevel = warning" in body, "MinAlertLevel should be set"
    assert "Vocab = concordat" in body, "Vocab should match style name"
    assert "StylesPath = styles" in body, "Existing root option should be preserved"
    assert "[legacy]" in body, "Existing sections should be retained"
    assert "BlockIgnores = (?m)^\\[\\^\\d+\\]:" in body, (
        "BlockIgnores pattern should be present"
    )


def test_update_vale_ini_creates_file_and_orders_sections(tmp_path: Path) -> None:
    """Create .vale.ini when missing and order sections deterministically."""
    ini_path = tmp_path / ".vale.ini"
    stilyagi._update_vale_ini(  # type: ignore[attr-defined]
        ini_path=ini_path,
        packages_url="https://example.test/v1.0.0/concordat-1.0.0.zip",
        manifest=stilyagi_install.InstallManifest(
            style_name="concordat",
            vocab_name="concordat",
            min_alert_level="warning",
        ),
    )

    body = ini_path.read_text(encoding="utf-8")
    assert "Packages = https://example.test/v1.0.0/concordat-1.0.0.zip" in body, (
        "Packages URL should be written when creating file"
    )
    assert "MinAlertLevel = warning" in body, "MinAlertLevel should be set"
    assert "Vocab = concordat" in body, "Vocab should match style name"
    section_positions = [
        body.index("[docs/**/*.{md,markdown,mdx}]"),
        body.index("[AGENTS.md]"),
        body.index("[*.{rs,ts,js,sh,py}]"),
        body.index("[README.md]"),
    ]
    assert section_positions == sorted(section_positions), "Sections should be ordered"


def test_update_makefile_adds_phony_and_target(tmp_path: Path) -> None:
    """Replace any existing vale target and merge .PHONY entries."""
    makefile = tmp_path / "Makefile"
    makefile.write_text(
        """.PHONY: test

vale: ## old target
\t@echo outdated

lint:
\t@echo lint
""",
        encoding="utf-8",
    )

    stilyagi._update_makefile(makefile)  # type: ignore[attr-defined]

    contents = makefile.read_text(encoding="utf-8")
    assert ".PHONY: test vale" in contents, ".PHONY should include vale"
    assert "vale: $(VALE) $(ACRONYM_SCRIPT) ## Check prose" in contents, (
        "vale target should be rewritten"
    )
    assert "\t$(VALE) sync" in contents, "vale target should sync before linting"
    assert "\t$(VALE) --no-global ." in contents, "vale target should lint workspace"
    assert "lint:" in contents, "Other targets should remain intact"


def test_update_makefile_creates_when_missing(tmp_path: Path) -> None:
    """Create Makefile with VALE variable, .PHONY, and target when absent."""
    makefile = tmp_path / "Makefile"
    stilyagi._update_makefile(makefile)  # type: ignore[attr-defined]

    contents = makefile.read_text(encoding="utf-8")
    assert "VALE ?= vale" in contents, "VALE variable should default to vale"
    assert any(line.lstrip().startswith(".PHONY") for line in contents.splitlines()), (
        ".PHONY line should be present"
    )
    assert "vale: $(VALE) $(ACRONYM_SCRIPT) ## Check prose" in contents, (
        "vale target should be added"
    )


def test_update_makefile_does_not_duplicate_phony(tmp_path: Path) -> None:
    """Leave existing .PHONY with vale untouched."""
    makefile = tmp_path / "Makefile"
    makefile.write_text(
        ".PHONY: vale test\n\nother: \n\t@echo hi\n",
        encoding="utf-8",
    )

    stilyagi._update_makefile(makefile)  # type: ignore[attr-defined]

    contents = makefile.read_text(encoding="utf-8")
    assert contents.count(".PHONY") == 1, ".PHONY should not be duplicated"
    assert "vale: $(VALE) $(ACRONYM_SCRIPT) ## Check prose" in contents, (
        "vale target should remain present"
    )


def test_update_makefile_adds_phony_when_absent(tmp_path: Path) -> None:
    """Insert .PHONY when missing and add vale target."""
    makefile = tmp_path / "Makefile"
    makefile.write_text("lint:\n\t@echo lint\n", encoding="utf-8")

    stilyagi._update_makefile(makefile)  # type: ignore[attr-defined]

    contents = makefile.read_text(encoding="utf-8")
    assert any(line.lstrip().startswith(".PHONY") for line in contents.splitlines()), (
        ".PHONY should be inserted when absent"
    )
    assert "vale: $(VALE) $(ACRONYM_SCRIPT) ## Check prose" in contents, (
        "vale target should be added when missing"
    )


@pytest.mark.parametrize(
    ("repo_ref", "expected_owner", "expected_repo", "expected_style"),
    [
        ("owner/repo", "owner", "repo", "repo"),
        ("owner/repo-vale", "owner", "repo-vale", "repo"),
    ],
)
def test_parse_repo_reference_valid_inputs(
    repo_ref: str, expected_owner: str, expected_repo: str, expected_style: str
) -> None:
    """_parse_repo_reference returns (owner, repo_name, style_name) for valid inputs."""
    result = stilyagi._parse_repo_reference(repo_ref)  # type: ignore[attr-defined]
    assert result == (expected_owner, expected_repo, expected_style), (
        f"Repository reference {repo_ref!r} should parse correctly"
    )


@pytest.mark.parametrize(
    "repo_ref",
    [
        "owner",  # no slash
        "owner/repo/xyz",  # too many segments
        "/repo",  # missing owner
        "owner/",  # missing repo name
        "/",  # both segments empty
        "   /repo",  # whitespace owner
        "owner/   ",  # whitespace repo
        "   /   ",  # whitespace owner and repo
    ],
)
def test_parse_repo_reference_invalid_inputs(repo_ref: str) -> None:
    """_parse_repo_reference rejects malformed repo references with a clear error."""
    with pytest.raises(
        ValueError,
        match=r"Repository reference must be in the form ['\"]owner/name['\"]",
    ):
        stilyagi._parse_repo_reference(repo_ref)  # type: ignore[attr-defined]


def test_parse_install_manifest_defaults() -> None:
    """Default manifest uses provided style for vocab and alert level."""
    manifest = stilyagi_install._parse_install_manifest(  # type: ignore[attr-defined]
        raw=None,
        default_style_name="concordat",
    )

    assert manifest.style_name == "concordat"
    assert manifest.vocab_name == "concordat"
    assert manifest.min_alert_level == "warning"


def test_parse_install_manifest_applies_overrides() -> None:
    """Manifest fields override defaults when provided."""
    manifest = stilyagi_install._parse_install_manifest(  # type: ignore[attr-defined]
        raw={
            "install": {
                "style_name": "custom-style",
                "vocab": "custom-vocab",
                "min_alert_level": "error",
            }
        },
        default_style_name="concordat",
    )

    assert manifest.style_name == "custom-style"
    assert manifest.vocab_name == "custom-vocab"
    assert manifest.min_alert_level == "error"


def test_perform_install_honours_manifest_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Installation uses manifest-derived style and alert level."""
    project_root = tmp_path / "consumer"
    project_root.mkdir()

    _, ini_path, makefile_path = stilyagi_install._resolve_install_paths(  # type: ignore[attr-defined]
        cwd=project_root,
        project_root=Path(),
        vale_ini=Path(".vale.ini"),
        makefile=Path("Makefile"),
    )

    manifest = stilyagi_install.InstallManifest(
        style_name="custom-style",
        vocab_name="custom-vocab",
        min_alert_level="error",
    )

    monkeypatch.setattr(
        stilyagi_install,
        "_load_install_manifest",
        lambda packages_url, default_style_name: manifest,
        raising=True,
    )
    monkeypatch.setattr(
        stilyagi_install,
        "_resolve_release",
        lambda **_kwargs: (
            "2.0.0",
            "v2.0.0",
            "https://example.test/custom-style-2.0.0.zip",
        ),
        raising=True,
    )

    config = stilyagi_install.InstallConfig(
        owner="example",
        repo_name="custom-style",
        style_name="default-style",
        ini_path=ini_path,
        makefile_path=makefile_path,
    )

    message = stilyagi_install._perform_install(config=config)  # type: ignore[attr-defined]

    body = ini_path.read_text(encoding="utf-8")
    assert "MinAlertLevel = error" in body, "Manifest should set MinAlertLevel"
    assert "Vocab = custom-vocab" in body, "Manifest should override vocab"
    assert "BasedOnStyles = custom-style" in body, (
        "Style name should come from manifest"
    )
    assert "custom-style 2.0.0" in message, (
        "Message should reflect manifest style/version"
    )
