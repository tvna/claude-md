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
    unmapped subcommands return 0. Only the local read-only probes remain in the
    script (``diff`` for working-tree changes, ``ls-remote`` for branch
    existence); the pin commit itself is created via the GitHub API. Refs #1437.
    """

    def __init__(self, rc_map: dict[str, int] | None = None) -> None:
        self.rc_map = rc_map or {}
        self.calls: list[list[str]] = []

    def __call__(self, args: list[str], *, check: bool = False, **_: Any) -> subprocess.CompletedProcess[str]:
        self.calls.append(args)
        return subprocess.CompletedProcess(["git", *args], self.rc_map.get(args[0], 0))

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
# _create_pin_branch
# ---------------------------------------------------------------------------


class TestCreatePinBranch:
    def test_creates_ref_and_signed_commit_from_working_tree(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import base64

        pin = tmp_path / "pin.json"
        pin.write_text("contents", encoding="utf-8")
        monkeypatch.setattr(dpp, "_get_ref_sha", lambda **kw: "base-oid")
        created_ref: dict[str, Any] = {}
        monkeypatch.setattr(dpp, "_create_branch_ref", lambda **kw: created_ref.update(kw))
        commit: dict[str, Any] = {}

        def _commit(**kw: Any) -> str:
            commit.update(kw)
            return "new-oid"

        monkeypatch.setattr(dpp, "_create_commit_on_branch", _commit)
        dpp._create_pin_branch(
            repo="o/r", base="main", branch="b", files=[str(pin)], subject="subj", trailer="Refs #1", token="tok"
        )
        # Branch is cut at the base ref head, and the commit pins that same oid as
        # expectedHeadOid so a racing write to the new branch is rejected.
        assert created_ref == {"repo": "o/r", "branch": "b", "sha": "base-oid", "token": "tok"}
        assert commit["expected_head_oid"] == "base-oid"
        assert commit["headline"] == "subj"
        assert commit["body"] == "Refs #1"
        assert commit["additions"] == [
            {"path": str(pin), "contents": base64.b64encode(b"contents").decode("ascii")}
        ]

    def test_ref_lookup_failure_propagates(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _boom(**kw: Any) -> str:
            raise RuntimeError("Get ref heads/main failed")

        monkeypatch.setattr(dpp, "_get_ref_sha", _boom)
        with pytest.raises(RuntimeError, match="Get ref"):
            dpp._create_pin_branch(
                repo="o/r", base="main", branch="b", files=[], subject="s", trailer="t", token="tok"
            )


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

    def test_branch_exists_with_open_pr_short_circuits(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(dpp, "run_git", _FakeGit({"diff": 1, "ls-remote": 0}))
        monkeypatch.setattr(dpp, "_list_open_prs", lambda **kw: [{"number": 5}])
        upserted: list[Any] = []

        def _record_upsert(**kw: Any) -> tuple[str, int]:
            upserted.append(kw)
            return ("created", 99)

        monkeypatch.setattr(dpp, "_upsert_pr", _record_upsert)
        rc = dpp.main(_open_argv(tmp_path))
        assert rc == 0
        assert "already exists: #5" in capsys.readouterr().out
        assert upserted == []  # existing PR short-circuits before upsert

    def test_branch_exists_without_pr_falls_through_to_upsert(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        git = _FakeGit({"diff": 1, "ls-remote": 0})
        monkeypatch.setattr(dpp, "run_git", git)
        monkeypatch.setattr(dpp, "_list_open_prs", lambda **kw: [])
        upserted: list[Any] = []

        def _record_upsert(**kw: Any) -> tuple[str, int]:
            upserted.append(kw)
            return ("created", 7)

        monkeypatch.setattr(dpp, "_upsert_pr", _record_upsert)
        rc = dpp.main(_open_argv(tmp_path))
        assert rc == 0
        assert len(upserted) == 1
        assert not git.ran("commit")  # branch already existed; no new commit

    def test_branch_absent_creates_branch_then_upserts(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        git = _FakeGit({"diff": 1, "ls-remote": 2})  # ls-remote --exit-code: 2 == no match
        monkeypatch.setattr(dpp, "run_git", git)
        pin_calls: list[dict[str, Any]] = []
        monkeypatch.setattr(dpp, "_create_pin_branch", lambda **kw: pin_calls.append(kw))
        captured: dict[str, Any] = {}

        def _record_upsert(**kw: Any) -> tuple[str, int]:
            captured.update(kw)
            return ("created", 8)

        monkeypatch.setattr(dpp, "_upsert_pr", _record_upsert)
        rc = dpp.main(_open_argv(tmp_path, sha="zz"))
        assert rc == 0
        # The absent branch is created via the signed-commit API path, then upserted.
        assert len(pin_calls) == 1
        assert pin_calls[0]["branch"] == "devcontainer/image-pins-zz"
        assert pin_calls[0]["base"] == "main"
        assert captured["head"] == "devcontainer/image-pins-zz"
        assert "zz" in captured["body"]  # template placeholder substituted

    def test_create_branch_api_failure_returns_1(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(dpp, "run_git", _FakeGit({"diff": 1, "ls-remote": 2}))

        def _boom(**kw: Any) -> None:
            raise RuntimeError("createCommitOnBranch errors: [stale expectedHeadOid]")

        monkeypatch.setattr(dpp, "_create_pin_branch", _boom)
        rc = dpp.main(_open_argv(tmp_path))
        assert rc == 1
        assert "failed creating pin branch" in capsys.readouterr().err

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

    def test_open_defers_merge_to_keeper(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # open no longer requests auto-merge; the pin auto-merge keeper merges the
        # PR once its checks pass. open should not touch any merge helper.
        monkeypatch.setattr(dpp, "run_git", _FakeGit({"diff": 1, "ls-remote": 0}))
        monkeypatch.setattr(dpp, "_list_open_prs", lambda **kw: [])
        monkeypatch.setattr(dpp, "_upsert_pr", lambda **kw: ("created", 12))

        def _fail(**kw: Any) -> bool:
            raise AssertionError("open must not attempt a merge")

        monkeypatch.setattr(dpp, "_merge_pin_pr_if_clean", _fail)
        rc = dpp.main(_open_argv(tmp_path))
        assert rc == 0
        assert "keeper merges it" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# _parse_published_sha
# ---------------------------------------------------------------------------

_PUBLISHED = "b417e5833394f6f04a6e9b1eefe48026c09b4089"


class TestParsePublishedSha:
    def test_original_branch(self) -> None:
        assert dpp._parse_published_sha(f"devcontainer/image-pins-{_PUBLISHED}") == _PUBLISHED

    def test_refreshed_branch_strips_suffix(self) -> None:
        branch = f"devcontainer/image-pins-{_PUBLISHED}-r-0123456789ab"
        assert dpp._parse_published_sha(branch) == _PUBLISHED

    def test_unrelated_branch_returns_none(self) -> None:
        assert dpp._parse_published_sha("claude/some-feature") is None
        assert dpp._parse_published_sha("devcontainer/image-pins-NOTHEX") is None


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
    ref = f"devcontainer/image-pins-{sha}{suffix}"
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

    def test_up_to_date_pr_attempts_merge(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(dpp, "_list_open_prs_by_prefix", lambda **kw: [_open_pin_pr(1132)])
        monkeypatch.setattr(dpp, "_compare_behind", lambda **kw: 0)
        merged: list[int] = []

        def _merge(**kw: Any) -> bool:
            merged.append(kw["number"])
            return True

        monkeypatch.setattr(dpp, "_merge_pin_pr_if_clean", _merge)
        regen: list[str] = []

        def _regen(sha: str) -> int:
            regen.append(sha)
            return 0

        monkeypatch.setattr(dpp, "_regenerate_pins", _regen)
        rc = dpp.main(_refresh_argv(tmp_path))
        assert rc == 0
        assert merged == [1132]
        assert regen == []  # no rebase work when already up to date

    def test_behind_with_changes_supersedes_old_pr(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        git = _FakeGit({"diff": 1, "ls-remote": 2})  # changes present; refresh branch absent
        monkeypatch.setattr(dpp, "run_git", git)
        monkeypatch.setattr(dpp, "_list_open_prs_by_prefix", lambda **kw: [_open_pin_pr(1132)])
        monkeypatch.setattr(dpp, "_compare_behind", lambda **kw: 3)
        monkeypatch.setattr(dpp, "_regenerate_pins", lambda sha: 0)
        pin_calls: list[dict[str, Any]] = []
        monkeypatch.setattr(dpp, "_create_pin_branch", lambda **kw: pin_calls.append(kw))
        captured: dict[str, Any] = {}

        def _record_upsert(**kw: Any) -> tuple[str, int]:
            captured.update(kw)
            return ("created", 1140)

        monkeypatch.setattr(dpp, "_upsert_pr", _record_upsert)
        merged: list[int] = []

        def _merge(**kw: Any) -> bool:
            merged.append(kw["number"])
            return True

        monkeypatch.setattr(dpp, "_merge_pin_pr_if_clean", _merge)
        comments: list[tuple[int, str]] = []
        monkeypatch.setattr(dpp, "_comment_pr", lambda **kw: comments.append((kw["number"], kw["body"])))
        closed: list[int] = []
        monkeypatch.setattr(dpp, "_close_pr", lambda **kw: closed.append(kw["number"]))
        deleted: list[str] = []
        monkeypatch.setattr(dpp, "_delete_branch", lambda **kw: deleted.append(kw["branch"]))

        rc = dpp.main(_refresh_argv(tmp_path))
        assert rc == 0
        expected_branch = f"devcontainer/image-pins-{_PUBLISHED}-r-{_TARGET[:12]}"
        assert captured["head"] == expected_branch
        assert _PUBLISHED in captured["body"]  # template substituted with the published SHA
        assert len(pin_calls) == 1 and pin_calls[0]["branch"] == expected_branch
        # A freshly cut superseding PR has no checks yet; refresh defers its merge
        # to the auto-merge keeper rather than merging inline.
        assert merged == []
        assert closed == [1132]
        assert deleted == [f"devcontainer/image-pins-{_PUBLISHED}"]
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

    def test_already_refreshed_onto_target_attempts_merge(
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
        merged: list[int] = []

        def _merge(**kw: Any) -> bool:
            merged.append(kw["number"])
            return True

        monkeypatch.setattr(dpp, "_merge_pin_pr_if_clean", _merge)
        rc = dpp.main(_refresh_argv(tmp_path))
        assert rc == 0
        assert merged == [1140]
        assert regen == []  # name already matches; no new branch cut

    def test_regenerate_failure_returns_1(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(dpp, "_list_open_prs_by_prefix", lambda **kw: [_open_pin_pr(1132)])
        monkeypatch.setattr(dpp, "_compare_behind", lambda **kw: 2)
        monkeypatch.setattr(dpp, "_regenerate_pins", lambda sha: 1)
        assert dpp.main(_refresh_argv(tmp_path)) == 1

    def test_create_branch_api_failure_surfaces_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A failed signed-commit API call reports the concrete reason in the run log.

        The commit is created via the GitHub API, so a rejection (e.g. a stale
        ``expectedHeadOid`` or a permission error) surfaces as a ``RuntimeError``
        whose message must reach stderr so a keeper regression is diagnosable.
        Refs #1437 (supersedes the #1229 git-stderr guard).
        """
        monkeypatch.setattr(dpp, "run_git", _FakeGit({"diff": 1, "ls-remote": 2}))
        monkeypatch.setattr(dpp, "_list_open_prs_by_prefix", lambda **kw: [_open_pin_pr(1132)])
        monkeypatch.setattr(dpp, "_compare_behind", lambda **kw: 3)
        monkeypatch.setattr(dpp, "_regenerate_pins", lambda sha: 0)

        def _boom(**kw: Any) -> None:
            raise RuntimeError("Create branch ref failed: HTTP 403: forbidden")

        monkeypatch.setattr(dpp, "_create_pin_branch", _boom)
        rc = dpp.main(_refresh_argv(tmp_path))
        assert rc == 1
        err = capsys.readouterr().err
        assert "failed creating refresh branch" in err
        assert "HTTP 403" in err


