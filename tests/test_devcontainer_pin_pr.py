"""Tests for ``scripts/devcontainer_pin_pr.py``.

The ``scripts/`` directory is added to ``sys.path`` via the ``pythonpath``
key under ``[tool.pytest.ini_options]`` in ``pyproject.toml``.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import devcontainer_pin_pr as dpp
import pytest

pytestmark = pytest.mark.shard_ci_ops


class _FakeGit:
    """Stand-in for ``run_git``: returns a configurable returncode per subcommand.

    ``rc_map`` maps the first git arg (e.g. ``"diff"``) to a returncode;
    unmapped subcommands return 0. When ``raise_on`` matches a subcommand and
    ``check`` is set, a CalledProcessError is raised (mirrors ``check=True``).
    """

    def __init__(self, rc_map: dict[str, int] | None = None, raise_on: str | None = None) -> None:
        self.rc_map = rc_map or {}
        self.raise_on = raise_on
        self.calls: list[list[str]] = []

    def __call__(self, args: list[str], *, check: bool = False, **_: Any) -> subprocess.CompletedProcess[str]:
        self.calls.append(args)
        sub = args[0]
        if check and self.raise_on == sub:
            raise subprocess.CalledProcessError(1, ["git", *args])
        return subprocess.CompletedProcess(["git", *args], self.rc_map.get(sub, 0))

    def ran(self, sub: str) -> bool:
        return any(c[0] == sub for c in self.calls)


def _template(tmp_path: Path) -> Path:
    p = tmp_path / "tmpl.md"
    p.write_text("Pinned to __GITHUB_SHA__ now.\n", encoding="utf-8")
    return p


def _open_argv(tmp_path: Path, *, sha: str = "abc123") -> list[str]:
    return [
        "open",
        "--github-sha",
        sha,
        "--base",
        "main",
        "--title",
        "fix(devcontainer): pin published agent images",
        "--commit-subject",
        "fix(devcontainer): pin published agent images",
        "--commit-trailer",
        "Refs #696",
        "--template",
        str(_template(tmp_path)),
        "--file",
        ".devcontainer/claude/devcontainer.json",
        "--file",
        "docs/runbooks/devcontainers.md",
    ]


@pytest.fixture
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GH_TOKEN", "tok")
    monkeypatch.setenv("REPO", "owner/repo")


# ---------------------------------------------------------------------------
# render_pr_body
# ---------------------------------------------------------------------------


class TestRenderPrBody:
    def test_substitutes_all_occurrences(self) -> None:
        out = dpp.render_pr_body("a __GITHUB_SHA__ b __GITHUB_SHA__", "deadbeef")
        assert out == "a deadbeef b deadbeef"

    def test_no_placeholder_is_passthrough(self) -> None:
        assert dpp.render_pr_body("no marker", "x") == "no marker"


# ---------------------------------------------------------------------------
# _cmd_open guards
# ---------------------------------------------------------------------------


class TestGuards:
    def test_missing_token_returns_1(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("GH_TOKEN", raising=False)
        assert dpp.main(_open_argv(tmp_path)) == 1

    def test_missing_repo_returns_1(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GH_TOKEN", "tok")
        monkeypatch.delenv("REPO", raising=False)
        assert dpp.main(_open_argv(tmp_path)) == 1


# ---------------------------------------------------------------------------
# _cmd_open flow
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("_env")
class TestOpenFlow:
    def test_no_changes_returns_0(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(dpp, "run_git", _FakeGit({"diff": 0}))
        rc = dpp.main(_open_argv(tmp_path, sha="sha1"))
        assert rc == 0
        assert "already match sha1" in capsys.readouterr().out

    def test_branch_exists_with_open_pr_enables_and_exits(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(dpp, "run_git", _FakeGit({"diff": 1, "ls-remote": 0}))
        monkeypatch.setattr(dpp, "_list_open_prs", lambda **kw: [{"number": 5}])
        enabled: list[int] = []
        monkeypatch.setattr(dpp, "_enable_auto_merge", lambda **kw: enabled.append(kw["pr_number"]))
        upserted: list[Any] = []

        def _record_upsert(**kw: Any) -> tuple[str, int]:
            upserted.append(kw)
            return ("created", 99)

        monkeypatch.setattr(dpp, "_upsert_pr", _record_upsert)
        rc = dpp.main(_open_argv(tmp_path))
        assert rc == 0
        assert enabled == [5]
        assert upserted == []  # existing PR short-circuits before upsert

    def test_branch_exists_without_pr_falls_through_to_upsert(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        git = _FakeGit({"diff": 1, "ls-remote": 0})
        monkeypatch.setattr(dpp, "run_git", git)
        monkeypatch.setattr(dpp, "_list_open_prs", lambda **kw: [])
        monkeypatch.setattr(dpp, "_upsert_pr", lambda **kw: ("created", 7))
        enabled: list[int] = []
        monkeypatch.setattr(dpp, "_enable_auto_merge", lambda **kw: enabled.append(kw["pr_number"]))
        rc = dpp.main(_open_argv(tmp_path))
        assert rc == 0
        assert enabled == [7]
        assert not git.ran("commit")  # branch already existed; no new commit

    def test_branch_absent_creates_branch_then_upserts(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        git = _FakeGit({"diff": 1, "ls-remote": 2})  # ls-remote --exit-code: 2 == no match
        monkeypatch.setattr(dpp, "run_git", git)
        captured: dict[str, Any] = {}

        def _record_upsert(**kw: Any) -> tuple[str, int]:
            captured.update(kw)
            return ("created", 8)

        monkeypatch.setattr(dpp, "_upsert_pr", _record_upsert)
        monkeypatch.setattr(dpp, "_enable_auto_merge", lambda **kw: None)
        rc = dpp.main(_open_argv(tmp_path, sha="zz"))
        assert rc == 0
        assert git.ran("commit") and git.ran("push") and git.ran("checkout")
        assert captured["head"] == "codex/devcontainer-image-pins-zz"
        assert "zz" in captured["body"]  # template placeholder substituted

    def test_create_branch_git_failure_returns_1(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(dpp, "run_git", _FakeGit({"diff": 1, "ls-remote": 2}, raise_on="commit"))
        rc = dpp.main(_open_argv(tmp_path))
        assert rc == 1

    def test_list_open_prs_error_returns_1(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(dpp, "run_git", _FakeGit({"diff": 1, "ls-remote": 0}))

        def _boom(**kw: Any) -> list[dict[str, Any]]:
            raise RuntimeError("List PRs failed")

        monkeypatch.setattr(dpp, "_list_open_prs", _boom)
        assert dpp.main(_open_argv(tmp_path)) == 1

    def test_unreadable_template_returns_1(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(dpp, "run_git", _FakeGit({"diff": 1, "ls-remote": 0}))
        monkeypatch.setattr(dpp, "_list_open_prs", lambda **kw: [])
        argv = _open_argv(tmp_path)
        argv[argv.index("--template") + 1] = str(tmp_path / "missing.md")
        assert dpp.main(argv) == 1

    def test_upsert_error_returns_1(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(dpp, "run_git", _FakeGit({"diff": 1, "ls-remote": 0}))
        monkeypatch.setattr(dpp, "_list_open_prs", lambda **kw: [])

        def _boom(**kw: Any) -> tuple[str, int]:
            raise RuntimeError("Create PR failed")

        monkeypatch.setattr(dpp, "_upsert_pr", _boom)
        assert dpp.main(_open_argv(tmp_path)) == 1

    def test_auto_merge_failure_is_a_warning_not_fatal(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(dpp, "run_git", _FakeGit({"diff": 1, "ls-remote": 0}))
        monkeypatch.setattr(dpp, "_list_open_prs", lambda **kw: [])
        monkeypatch.setattr(dpp, "_upsert_pr", lambda **kw: ("created", 12))

        def _boom(**kw: Any) -> None:
            raise RuntimeError("automerge denied")

        monkeypatch.setattr(dpp, "_enable_auto_merge", _boom)
        rc = dpp.main(_open_argv(tmp_path))
        assert rc == 0
        assert "auto-merge request failed for PR #12" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# _parse_published_sha
# ---------------------------------------------------------------------------

_PUBLISHED = "b417e5833394f6f04a6e9b1eefe48026c09b4089"


class TestParsePublishedSha:
    def test_original_branch(self) -> None:
        assert dpp._parse_published_sha(f"codex/devcontainer-image-pins-{_PUBLISHED}") == _PUBLISHED

    def test_refreshed_branch_strips_suffix(self) -> None:
        branch = f"codex/devcontainer-image-pins-{_PUBLISHED}-r-0123456789ab"
        assert dpp._parse_published_sha(branch) == _PUBLISHED

    def test_unrelated_branch_returns_none(self) -> None:
        assert dpp._parse_published_sha("claude/some-feature") is None
        assert dpp._parse_published_sha("codex/devcontainer-image-pins-NOTHEX") is None


# ---------------------------------------------------------------------------
# _cmd_refresh flow
# ---------------------------------------------------------------------------

_TARGET = "0011223344556677889900aabbccddeeff001122"


def _refresh_argv(tmp_path: Path, *, target: str = _TARGET) -> list[str]:
    return [
        "refresh",
        "--base",
        "main",
        "--target-sha",
        target,
        "--title",
        "fix(devcontainer): pin published agent images",
        "--commit-subject",
        "fix(devcontainer): pin published agent images",
        "--commit-trailer",
        "Refs #696",
        "--template",
        str(_template(tmp_path)),
        "--file",
        ".devcontainer/claude/devcontainer.json",
        "--file",
        "docs/runbooks/devcontainers.md",
    ]


def _open_pin_pr(number: int = 1132, *, sha: str = _PUBLISHED, suffix: str = "") -> dict[str, Any]:
    ref = f"codex/devcontainer-image-pins-{sha}{suffix}"
    return {"number": number, "head": {"ref": ref}}


@pytest.mark.usefixtures("_env")
class TestRefreshFlow:
    def test_no_open_pr_is_noop(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(dpp, "_list_open_prs_by_prefix", lambda **kw: [])
        rc = dpp.main(_refresh_argv(tmp_path))
        assert rc == 0
        assert "nothing to refresh" in capsys.readouterr().out

    def test_unparseable_branch_returns_1(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            dpp, "_list_open_prs_by_prefix", lambda **kw: [{"number": 9, "head": {"ref": "codex/odd"}}]
        )
        assert dpp.main(_refresh_argv(tmp_path)) == 1

    def test_up_to_date_pr_only_requests_auto_merge(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(dpp, "_list_open_prs_by_prefix", lambda **kw: [_open_pin_pr(1132)])
        monkeypatch.setattr(dpp, "_compare_behind", lambda **kw: 0)
        enabled: list[int] = []
        monkeypatch.setattr(dpp, "_enable_auto_merge", lambda **kw: enabled.append(kw["pr_number"]))
        regen: list[str] = []

        def _regen(sha: str) -> int:
            regen.append(sha)
            return 0

        monkeypatch.setattr(dpp, "_regenerate_pins", _regen)
        rc = dpp.main(_refresh_argv(tmp_path))
        assert rc == 0
        assert enabled == [1132]
        assert regen == []  # no rebase work when already up to date

    def test_behind_with_changes_supersedes_old_pr(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        git = _FakeGit({"diff": 1, "ls-remote": 2})  # changes present; refresh branch absent
        monkeypatch.setattr(dpp, "run_git", git)
        monkeypatch.setattr(dpp, "_list_open_prs_by_prefix", lambda **kw: [_open_pin_pr(1132)])
        monkeypatch.setattr(dpp, "_compare_behind", lambda **kw: 3)
        monkeypatch.setattr(dpp, "_regenerate_pins", lambda sha: 0)
        captured: dict[str, Any] = {}

        def _record_upsert(**kw: Any) -> tuple[str, int]:
            captured.update(kw)
            return ("created", 1140)

        monkeypatch.setattr(dpp, "_upsert_pr", _record_upsert)
        enabled: list[int] = []
        monkeypatch.setattr(dpp, "_enable_auto_merge", lambda **kw: enabled.append(kw["pr_number"]))
        comments: list[tuple[int, str]] = []
        monkeypatch.setattr(dpp, "_comment_pr", lambda **kw: comments.append((kw["number"], kw["body"])))
        closed: list[int] = []
        monkeypatch.setattr(dpp, "_close_pr", lambda **kw: closed.append(kw["number"]))
        deleted: list[str] = []
        monkeypatch.setattr(dpp, "_delete_branch", lambda **kw: deleted.append(kw["branch"]))

        rc = dpp.main(_refresh_argv(tmp_path))
        assert rc == 0
        expected_branch = f"codex/devcontainer-image-pins-{_PUBLISHED}-r-{_TARGET[:12]}"
        assert captured["head"] == expected_branch
        assert _PUBLISHED in captured["body"]  # template substituted with the published SHA
        assert git.ran("commit") and git.ran("push")
        assert enabled == [1140]
        assert closed == [1132]
        assert deleted == [f"codex/devcontainer-image-pins-{_PUBLISHED}"]
        assert comments and comments[0][0] == 1132 and "Superseded by #1140" in comments[0][1]

    def test_behind_but_pins_already_on_main_closes_redundant_pr(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(dpp, "run_git", _FakeGit({"diff": 0}))  # regen produced no diff
        monkeypatch.setattr(dpp, "_list_open_prs_by_prefix", lambda **kw: [_open_pin_pr(1132)])
        monkeypatch.setattr(dpp, "_compare_behind", lambda **kw: 2)
        monkeypatch.setattr(dpp, "_regenerate_pins", lambda sha: 0)
        upserts: list[Any] = []

        def _record_upsert(**kw: Any) -> tuple[str, int]:
            upserts.append(kw)
            return ("created", 0)

        monkeypatch.setattr(dpp, "_upsert_pr", _record_upsert)
        monkeypatch.setattr(dpp, "_comment_pr", lambda **kw: None)
        closed: list[int] = []
        monkeypatch.setattr(dpp, "_close_pr", lambda **kw: closed.append(kw["number"]))
        monkeypatch.setattr(dpp, "_delete_branch", lambda **kw: None)
        rc = dpp.main(_refresh_argv(tmp_path))
        assert rc == 0
        assert closed == [1132]
        assert upserts == []  # no replacement PR when pins already match main

    def test_already_refreshed_onto_target_is_noop(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The open PR already sits on the refresh branch for this target SHA.
        pr = _open_pin_pr(1140, suffix=f"-r-{_TARGET[:12]}")
        monkeypatch.setattr(dpp, "_list_open_prs_by_prefix", lambda **kw: [pr])
        monkeypatch.setattr(dpp, "_compare_behind", lambda **kw: 1)
        regen: list[str] = []

        def _regen(sha: str) -> int:
            regen.append(sha)
            return 0

        monkeypatch.setattr(dpp, "_regenerate_pins", _regen)
        enabled: list[int] = []
        monkeypatch.setattr(dpp, "_enable_auto_merge", lambda **kw: enabled.append(kw["pr_number"]))
        rc = dpp.main(_refresh_argv(tmp_path))
        assert rc == 0
        assert enabled == [1140]
        assert regen == []  # name already matches; no new branch cut

    def test_regenerate_failure_returns_1(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(dpp, "_list_open_prs_by_prefix", lambda **kw: [_open_pin_pr(1132)])
        monkeypatch.setattr(dpp, "_compare_behind", lambda **kw: 2)
        monkeypatch.setattr(dpp, "_regenerate_pins", lambda sha: 1)
        assert dpp.main(_refresh_argv(tmp_path)) == 1
