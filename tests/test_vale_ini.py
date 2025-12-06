"""Tests guarding the packaged .vale.ini defaults."""

from __future__ import annotations

from pathlib import Path


def test_vale_ini_contains_styles_path_before_vocab() -> None:
    """Ensure StylesPath is present and precedes Vocab in .vale.ini."""
    content = Path(".vale.ini").read_text(encoding="utf-8").splitlines()

    try:
        styles_idx = next(i for i, line in enumerate(content) if line.startswith("StylesPath"))
    except StopIteration as exc:  # pragma: no cover - explicit assertion below
        raise AssertionError("StylesPath entry missing from .vale.ini") from exc

    try:
        vocab_idx = next(i for i, line in enumerate(content) if line.startswith("Vocab"))
    except StopIteration as exc:  # pragma: no cover - explicit assertion below
        raise AssertionError("Vocab entry missing from .vale.ini") from exc

    assert styles_idx < vocab_idx, "StylesPath must precede Vocab in .vale.ini"
