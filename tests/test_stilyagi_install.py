"""Unit tests for installing Concordat packages via stilyagi."""

from __future__ import annotations

import json
import typing as typ

from concordat_vale import stilyagi

if typ.TYPE_CHECKING:
    from pathlib import Path
    from urllib.request import Request

    import pytest


class _FakeResponse:
    """Minimal HTTP response stub for exercising release fetching."""

    def __init__(self, *, status: int, body: dict[str, typ.Any]) -> None:
        self._status = status
        self._payload = json.dumps(body).encode("utf-8")

    def read(self) -> bytes:  # pragma: no cover - exercised indirectly
        return self._payload

    def getcode(self) -> int:
        return self._status

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        _traceback: object,
    ) -> None:
        return None


def _fake_release(version: str, asset_url: str) -> dict[str, typ.Any]:
    """Return a GitHub-like release payload for the specified version."""
    return {
        "tag_name": f"v{version}",
        "assets": [
            {
                "name": f"concordat-{version}.zip",
                "browser_download_url": asset_url,
            }
        ],
    }


def test_fetch_latest_release_prefers_matching_zip() -> None:
    """Select the concordat ZIP asset and strip the tag prefix."""
    captured_headers: dict[str, str] = {}

    def fake_open(request: Request, timeout: int = 10) -> _FakeResponse:
        # Request objects flow through from urllib so we can inspect headers.
        accept_header = request.get_header("Accept") or ""
        auth_header = request.get_header("Authorization") or ""
        captured_headers.update(
            {
                "Accept": accept_header,
                "Authorization": auth_header,
            }
        )
        return _FakeResponse(
            status=200,
            body=_fake_release(
                version="9.9.9",
                asset_url="https://downloads.example/concordat-9.9.9.zip",
            ),
        )

    fake_token = "-".join(["test", "token"])
    release = stilyagi._fetch_latest_release(  # type: ignore[attr-defined]
        "acme/concordat",
        api_base="https://api.example",
        token=fake_token,
        opener=fake_open,
    )

    assert release.version == "9.9.9"
    assert release.asset_url.endswith("concordat-9.9.9.zip")
    assert captured_headers["Accept"].startswith("application/vnd.github+json")
    assert captured_headers["Authorization"] == f"Bearer {fake_token}"


def test_install_rewrites_ini_and_preserves_styles_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Rewrite .vale.ini with Concordat defaults while keeping StylesPath."""
    existing_ini = tmp_path / ".vale.ini"
    existing_ini.write_text(
        "StylesPath = .vale/styles\nMinAlertLevel = suggestion\n", encoding="utf-8"
    )

    monkeypatch.setattr(
        stilyagi,
        "_fetch_latest_release",
        lambda repo, api_base, token, opener=None: stilyagi.ReleaseInfo(  # type: ignore[attr-defined]
            tag="v1.2.3",
            version="1.2.3",
            asset_url="https://github.com/example/releases/download/v1.2.3/concordat-1.2.3.zip",
        ),
    )

    destination = stilyagi.install_styles(
        repo="example/concordat",
        config_path=existing_ini,
        api_base="https://api.example",
        styles_path=None,
        token=None,
    )

    body = destination.read_text(encoding="utf-8")
    assert body.startswith("StylesPath = .vale/styles\n")
    assert "MinAlertLevel = warning" in body
    assert (
        "Packages = https://github.com/example/releases/download/v1.2.3/concordat-1.2.3.zip"
        in body
    )
    assert "BasedOnStyles = concordat" in body
    assert "BlockIgnores = (?m)^\\[\\^\\d+\\]:" in body
    assert "concordat.Pronouns = NO" in body


def test_install_defaults_styles_path_when_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Use a hidden styles directory when no StylesPath is configured."""
    config_path = tmp_path / ".vale.ini"
    monkeypatch.setattr(
        stilyagi,
        "_fetch_latest_release",
        lambda repo, api_base, token, opener=None: stilyagi.ReleaseInfo(  # type: ignore[attr-defined]
            tag="v2.0.0",
            version="2.0.0",
            asset_url="https://example.invalid/concordat-2.0.0.zip",
        ),
    )

    stilyagi.install_styles(
        repo="acme/concordat",
        config_path=config_path,
        api_base="https://api.example",
        styles_path=None,
        token=None,
    )

    contents = config_path.read_text(encoding="utf-8")
    assert contents.splitlines()[0] == "StylesPath = .vale/styles"
    assert "Packages = https://example.invalid/concordat-2.0.0.zip" in contents
