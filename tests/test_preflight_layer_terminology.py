"""Terminology boundary tests for client-side preflight hooks."""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.shard_preflight


ALLOWED_LAYER_25_PATHS = {
    Path("scripts/preflight_non_ascii.py"),
    Path("tests/test_preflight_non_ascii.py"),
    Path("docs/prd/non-ascii-defense.md"),
    Path("docs/prd/agent-rules-design-philosophy.md"),
}

SCANNED_ROOTS = (
    Path("scripts"),
    Path("tests"),
    Path("docs/standards/issue-pr-body-standard.md"),
    Path("docs/prd/non-ascii-defense.md"),
    Path("docs/prd/agent-rules-design-philosophy.md"),
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


def test_layer_25_term_stays_local_to_non_ascii_defense() -> None:
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
