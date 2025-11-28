"""Ensure the package exposes only the public surface we expect."""

from __future__ import annotations

import importlib
import types


def test_public_api_surface_is_empty() -> None:
    """`concordat_vale` should not export stilyagi symbols anymore."""
    module = importlib.import_module("concordat_vale")

    assert isinstance(module, types.ModuleType), (
        "concordat_vale should import as a module"
    )
    assert hasattr(module, "__all__"), (
        "concordat_vale.__all__ must exist to define the public surface explicitly"
    )
    assert module.__all__ == [], "concordat_vale must not export any public symbols"
    assert not hasattr(module, "stilyagi"), (
        "concordat_vale must not expose the legacy stilyagi entrypoint"
    )
