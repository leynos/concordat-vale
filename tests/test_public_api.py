"""Ensure the package exposes only the public surface we expect."""

from __future__ import annotations

import importlib
import types


def test_public_api_surface_is_empty() -> None:
    """`concordat_vale` should not export stilyagi symbols anymore."""
    module = importlib.import_module("concordat_vale")

    assert isinstance(module, types.ModuleType)
    assert getattr(module, "__all__", []) == []
    assert not hasattr(module, "stilyagi")