# ---------------------------------------------------------------------------
# _merge subcommand
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("_env")
class TestMergeCommand:
    def test_no_open_pr_is_noop(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(dpp, "_list_open_prs_by_prefix", lambda **kw: [])
        rc = dpp.main(["merge"])
        assert rc == 0
        assert "nothing to merge" in capsys.readouterr().out

    def test_clean_pr_is_merged_with_head_ref(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(dpp, "_list_open_prs_by_prefix", lambda **kw: [_open_pin_pr(1132)])
        captured: dict[str, Any] = {}

        def _merge(**kw: Any) -> bool:
            captured.update(kw)
            return True

        monkeypatch.setattr(dpp, "_merge_pin_pr_if_clean", _merge)
        rc = dpp.main(["merge"])
        assert rc == 0
        assert captured["number"] == 1132
        assert captured["head_ref"] == f"devcontainer/image-pins-{_PUBLISHED}"

    def test_picks_newest_pr(self, monkeypatch: pytest.MonkeyPatch) -> None:
        prs = [_open_pin_pr(1132), _open_pin_pr(1140)]
        monkeypatch.setattr(dpp, "_list_open_prs_by_prefix", lambda **kw: prs)
        captured: dict[str, Any] = {}

        def _merge(**kw: Any) -> bool:
            captured.update(kw)
            return True

        monkeypatch.setattr(dpp, "_merge_pin_pr_if_clean", _merge)
        rc = dpp.main(["merge"])
        assert rc == 0
        assert captured["number"] == 1140

    def test_list_error_returns_1(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _boom(**kw: Any) -> list[dict[str, Any]]:
            raise RuntimeError("List PRs failed")

        monkeypatch.setattr(dpp, "_list_open_prs_by_prefix", _boom)
        assert dpp.main(["merge"]) == 1

    def test_merge_api_error_returns_1(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(dpp, "_list_open_prs_by_prefix", lambda **kw: [_open_pin_pr(1132)])

        def _boom(**kw: Any) -> bool:
            raise RuntimeError("Merge PR #1132 failed")

        monkeypatch.setattr(dpp, "_merge_pin_pr_if_clean", _boom)
        assert dpp.main(["merge"]) == 1

    def test_missing_token_returns_1(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("GH_TOKEN", raising=False)
        assert dpp.main(["merge"]) == 1

    def test_missing_repo_returns_1(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("REPO", raising=False)
        assert dpp.main(["merge"]) == 1


# ---------------------------------------------------------------------------
# _merge_pin_pr_if_clean / _poll_pr_mergeability
# ---------------------------------------------------------------------------


class TestMergePinPrIfClean:
    @pytest.fixture(autouse=True)
    def _no_sleep(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(dpp.time, "sleep", lambda _s: None)

    def test_clean_pr_merges_and_deletes_branch(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            dpp,
            "_get_pr",
            lambda **kw: {"mergeable": True, "mergeable_state": "clean", "head": {"sha": "deadbeef"}},
        )
        merged: dict[str, Any] = {}

        def _merge(**kw: Any) -> bool:
            merged.update(kw)
            return True

        monkeypatch.setattr(dpp, "_merge_pr", _merge)
        deleted: list[str] = []
        monkeypatch.setattr(dpp, "_delete_branch", lambda **kw: deleted.append(kw["branch"]))
        result = dpp._merge_pin_pr_if_clean(
            repo="o/r", number=5, head_ref="devcontainer/image-pins-x", token="t"
        )
        assert result is True
        assert merged["sha"] == "deadbeef"
        assert merged["merge_method"] == "squash"
        assert deleted == ["devcontainer/image-pins-x"]

    def test_not_clean_is_noop(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            dpp,
            "_get_pr",
            lambda **kw: {"mergeable": False, "mergeable_state": "dirty", "head": {"sha": "x"}},
        )
        called: list[Any] = []

        def _merge(**kw: Any) -> bool:
            called.append(kw)
            return True

        monkeypatch.setattr(dpp, "_merge_pr", _merge)
        result = dpp._merge_pin_pr_if_clean(repo="o/r", number=5, head_ref="b", token="t")
        assert result is False
        assert called == []  # never attempts the merge API on a non-clean PR

    def test_merge_race_returns_false_and_keeps_branch(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            dpp,
            "_get_pr",
            lambda **kw: {"mergeable": True, "mergeable_state": "clean", "head": {"sha": "s"}},
        )
        monkeypatch.setattr(dpp, "_merge_pr", lambda **kw: False)  # 405/409 race
        deleted: list[str] = []
        monkeypatch.setattr(dpp, "_delete_branch", lambda **kw: deleted.append(kw["branch"]))
        result = dpp._merge_pin_pr_if_clean(repo="o/r", number=5, head_ref="b", token="t")
        assert result is False
        assert deleted == []  # do not delete a branch we did not merge

    def test_clean_without_head_sha_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            dpp, "_get_pr", lambda **kw: {"mergeable": True, "mergeable_state": "clean", "head": {}}
        )
        with pytest.raises(RuntimeError, match="no head sha"):
            dpp._merge_pin_pr_if_clean(repo="o/r", number=5, head_ref="b", token="t")

    def test_polls_until_mergeable_computed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        seq: list[dict[str, Any]] = [
            {"mergeable": None, "mergeable_state": "unknown", "head": {"sha": "s"}},
            {"mergeable": True, "mergeable_state": "clean", "head": {"sha": "s"}},
        ]
        calls = {"n": 0}

        def _get(**kw: Any) -> dict[str, Any]:
            item = seq[min(calls["n"], len(seq) - 1)]
            calls["n"] += 1
            return item

        monkeypatch.setattr(dpp, "_get_pr", _get)
        monkeypatch.setattr(dpp, "_merge_pr", lambda **kw: True)
        monkeypatch.setattr(dpp, "_delete_branch", lambda **kw: None)
        result = dpp._merge_pin_pr_if_clean(repo="o/r", number=5, head_ref="b", token="t")
        assert result is True
        assert calls["n"] == 2  # polled past the still-computing response
