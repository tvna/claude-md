"""Tests for ``scripts/_commit_signatures.py``.

Refs #1959.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import _commit_signatures as helper
import pytest

pytestmark = pytest.mark.shard_preflight


# A raw ``git cat-file commit`` body with an SSH signature header. The signature
# spans continuation lines (leading space), exactly as git emits it, so the
# header/message split (first blank line) must not be fooled by it.
_SIGNED_RAW = (
    "tree 5363ef9712e5e7be8b08c23db2a98682fe380c02\n"
    "parent 4316938dedea411c061ec9a2e732eb2ddaf6cad0\n"
    "author Dev <dev@example.com> 1782336345 +0000\n"
    "committer Dev <dev@example.com> 1782336345 +0000\n"
    "gpgsig -----BEGIN SSH SIGNATURE-----\n"
    " U1NIU0lHAAAAAQAAADMAAAALc3NoLWVkMjU1MTkAAAAg\n"
    " -----END SSH SIGNATURE-----\n"
    "\n"
    "feat: a signed thing\n\nbody line\n"
)

_UNSIGNED_RAW = (
    "tree 5363ef9712e5e7be8b08c23db2a98682fe380c02\n"
    "author Dev <dev@example.com> 1782336345 +0000\n"
    "committer Dev <dev@example.com> 1782336345 +0000\n"
    "\n"
    "wip: scratch\n"
)


# ---------------------------------------------------------------------------
# parse_commit_object (pure)
# ---------------------------------------------------------------------------


def test_parse_detects_ssh_signature_header() -> None:
    record = helper.parse_commit_object("a" * 40, _SIGNED_RAW)
    assert record.signed is True
    assert record.subject == "feat: a signed thing"
    assert record.acked is False


def test_parse_detects_unsigned_commit() -> None:
    record = helper.parse_commit_object("b" * 40, _UNSIGNED_RAW)
    assert record.signed is False
    assert record.subject == "wip: scratch"


def test_parse_marks_acked_when_marker_in_message() -> None:
    raw = _UNSIGNED_RAW.replace("wip: scratch\n", "wip: scratch\n\nunsigned-ack: throwaway\n")
    record = helper.parse_commit_object("c" * 40, raw)
    assert record.acked is True


def test_parse_signature_body_does_not_leak_into_subject() -> None:
    # The multi-line signature must not be mistaken for the message: the subject
    # is the first message line after the blank separator, not a signature line.
    record = helper.parse_commit_object("d" * 40, _SIGNED_RAW)
    assert "SSH SIGNATURE" not in record.subject


# ---------------------------------------------------------------------------
# select_unsigned (pure)
# ---------------------------------------------------------------------------


def _sig(*, signed: bool, acked: bool = False) -> helper.CommitSignature:
    return helper.CommitSignature(sha="x" * 40, signed=signed, subject="s", acked=acked)


def test_select_unsigned_flags_only_unsigned() -> None:
    records = [_sig(signed=True), _sig(signed=False)]
    unsigned = helper.select_unsigned(records)
    assert len(unsigned) == 1
    assert unsigned[0].signed is False


def test_select_unsigned_skips_acked() -> None:
    records = [_sig(signed=False, acked=True), _sig(signed=False)]
    assert len(helper.select_unsigned(records)) == 1


def test_signed_commit_is_never_flagged() -> None:
    # The key regression guard: a signed commit (even one git's %G? would report
    # as N for lack of an allowed-signers file) must NOT be treated as unsigned.
    assert helper.select_unsigned([_sig(signed=True)]) == []


# ---------------------------------------------------------------------------
# Integration against a real repo (unsigned commits carry no gpgsig header)
# ---------------------------------------------------------------------------


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "commit.gpgsign=false", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")
    return repo


def _commit(repo: Path, name: str, message: str = "commit") -> None:
    (repo / name).write_text(name, encoding="utf-8")
    _git(repo, "add", name)
    _git(repo, "commit", "-m", message)


def test_list_signatures_detects_unsigned_commit(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _commit(repo, "a.txt")
    records = helper.list_signatures(repo, ["--max-count=1", "HEAD"])
    assert len(records) == 1
    assert records[0].signed is False
    assert helper.select_unsigned(records)


def test_list_signatures_over_range(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _commit(repo, "base.txt")
    _git(repo, "switch", "-c", "feature")
    _commit(repo, "f1.txt", message="first feature commit")
    _commit(repo, "f2.txt", message="second\n\nunsigned-ack: intentional")
    records = helper.list_signatures(repo, ["main..HEAD"])
    assert len(records) == 2  # base.txt excluded by the range
    unsigned = helper.select_unsigned(records)
    # Both are unsigned; the acked one is excluded from the flagged set.
    assert len(unsigned) == 1
    assert unsigned[0].subject == "first feature commit"


def test_list_signatures_raises_on_git_error(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _commit(repo, "a.txt")
    with pytest.raises(RuntimeError):
        helper.list_signatures(repo, ["does-not-exist..HEAD"])


def test_resolve_base_returns_first_resolving_ref(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _commit(repo, "a.txt")
    assert helper.resolve_base(repo, ("origin/main", "main")) == "main"
    assert helper.resolve_base(repo, ("origin/main", "nope")) is None
