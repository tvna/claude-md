"""Tests for ``scripts/auto_tag_version.py``.

Pure decision functions get parametrize cases; the subprocess boundary is
exercised via a fake ``runner`` injected through the ``runner`` kwarg the
production code already exposes, and the ``run`` subcommand is driven with the
git boundary monkeypatched. Refs #89.
"""

from __future__ import annotations

import subprocess
from typing import Any

import auto_tag_version as tagger
import pytest

pytestmark = pytest.mark.shard_ci_ops


# --------------------------------------------------------------------------
# pure decision functions
# --------------------------------------------------------------------------


def test_tag_name() -> None:
    assert tagger.tag_name((1, 1, 0)) == "v1.1.0"
    assert tagger.tag_name((0, 0, 1)) == "v0.0.1"


@pytest.mark.parametrize(
    ("base", "head", "expected"),
    [
        ((1, 0, 0), (1, 1, 0), "v1.1.0"),
        ((1, 0, 0), (2, 0, 0), "v2.0.0"),
        ((1, 2, 3), (1, 2, 4), "v1.2.4"),
        ((1, 0, 0), (1, 0, 0), None),  # unchanged -> no tag
    ],
)
def test_tag_for_change(
    base: tagger.Version, head: tagger.Version, expected: str | None
) -> None:
    assert tagger.tag_for_change(base, head) == expected


# --------------------------------------------------------------------------
# git boundary; fake runner
# --------------------------------------------------------------------------


def _fake_runner(responses: dict[str, str], *, record: list[str] | None = None):
    """Return a runner keyed by a substring of the git command.

    Records each joined command into *record* when provided so a test can
    assert which git mutations ran.
    """

    def runner(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        joined = " ".join(cmd)
        if record is not None:
            record.append(joined)
        for needle, stdout in responses.items():
            if needle in joined:
                return subprocess.CompletedProcess(cmd, 0, stdout=stdout, stderr="")
        raise AssertionError(f"unexpected command: {joined}")

    return runner


def test_read_version_at() -> None:
    runner = _fake_runner({"show": "version: 4.5.6\n"})
    assert tagger.read_version_at("HEAD", runner=runner) == (4, 5, 6)


def test_tag_exists_true_and_false() -> None:
    assert tagger.tag_exists(
        "v1.1.0", runner=_fake_runner({"tag --list": "v1.1.0\n"})
    )
    assert not tagger.tag_exists(
        "v1.1.0", runner=_fake_runner({"tag --list": ""})
    )
    # A prefix match must not count as an existing tag.
    assert not tagger.tag_exists(
        "v1.1.0", runner=_fake_runner({"tag --list": "v1.1.00\n"})
    )


def test_create_and_push_tag_runs_tag_then_push() -> None:
    record: list[str] = []
    runner = _fake_runner({"tag": "", "push": ""}, record=record)
    tagger.create_and_push_tag("v1.1.0", "abc123", "origin", runner=runner)
    assert record == ["git tag v1.1.0 abc123", "git push origin v1.1.0"]


# --------------------------------------------------------------------------
# run subcommand end-to-end (monkeypatched boundary)
# --------------------------------------------------------------------------


def _patch_versions(
    monkeypatch: pytest.MonkeyPatch, *, head: str, base: str
) -> None:
    def fake_read(ref: str, **k: Any) -> tagger.Version:
        # The merge SHA itself is the head; "<sha>^" is the first parent.
        return tagger.parse_version(base if ref.endswith("^") else head)

    monkeypatch.setattr(tagger, "read_version_at", fake_read)


def test_run_creates_tag_on_bump(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _patch_versions(monkeypatch, head="version: 1.1.0\n", base="version: 1.0.0\n")
    monkeypatch.setattr(tagger, "tag_exists", lambda *a, **k: False)
    pushed: list[tuple[str, str, str]] = []
    monkeypatch.setattr(
        tagger,
        "create_and_push_tag",
        lambda tag, sha, remote, **k: pushed.append((tag, sha, remote)),
    )
    rc = tagger.main(["run", "--merge-sha", "deadbeef"])
    out = capsys.readouterr().out
    assert rc == 0
    assert pushed == [("v1.1.0", "deadbeef", "origin")]
    assert "created and pushed tag v1.1.0" in out


def test_run_noop_when_version_unchanged(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _patch_versions(monkeypatch, head="version: 1.0.0\n", base="version: 1.0.0\n")
    called = False

    def _should_not_run(*a: Any, **k: Any) -> bool:
        nonlocal called
        called = True
        return False

    monkeypatch.setattr(tagger, "tag_exists", _should_not_run)
    rc = tagger.main(["run", "--merge-sha", "deadbeef"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "version unchanged" in out
    assert called is False


def test_run_idempotent_when_tag_exists(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _patch_versions(monkeypatch, head="version: 1.1.0\n", base="version: 1.0.0\n")
    monkeypatch.setattr(tagger, "tag_exists", lambda *a, **k: True)

    def _should_not_push(*a: Any, **k: Any) -> None:
        raise AssertionError("must not push when the tag already exists")

    monkeypatch.setattr(tagger, "create_and_push_tag", _should_not_push)
    rc = tagger.main(["run", "--merge-sha", "deadbeef"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "already exists" in out


def test_run_dry_run_pushes_nothing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _patch_versions(monkeypatch, head="version: 2.0.0\n", base="version: 1.0.0\n")
    monkeypatch.setattr(tagger, "tag_exists", lambda *a, **k: False)

    def _should_not_push(*a: Any, **k: Any) -> None:
        raise AssertionError("dry-run must not push")

    monkeypatch.setattr(tagger, "create_and_push_tag", _should_not_push)
    rc = tagger.main(["run", "--merge-sha", "deadbeef", "--dry-run"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "DRY-RUN: would create and push tag v2.0.0" in out


def test_run_git_failure_is_loud(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def boom(ref: str, **k: Any) -> tagger.Version:
        raise subprocess.CalledProcessError(128, ["git", "show"], stderr="bad")

    monkeypatch.setattr(tagger, "read_version_at", boom)
    rc = tagger.main(["run", "--merge-sha", "deadbeef"])
    err = capsys.readouterr().err
    assert rc == 1
    assert "could not read apm.yml version" in err


def test_resolve_merge_sha_prefers_flag_then_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MERGE_SHA", "fromenv")
    assert (
        tagger._resolve_merge_sha(argparse_ns(merge_sha="fromflag")) == "fromflag"
    )
    assert tagger._resolve_merge_sha(argparse_ns(merge_sha=None)) == "fromenv"
    monkeypatch.delenv("MERGE_SHA", raising=False)
    assert tagger._resolve_merge_sha(argparse_ns(merge_sha=None)) == "HEAD"


def argparse_ns(**kwargs: Any):
    import argparse

    return argparse.Namespace(**kwargs)
