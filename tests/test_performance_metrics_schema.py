"""Pin the benchmark-record schema documented in performance-metrics.md.

Issue #89: the benchmark record gains a human-readable
``compiled_source_version`` companion to the canonical ``compiled_source_sha``,
and ``schema_version`` bumps to ``"3"`` (the coordinated number recorded in
the PRD; ``"2"`` was reserved by #88, closed ``not_planned``). The schema is
design-only; it lives as a fenced ``json`` example in
``docs/standards/performance-metrics.md`` (the Phase 3 harness, #62, is not
yet implemented, so there is no runtime validator). Nothing cross-checked the
example, so a future edit could silently drop a required field or desync the
version.

These tests parse the schema's ``json`` code block (the fenced block that
declares ``schema_version``) and assert the contract the doc promises:

* the block is valid JSON;
* ``schema_version`` is exactly ``"3"`` (string, per the doc);
* both ``compiled_source_sha`` (canonical) and ``compiled_source_version``
  (human-readable companion) are present at the top level.

Refs #89, #86.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.shard_policy

REPO_ROOT = Path(__file__).resolve().parents[1]
METRICS_DOC = REPO_ROOT / "docs" / "standards" / "performance-metrics.md"

# Fenced ```json ... ``` blocks. Non-greedy body so each block is captured
# independently when the doc grows more than one.
_JSON_BLOCK_RE = re.compile(r"```json\n(.*?)\n```", re.DOTALL)


def _schema_record() -> dict[str, object]:
    """Return the parsed benchmark-record schema example from the doc.

    The schema is the fenced ``json`` block that declares ``schema_version``;
    selecting by content rather than by position keeps the test stable if the
    doc adds other ``json`` examples around it.
    """
    text = METRICS_DOC.read_text(encoding="utf-8")
    blocks = [b for b in _JSON_BLOCK_RE.findall(text) if '"schema_version"' in b]
    assert len(blocks) == 1, (
        f"expected exactly one json block declaring schema_version in "
        f"{METRICS_DOC.name}, found {len(blocks)}"
    )
    return json.loads(blocks[0])


def test_schema_block_is_valid_json() -> None:
    record = _schema_record()
    assert isinstance(record, dict)


def test_schema_version_is_three() -> None:
    record = _schema_record()
    assert record["schema_version"] == "3"


def test_record_keeps_sha_and_adds_version() -> None:
    record = _schema_record()
    # The SHA stays the canonical immutable key; the version is the
    # human-readable companion added by #89.
    assert "compiled_source_sha" in record
    assert "compiled_source_version" in record
