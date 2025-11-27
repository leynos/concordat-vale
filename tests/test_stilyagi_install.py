"""Unit tests for the stilyagi install helpers."""

from __future__ import annotations

import dataclasses as dc
import io
import typing as typ
from pathlib import Path
from zipfile import ZipFile

import pytest

from concordat_vale import stilyagi, stilyagi_install


@dc.dataclass
class _ExpectedManifest:
    """Expected values for manifest parsing assertions."""

    style: str
    vocab: str
    min_alert: str
    post_sync_steps: tuple[str, ...] = ()


DEFAULT_MANIFEST = stilyagi_install.InstallManifest(
    style_name="concordat",
    vocab_name="concordat",
    min_alert_level="warning",
)


def _assert_default_manifest(manifest: stilyagi_install.InstallManifest) -> None:
    assert manifest.style_name == "concordat"
    assert manifest.vocab_name == "concordat"
    assert manifest.min_alert_level == "warning"
    assert manifest.post_sync_steps == ()


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

    stilyagi._update_makefile(  # type: ignore[attr-defined]
        makefile, manifest=DEFAULT_MANIFEST
    )

    contents = makefile.read_text(encoding="utf-8")
    assert ".PHONY: test vale" in contents, ".PHONY should include vale"
    assert "vale: $(VALE) ## Check prose" in contents, "vale target should be rewritten"
    assert "\t$(VALE) sync" in contents, "vale target should sync before linting"
    assert "\t$(VALE) --no-global ." in contents, "vale target should lint workspace"
    assert "lint:" in contents, "Other targets should remain intact"


def test_update_makefile_creates_when_missing(tmp_path: Path) -> None:
    """Create Makefile with VALE variable, .PHONY, and target when absent."""
    makefile = tmp_path / "Makefile"
    stilyagi._update_makefile(makefile, manifest=DEFAULT_MANIFEST)  # type: ignore[attr-defined]

    contents = makefile.read_text(encoding="utf-8")
    assert "VALE ?= vale" in contents, "VALE variable should default to vale"
    assert any(line.lstrip().startswith(".PHONY") for line in contents.splitlines()), (
        ".PHONY line should be present"
    )
    assert "vale: $(VALE) ## Check prose" in contents, "vale target should be added"


def test_update_makefile_does_not_duplicate_phony(tmp_path: Path) -> None:
    """Leave existing .PHONY with vale untouched."""
    makefile = tmp_path / "Makefile"
    makefile.write_text(
        ".PHONY: vale test\n\nother: \n\t@echo hi\n",
        encoding="utf-8",
    )

    stilyagi._update_makefile(makefile, manifest=DEFAULT_MANIFEST)  # type: ignore[attr-defined]

    contents = makefile.read_text(encoding="utf-8")
    assert contents.count(".PHONY") == 1, ".PHONY should not be duplicated"
    assert "vale: $(VALE) ## Check prose" in contents, (
        "vale target should remain present"
    )


def test_update_makefile_adds_phony_when_absent(tmp_path: Path) -> None:
    """Insert .PHONY when missing and add vale target."""
    makefile = tmp_path / "Makefile"
    makefile.write_text("lint:\n\t@echo lint\n", encoding="utf-8")

    stilyagi._update_makefile(makefile, manifest=DEFAULT_MANIFEST)  # type: ignore[attr-defined]

    contents = makefile.read_text(encoding="utf-8")
    assert any(line.lstrip().startswith(".PHONY") for line in contents.splitlines()), (
        ".PHONY should be inserted when absent"
    )
    assert "vale: $(VALE) ## Check prose" in contents, (
        "vale target should be added when missing"
    )


