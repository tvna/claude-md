"""Tests for scripts/session_set_origin_head.py.

Refs #2080. The SessionStart hook makes ``refs/remotes/origin/HEAD``
resolvable so ``git diff origin/HEAD...HEAD`` (the default review range of
the ``/security-review`` and ``/code-review`` slash commands) stops failing
with ``fatal: ambiguous argument 'origin/HEAD...'`` on a fresh clone.

These tests drive the branch logic through an injected fake git runner, so
the three required behaviours; set when absent, no-op when present, and
soft-fail when ``origin/main`` is missing; are exercised without a real
repository.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable

import pytest
import session_set_origin_head as subject

pytestmark = pytest.mark.shard_preflight

_ORIGIN_HEAD = "refs/remotes/origin/HEAD"
_ORIGIN_MAIN = "refs/remotes/origin/main"


def _proc(returncode: int) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout="", stderr="")


class _FakeGit:
    """A git runner with scripted return codes keyed by intent.

    ``head_resolves`` controls ``rev-parse --verify --quiet <HEAD>`` (the
    idempotence probe: does origin/HEAD resolve to a commit), ``main_exists``
    controls ``show-ref --verify --quiet <main>``, and ``set_ok`` controls
    the ``symbolic-ref <HEAD> <main>`` write. Every invocation is recorded so
    a test can assert the write happened (or did not).
    """

    def __init__(self, *, head_resolves: bool, main_exists: bool, set_ok: bool = True) -> None:
        self.head_resolves = head_resolves
        self.main_exists = main_exists
        self.set_ok = set_ok
        self.calls: list[list[str]] = []

    def __call__(self, args: list[str]) -> subprocess.CompletedProcess[str]:
        self.calls.append(args)
        if args[:1] == ["rev-parse"]:
            # The idempotence probe: resolves to a commit (0) or not (absent
            # or dangling symref -> non-zero).
            return _proc(0 if self.head_resolves else 1)
        if args[:1] == ["show-ref"]:
            return _proc(0 if self.main_exists else 1)
        if args[:1] == ["symbolic-ref"]:
            # Only the write form reaches the runner now; it overwrites any
            # stale target.
            return _proc(0 if self.set_ok else 1)
        raise AssertionError(f"unexpected git invocation: {args}")

    def wrote_head(self) -> bool:
        return [_ORIGIN_HEAD, _ORIGIN_MAIN] in [a[-2:] for a in self.calls if a[:1] == ["symbolic-ref"]]


def _raising(_args: list[str]) -> subprocess.CompletedProcess[str]:
    raise RuntimeError("git executable not found on PATH")


# --- configure(): the three required behaviours -----------------------------


def test_configure_noop_when_origin_head_already_resolves() -> None:
    """Idempotent: a settled ref is a silent no-op and never rewrites."""
    git = _FakeGit(head_resolves=True, main_exists=True)
    assert subject.configure(git) is None
    assert not git.wrote_head()


def test_configure_sets_head_when_absent_and_main_present() -> None:
    git = _FakeGit(head_resolves=False, main_exists=True, set_ok=True)
    output = subject.configure(git)
    assert git.wrote_head()
    assert output is not None
    msg = output["hookSpecificOutput"]["additionalContext"]
    assert _ORIGIN_HEAD in msg
    assert _ORIGIN_MAIN in msg
    assert "WARNING" not in msg


def test_configure_resets_dangling_symref() -> None:
    """A dangling origin/HEAD (does not resolve) is repaired, not no-oped.

    Regression for the Codex review on PR #2101: `git symbolic-ref --quiet`
    returns 0 for a symref whose target was pruned, so the old probe would
    no-op while `git diff origin/HEAD...HEAD` still failed. The rev-parse
    probe treats a non-resolving ref as needing repair.
    """
    git = _FakeGit(head_resolves=False, main_exists=True, set_ok=True)
    output = subject.configure(git)
    assert git.wrote_head()  # re-pointed at origin/main, overwriting the stale target
    assert output is not None
    assert "WARNING" not in output["hookSpecificOutput"]["additionalContext"]


def test_configure_probe_uses_rev_parse_verify() -> None:
    """The idempotence probe checks resolution, not mere symref existence."""
    git = _FakeGit(head_resolves=True, main_exists=True)
    subject.configure(git)
    assert git.calls[0] == ["rev-parse", "--verify", "--quiet", _ORIGIN_HEAD]


def test_configure_soft_fails_when_origin_main_missing() -> None:
    """Missing origin/main (or non-git cwd) warns, never aborts, never writes."""
    git = _FakeGit(head_resolves=False, main_exists=False)
    output = subject.configure(git)
    assert not git.wrote_head()
    assert output is not None
    msg = output["hookSpecificOutput"]["additionalContext"]
    assert msg.startswith("WARNING")
    assert _ORIGIN_MAIN in msg


def test_configure_warns_when_symbolic_ref_write_fails() -> None:
    git = _FakeGit(head_resolves=False, main_exists=True, set_ok=False)
    output = subject.configure(git)
    assert output is not None
    msg = output["hookSpecificOutput"]["additionalContext"]
    assert msg.startswith("WARNING")
    assert "could not set" in msg


def test_configure_soft_fails_when_git_runner_raises() -> None:
    """A missing git binary degrades to the soft-fail warning, not a crash."""
    output = subject.configure(_raising)
    assert output is not None
    assert output["hookSpecificOutput"]["additionalContext"].startswith("WARNING")


# --- predicate helpers ------------------------------------------------------


def test_origin_head_resolves_reads_returncode() -> None:
    assert subject.origin_head_resolves(_FakeGit(head_resolves=True, main_exists=False)) is True
    assert subject.origin_head_resolves(_FakeGit(head_resolves=False, main_exists=False)) is False


def test_origin_main_exists_reads_returncode() -> None:
    assert subject.origin_main_exists(_FakeGit(head_resolves=False, main_exists=True)) is True
    assert subject.origin_main_exists(_FakeGit(head_resolves=False, main_exists=False)) is False


def test_helpers_swallow_runtime_error() -> None:
    assert subject.origin_head_resolves(_raising) is False
    assert subject.origin_main_exists(_raising) is False
    assert subject.set_origin_head(_raising) is False


def test_set_origin_head_issues_expected_argv() -> None:
    git = _FakeGit(head_resolves=False, main_exists=True, set_ok=True)
    assert subject.set_origin_head(git) is True
    assert git.calls[-1] == ["symbolic-ref", _ORIGIN_HEAD, _ORIGIN_MAIN]


# --- main(): fail-soft entry point ------------------------------------------


def test_main_prints_context_when_set(capsys: pytest.CaptureFixture[str]) -> None:
    fake: Callable[[list[str]], subprocess.CompletedProcess[str]] = _FakeGit(
        head_resolves=False, main_exists=True, set_ok=True
    )
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(subject, "run_git", fake)
        subject.main()
    out = capsys.readouterr().out
    assert _ORIGIN_HEAD in out


def test_main_silent_on_noop(capsys: pytest.CaptureFixture[str]) -> None:
    fake: Callable[[list[str]], subprocess.CompletedProcess[str]] = _FakeGit(
        head_resolves=True, main_exists=True
    )
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(subject, "run_git", fake)
        subject.main()
    assert capsys.readouterr().out == ""
