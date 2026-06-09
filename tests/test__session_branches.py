"""Tests for scripts/_session_branches.py.

Refs #1513, #1181, #785. The module holds the persisted format and the
authorization predicate shared by the session-branch gates: an empty/absent
file is the empty set (fail-open), a legacy single line is a valid
one-element set, a protected branch is never authorized even if present,
and appends de-duplicate and fail open on a write error.
"""

from __future__ import annotations

from pathlib import Path

import _session_branches as subject
import pytest

pytestmark = pytest.mark.shard_preflight


# ---------------------------------------------------------------------------
# read_authorized_set
# ---------------------------------------------------------------------------


class TestReadAuthorizedSet:
    def test_missing_file_is_empty_set(self, tmp_path: Path) -> None:
        assert subject.read_authorized_set(tmp_path / "MISSING") == set()

    def test_empty_file_is_empty_set(self, tmp_path: Path) -> None:
        f = tmp_path / "lock"
        f.write_text("  \n\n")
        assert subject.read_authorized_set(f) == set()

    def test_legacy_single_line_is_one_element_set(self, tmp_path: Path) -> None:
        f = tmp_path / "lock"
        f.write_text("claude/legacy-branch\n")
        assert subject.read_authorized_set(f) == {"claude/legacy-branch"}

    def test_multi_line_is_deduped_set(self, tmp_path: Path) -> None:
        f = tmp_path / "lock"
        f.write_text("claude/a\nclaude/b\nclaude/a\n")
        assert subject.read_authorized_set(f) == {"claude/a", "claude/b"}


# ---------------------------------------------------------------------------
# append_branch
# ---------------------------------------------------------------------------


class TestAppendBranch:
    def test_appends_new_branch(self, tmp_path: Path) -> None:
        f = tmp_path / "lock"
        f.write_text("claude/a\n")
        subject.append_branch(f, "claude/b")
        assert subject.read_authorized_set(f) == {"claude/a", "claude/b"}

    def test_creates_file_when_absent(self, tmp_path: Path) -> None:
        f = tmp_path / "lock"
        subject.append_branch(f, "claude/a")
        assert subject.read_authorized_set(f) == {"claude/a"}

    def test_duplicate_is_noop(self, tmp_path: Path) -> None:
        f = tmp_path / "lock"
        f.write_text("claude/a\n")
        subject.append_branch(f, "claude/a")
        assert f.read_text() == "claude/a\n"

    def test_blank_branch_is_noop(self, tmp_path: Path) -> None:
        f = tmp_path / "lock"
        f.write_text("claude/a\n")
        subject.append_branch(f, "  ")
        assert subject.read_authorized_set(f) == {"claude/a"}

    def test_unwritable_path_fails_open(self, tmp_path: Path) -> None:
        # Parent directory does not exist -> OSError on open, suppressed.
        bad = tmp_path / "nonexistent_dir" / "lock"
        subject.append_branch(bad, "claude/a")  # must not raise
        assert subject.read_authorized_set(bad) == set()


# ---------------------------------------------------------------------------
# is_authorized
# ---------------------------------------------------------------------------


class TestIsAuthorized:
    def test_empty_set_authorizes_nothing(self) -> None:
        assert subject.is_authorized("claude/a", set()) is False

    def test_member_is_authorized(self) -> None:
        assert subject.is_authorized("claude/a", {"claude/a", "claude/b"}) is True

    def test_non_member_is_unauthorized(self) -> None:
        # A prior session's branch never added to the set stays blocked.
        assert subject.is_authorized("claude/prior", {"claude/a"}) is False

    def test_protected_branch_never_authorized_even_if_present(self) -> None:
        for protected in subject.PROTECTED:
            assert subject.is_authorized(protected, {protected, "claude/a"}) is False

    def test_none_or_empty_branch_is_unauthorized(self) -> None:
        assert subject.is_authorized(None, {"claude/a"}) is False
        assert subject.is_authorized("", {"claude/a"}) is False
