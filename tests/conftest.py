"""Pytest fixtures shared across Vale rule tests."""

from __future__ import annotations

import typing as typ
from pathlib import Path

import pytest
from valedate import Valedate

_REPO_ROOT = Path(__file__).resolve().parents[1]
_STYLES = _REPO_ROOT / "styles"

_VALE_INI = {
    "__root__": {"MinAlertLevel": "suggestion"},
    "[*.md]": {"BasedOnStyles": "concordat"},
}


@pytest.fixture
def concordat_vale() -> typ.Iterator[Valedate]:
    """Provide a Vale sandbox loaded with the concordat style."""
    with Valedate(_VALE_INI, styles=_STYLES) as env:
        yield env