def test_update_makefile_includes_post_sync_steps(tmp_path: Path) -> None:
    """Insert manifest-driven steps between sync and lint."""
    makefile = tmp_path / "Makefile"
    manifest = stilyagi_install.InstallManifest(
        style_name="concordat",
        vocab_name="concordat",
        min_alert_level="warning",
        post_sync_steps=(
            "uv run stilyagi update-tengo-map --source one --dest two --type true",
            "uv run stilyagi update-tengo-map --source three --dest four --type =",
        ),
    )

    stilyagi._update_makefile(makefile, manifest=manifest)  # type: ignore[attr-defined]

    contents = makefile.read_text(encoding="utf-8").splitlines()
    assert (
        "\tuv run stilyagi update-tengo-map --source one --dest two --type true"
        in contents
    ), "post sync steps should be added"
    assert (
        "\tuv run stilyagi update-tengo-map --source three --dest four --type ="
        in contents
    ), "multiple steps should be preserved"

    sync_idx = contents.index("\t$(VALE) sync")
    first_step_idx = contents.index(
        "\tuv run stilyagi update-tengo-map --source one --dest two --type true"
    )
    lint_idx = contents.index("\t$(VALE) --no-global .")
    assert sync_idx < first_step_idx < lint_idx, (
        "steps should sit between sync and lint"
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

    _assert_default_manifest(manifest)


@pytest.mark.parametrize(
    (
        "test_id",
        "raw_input",
        "expected",
    ),
    [
        (
            "applies_overrides",
            {
                "install": {
                    "style_name": "custom-style",
                    "vocab": "custom-vocab",
                    "min_alert_level": "error",
                }
            },
            _ExpectedManifest(
                style="custom-style", vocab="custom-vocab", min_alert="error"
            ),
        ),
        (
            "partial_missing_vocab",
            {
                "install": {
                    "style_name": "custom-style",
                    "min_alert_level": "error",
                }
            },
            _ExpectedManifest(
                style="custom-style", vocab="custom-style", min_alert="error"
            ),
        ),
        (
            "partial_missing_min_alert_level",
            {
                "install": {
                    "style_name": "custom-style",
                    "vocab": "custom-vocab",
                }
            },
            _ExpectedManifest(
                style="custom-style", vocab="custom-vocab", min_alert="warning"
            ),
        ),
        (
            "whitespace_only_fields",
            {
                "install": {
                    "style_name": "   ",
                    "vocab": " \t ",
                    "min_alert_level": "  ",
                }
            },
            _ExpectedManifest(
                style="concordat", vocab="concordat", min_alert="warning"
            ),
        ),
        (
            "captures_post_sync_steps",
            {
                "install": {
                    "post_sync_steps": [
                        {
                            "action": "update-tengo-map",
                            "source": " a ",
                            "dest": " b ",
                            "type": "=n",
                        }
                    ]
                }
            },
            _ExpectedManifest(
                style="concordat",
                vocab="concordat",
                min_alert="warning",
                post_sync_steps=(
                    (
                        "uv run stilyagi update-tengo-map --source ' a ' "
                        "--dest ' b ' --type =n"
                    ),
                ),
            ),
        ),
    ],
)
def test_parse_install_manifest_overrides(
    test_id: str,
    raw_input: dict[str, object],
    expected: _ExpectedManifest,
) -> None:
    """Manifest fields are normalised according to provided overrides."""
    manifest = stilyagi_install._parse_install_manifest(  # type: ignore[attr-defined]
        raw=raw_input,
        default_style_name="concordat",
    )

    assert manifest.style_name == expected.style
    assert manifest.vocab_name == expected.vocab
    assert manifest.min_alert_level == expected.min_alert
    assert manifest.post_sync_steps == expected.post_sync_steps


def test_parse_install_manifest_non_mapping_raw_uses_defaults() -> None:
    """Non-dict manifest inputs fall back to defaults."""
    manifest = stilyagi_install._parse_install_manifest(  # type: ignore[attr-defined]
        raw=typ.cast("dict[str, object] | None", "not-a-dict"),
        default_style_name="concordat",
    )

    _assert_default_manifest(manifest)


def test_parse_install_manifest_non_mapping_install_section_uses_defaults() -> None:
    """Non-dict install section triggers defaults."""
    manifest = stilyagi_install._parse_install_manifest(  # type: ignore[attr-defined]
        raw={"install": "not-a-dict"},
        default_style_name="concordat",
    )

    _assert_default_manifest(manifest)


def test_parse_install_manifest_rejects_string_post_sync_step() -> None:
    """String post_sync_steps are rejected as invalid."""
    with pytest.raises(TypeError):
        stilyagi_install._parse_install_manifest(  # type: ignore[attr-defined]
            raw={"install": {"post_sync_steps": " echo me "}},
            default_style_name="concordat",
        )


def test_parse_install_manifest_rejects_non_list_post_sync_steps() -> None:
    """Non-list post_sync_steps raises a clear error."""
    with pytest.raises(TypeError, match=r"list of tables"):
        stilyagi_install._parse_install_manifest(  # type: ignore[attr-defined]
            raw={"install": {"post_sync_steps": 123}},
            default_style_name="concordat",
        )


def test_parse_install_manifest_rejects_non_string_list_entries() -> None:
    """Lists must contain only tables."""
    with pytest.raises(TypeError, match=r"list of tables"):
        stilyagi_install._parse_install_manifest(  # type: ignore[attr-defined]
            raw={"install": {"post_sync_steps": ["ok"]}},
            default_style_name="concordat",
        )


def test_parse_install_manifest_allows_explicit_empty_list() -> None:
    """Empty list normalises to an empty tuple."""
    manifest = stilyagi_install._parse_install_manifest(  # type: ignore[attr-defined]
        raw={"install": {"post_sync_steps": []}},
        default_style_name="concordat",
    )

    assert manifest.post_sync_steps == ()


def test_parse_install_manifest_rejects_unknown_action() -> None:
    """Only update-tengo-map actions are supported."""
    with pytest.raises(ValueError, match=r"update-tengo-map"):
        stilyagi_install._parse_install_manifest(  # type: ignore[attr-defined]
            raw={
                "install": {
                    "post_sync_steps": [
                        {"action": "something-else", "source": "a", "dest": "b"}
                    ]
                }
            },
            default_style_name="concordat",
        )


def test_parse_install_manifest_rejects_invalid_value_type() -> None:
    """Value type must be among the allowed Tengo update options."""
    with pytest.raises(ValueError, match=r"one of"):
        stilyagi_install._parse_install_manifest(  # type: ignore[attr-defined]
            raw={
                "install": {
                    "post_sync_steps": [
                        {
                            "action": "update-tengo-map",
                            "source": "a",
                            "dest": "b",
                            "type": "invalid",
                        }
                    ]
                }
            },
            default_style_name="concordat",
        )


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
        post_sync_steps=("echo prepare custom",),
    )

    monkeypatch.setattr(
        stilyagi_install,
        "_load_install_manifest",
        lambda **_kwargs: manifest,
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
    makefile_body = makefile_path.read_text(encoding="utf-8")
    assert "\techo prepare custom" in makefile_body, (
        "Manifest post-sync steps should be written to the Makefile"
    )
    assert "custom-style 2.0.0" in message, (
        "Message should reflect manifest style/version"
    )


def test_load_install_manifest_skips_download_when_env_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Env override bypasses download and returns defaults."""
    download_called = False

    def _download_fail(*_: object, **__: object) -> None:
        nonlocal download_called
        download_called = True
        pytest.fail("download should be skipped when env is set")

    monkeypatch.setenv("STILYAGI_SKIP_MANIFEST_DOWNLOAD", "1")
    monkeypatch.setattr(stilyagi_install, "_download_packages_archive", _download_fail)

    manifest = stilyagi_install._load_install_manifest(  # type: ignore[attr-defined]
        packages_url="https://example.test/archive.zip",
        default_style_name="concordat",
    )

    assert download_called is False
    assert manifest.style_name == "concordat"
    assert manifest.vocab_name == "concordat"
    assert manifest.min_alert_level == "warning"


def test_load_install_manifest_uses_manifest_when_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Manifest embedded in archive is parsed and applied."""
    buffer = io.BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr(
            "concordat-0.0.1/stilyagi.toml",
            """[install]
style_name = "manifest-style"
vocab = "manifest-vocab"
min_alert_level = "error"
""",
        )

    monkeypatch.delenv("STILYAGI_SKIP_MANIFEST_DOWNLOAD", raising=False)
    monkeypatch.setattr(
        stilyagi_install,
        "_download_packages_archive",
        lambda *_args, **_kwargs: buffer.getvalue(),
    )

    manifest = stilyagi_install._load_install_manifest(  # type: ignore[attr-defined]
        packages_url="https://example.test/archive.zip",
        default_style_name="concordat",
    )

    assert manifest.style_name == "manifest-style"
    assert manifest.vocab_name == "manifest-vocab"
    assert manifest.min_alert_level == "error"


def test_load_install_manifest_defaults_when_no_manifest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Defaults are used when archive lacks stilyagi.toml."""
    buffer = io.BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr("concordat-0.0.1/.vale.ini", "StylesPath = styles\n")

    download_called = False
    extract_called = False

    def _download(*_args: object, **_kwargs: object) -> bytes:
        nonlocal download_called
        download_called = True
        return buffer.getvalue()

    def _extract(_bytes: bytes) -> bytes | None:
        nonlocal extract_called
        extract_called = True
        return None

    monkeypatch.delenv("STILYAGI_SKIP_MANIFEST_DOWNLOAD", raising=False)
    monkeypatch.setattr(stilyagi_install, "_download_packages_archive", _download)
    monkeypatch.setattr(stilyagi_install, "_extract_stilyagi_toml", _extract)

    manifest = stilyagi_install._load_install_manifest(  # type: ignore[attr-defined]
        packages_url="https://example.test/archive.zip",
        default_style_name="concordat",
    )

    assert download_called is True
    assert extract_called is True
    assert manifest.style_name == "concordat"
    assert manifest.vocab_name == "concordat"
    assert manifest.min_alert_level == "warning"


def test_load_install_manifest_falls_back_on_download_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Download errors return the default manifest."""

    def _download_fail(*_args: object, **_kwargs: object) -> bytes:
        raise RuntimeError

    monkeypatch.delenv("STILYAGI_SKIP_MANIFEST_DOWNLOAD", raising=False)
    monkeypatch.setattr(stilyagi_install, "_download_packages_archive", _download_fail)

    manifest = stilyagi_install._load_install_manifest(  # type: ignore[attr-defined]
        packages_url="https://example.test/archive.zip",
        default_style_name="concordat",
    )

    assert manifest.style_name == "concordat"
    assert manifest.vocab_name == "concordat"
    assert manifest.min_alert_level == "warning"
