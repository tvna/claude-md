"""Terminology boundary tests for client-side preflight hooks."""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.shard_preflight


ALLOWED_LAYER_25_PATHS: frozenset[Path] = frozenset()

SCANNED_ROOTS = (
    Path("scripts"),
    Path("tests"),
    Path("docs"),
)


def _scanned_files() -> list[Path]:
    files: list[Path] = []
    for root in SCANNED_ROOTS:
        if root.is_file():
            files.append(root)
            continue
        files.extend(
            path
            for path in root.rglob("*")
            if path.is_file()
            and path.suffix in {".py", ".md"}
            and path.name != "translations.json"
        )
    return sorted(set(files))


def test_layer_25_term_is_eliminated() -> None:
    layer_label = "Layer " + "2.5"
    mirror_label = "2" + ".5 mirror"
    offenders: list[str] = []
    for path in _scanned_files():
        text = path.read_text()
        if layer_label not in text and mirror_label not in text:
            continue
        if path in ALLOWED_LAYER_25_PATHS:
            continue
        offenders.append(str(path))

    assert offenders == []
