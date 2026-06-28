"""Tests for scripts/_pr_commit_batch.py payload batching.

Refs #1578. The single createCommitOnBranch mutation overflowed on a large
generated-docs backlog; these cover the batch splitter and the chained-commit
publisher that fixes it, plus the unchanged single-commit path for small
payloads. The ``_create_commit_on_branch`` primitive itself is covered in
tests/test_pr_upsert.py (TestCreateCommitOnBranch, via the _pr_commit_batch
alias).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import _pr_commit_batch as pcb

pytestmark = pytest.mark.shard_ci_ops


def _addition(path: str, contents: str) -> dict[str, str]:
    """A createCommitOnBranch addition entry (contents already base64-shaped)."""
    return {"path": path, "contents": contents}


class _RecordingGraphql:
    """Record mutation variables and return a fixed commit oid each call."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def graphql_call(self, *, query: str, variables: dict[str, Any], token: str) -> tuple[int, dict[str, Any]]:
        self.calls.append(variables)
        return 200, {"data": {"createCommitOnBranch": {"commit": {"oid": "newoid"}}}}


class TestBatchAdditions:
    def test_empty_yields_no_batches(self) -> None:
        assert pcb._batch_additions([]) == []

    def test_splits_on_file_count(self) -> None:
        items = [_addition(f"f{i}", "x") for i in range(5)]
        batches = pcb._batch_additions(items, max_files=2, max_bytes=10_000)
        assert [len(b) for b in batches] == [2, 2, 1]
        # Order is preserved and no entry is dropped.
        assert [e["path"] for b in batches for e in b] == [f"f{i}" for i in range(5)]

    def test_splits_on_cumulative_size(self) -> None:
        items = [_addition(f"f{i}", "abcd") for i in range(4)]  # 4 bytes each
        batches = pcb._batch_additions(items, max_files=99, max_bytes=8)
        assert [len(b) for b in batches] == [2, 2]

    def test_single_oversized_file_is_its_own_batch(self) -> None:
        items = [_addition("big", "x" * 100), _addition("small", "y")]
        batches = pcb._batch_additions(items, max_files=99, max_bytes=10)
        # The oversized file never produces an empty batch; it stands alone.
        assert [[e["path"] for e in b] for b in batches] == [["big"], ["small"]]


class TestCreateCommitsInBatches:
    def test_single_batch_keeps_headline_and_carries_deletions(self) -> None:
        gql = _RecordingGraphql()
        additions = [_addition("a", "x"), _addition("b", "y")]
        deletions = [{"path": "gone"}]
        final = pcb._create_commits_in_batches(
            repo="o/r", branch="chore/x", start_oid="base", headline="subject",
            body="Refs #1", additions=additions, deletions=deletions, token="tok",
            graphql_call=gql.graphql_call, max_files=40, max_bytes=999_999,
        )
        assert final == "newoid"
        assert len(gql.calls) == 1
        assert gql.calls[0]["input"]["message"]["headline"] == "subject"  # no (batch) suffix
        assert gql.calls[0]["input"]["expectedHeadOid"] == "base"
        assert gql.calls[0]["input"]["fileChanges"]["deletions"] == deletions

    def test_multi_batch_chains_oid_and_deletes_only_first(self) -> None:
        gql = _RecordingGraphql()
        additions = [_addition(f"f{i}", "x") for i in range(3)]
        deletions = [{"path": "gone"}]
        pcb._create_commits_in_batches(
            repo="o/r", branch="chore/x", start_oid="base", headline="subject",
            body="Refs #1", additions=additions, deletions=deletions, token="tok",
            graphql_call=gql.graphql_call, max_files=2, max_bytes=999_999,
        )
        assert len(gql.calls) == 2
        # expectedHeadOid chains: first off base, second off the first commit oid.
        assert gql.calls[0]["input"]["expectedHeadOid"] == "base"
        assert gql.calls[1]["input"]["expectedHeadOid"] == "newoid"
        # Deletions ride only the first commit.
        assert gql.calls[0]["input"]["fileChanges"]["deletions"] == deletions
        assert "deletions" not in gql.calls[1]["input"]["fileChanges"]
        # Headlines are suffixed for traceability.
        assert gql.calls[0]["input"]["message"]["headline"] == "subject (batch 1/2)"
        assert gql.calls[1]["input"]["message"]["headline"] == "subject (batch 2/2)"

    def test_pure_deletion_makes_one_commit(self) -> None:
        # No additions but a deletion: a single commit with empty additions and
        # the deletion, so a removal-only drift still publishes.
        gql = _RecordingGraphql()
        pcb._create_commits_in_batches(
            repo="o/r", branch="chore/x", start_oid="base", headline="subject",
            body="", additions=[], deletions=[{"path": "gone"}], token="tok",
            graphql_call=gql.graphql_call,
        )
        assert len(gql.calls) == 1
        assert gql.calls[0]["input"]["fileChanges"]["additions"] == []
        assert gql.calls[0]["input"]["fileChanges"]["deletions"] == [{"path": "gone"}]
