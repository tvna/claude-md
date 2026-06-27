"""Tests for ``scripts/backup_non_ascii.py``.

The ``scripts/`` directory is on ``sys.path`` via ``pyproject.toml``
``[tool.pytest.ini_options].pythonpath``. The REST boundary
(``backup_non_ascii.gh_paginate``, delegating to ``_github_api.paginate``)
is exercised by monkeypatching ``backup.paginate``; we never hit the network.

Refs #102.
"""

from __future__ import annotations

import gzip
import io
import json
from pathlib import Path
from typing import Any

import backup_non_ascii as backup
import pytest

pytestmark = pytest.mark.shard_policy
# ---------------------------------------------------------------------------
# Fakes for the REST boundary
# ---------------------------------------------------------------------------


def _make_paginate(items_by_path: dict[str, list[dict[str, Any]]]):
    """Return a fake ``_github_api.paginate`` keyed by REST path.

    ``items_by_path`` maps the path passed to ``gh_paginate`` (the helper
    appends ``per_page`` / ``page`` itself) to the full flattened item list
    the real paginated endpoint would yield.
    """

    def fake_paginate(path: str, *, token: str, **_kw: Any) -> list[dict[str, Any]]:
        return list(items_by_path.get(path, []))

    return fake_paginate


# ---------------------------------------------------------------------------
# gh_paginate
# ---------------------------------------------------------------------------


class TestGhPaginate:
    def test_empty_repo_yields_empty_list(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(backup, "paginate", _make_paginate({"/repos/x/y/issues?state=all": []}))
        assert backup.gh_paginate("/repos/x/y/issues?state=all") == []

    def test_returns_flattened_items(self, monkeypatch: pytest.MonkeyPatch) -> None:
        items = [{"id": 1}, {"id": 2}, {"id": 3}, {"id": 4}, {"id": 5}, {"id": 6}]
        monkeypatch.setattr(backup, "paginate", _make_paginate({"/foo": items}))
        out = backup.gh_paginate("/foo")
        assert [item["id"] for item in out] == [1, 2, 3, 4, 5, 6]

    def test_passes_token(self, monkeypatch: pytest.MonkeyPatch) -> None:
        seen: dict[str, Any] = {}

        def fake_paginate(path: str, *, token: str, **_kw: Any) -> list[dict[str, Any]]:
            seen["token"] = token
            return []

        monkeypatch.setattr(backup, "paginate", fake_paginate)
        backup.gh_paginate("/foo", token="tok")
        assert seen["token"] == "tok"


# ---------------------------------------------------------------------------
# _normalise_*
# ---------------------------------------------------------------------------


class TestNormaliseIssueOrPr:
    def test_issue_without_pull_request_field(self) -> None:
        raw = {
            "id": 100,
            "number": 5,
            "title": "Title",
            "body": "Body",
            "user": {"login": "alice"},
            "state": "open",
            "author_association": "OWNER",
        }
        out = backup._normalise_issue_or_pr(raw)
        assert out["type"] == "issue"
        assert out["number"] == 5
        assert out["comment_id"] is None
        assert out["author"] == "alice"

    def test_issue_with_pull_request_field_becomes_pr(self) -> None:
        raw = {
            "id": 200,
            "number": 7,
            "title": "PR",
            "body": "",
            "pull_request": {"url": "..."},
            "user": {"login": "bob"},
            "state": "closed",
            "author_association": "CONTRIBUTOR",
        }
        out = backup._normalise_issue_or_pr(raw)
        assert out["type"] == "pr"

    def test_null_body_coerced_to_empty_string(self) -> None:
        raw = {"id": 1, "number": 1, "title": None, "body": None, "user": None}
        out = backup._normalise_issue_or_pr(raw)
        assert out["title"] == ""
        assert out["body"] == ""
        assert out["author"] is None

    def test_body_preserves_non_ascii_byte_for_byte(self) -> None:
        body = "日本語 \U0001f3af zero​width"
        raw = {"id": 1, "number": 1, "title": "", "body": body, "user": {}}
        out = backup._normalise_issue_or_pr(raw)
        assert out["body"] == body


class TestNormaliseIssueComment:
    def test_extracts_parent_number_from_issue_url(self) -> None:
        raw = {
            "id": 999,
            "body": "hi",
            "user": {"login": "alice"},
            "issue_url": "https://api.github.com/repos/x/y/issues/42",
            "author_association": "MEMBER",
        }
        out = backup._normalise_issue_comment(raw)
        assert out["type"] == "issue_comment"
        assert out["number"] == 42
        assert out["comment_id"] == 999
        assert out["id"] == 999

    def test_missing_issue_url_yields_none_number(self) -> None:
        raw = {"id": 1, "body": "", "user": {}}
        out = backup._normalise_issue_comment(raw)
        assert out["number"] is None


class TestNormalisePrReviewComment:
    def test_extracts_parent_number_from_pull_request_url(self) -> None:
        raw = {
            "id": 555,
            "body": "review",
            "user": {"login": "bob"},
            "pull_request_url": "https://api.github.com/repos/x/y/pulls/7",
            "author_association": "OWNER",
        }
        out = backup._normalise_pr_review_comment(raw)
        assert out["type"] == "pr_review_comment"
        assert out["number"] == 7
        assert out["comment_id"] == 555


# ---------------------------------------------------------------------------
# normalise_items: comment kinds separated and sort is stable
# ---------------------------------------------------------------------------


class TestNormaliseItems:
    def test_comment_kinds_kept_separate(self) -> None:
        items = backup.normalise_items(
            issues_and_prs=[],
            issue_comments=[
                {
                    "id": 11,
                    "body": "issue-comment",
                    "user": {"login": "a"},
                    "issue_url": "https://api.github.com/repos/x/y/issues/1",
                }
            ],
            pr_review_comments=[
                {
                    "id": 22,
                    "body": "review-comment",
                    "user": {"login": "b"},
                    "pull_request_url": "https://api.github.com/repos/x/y/pulls/2",
                }
            ],
        )
        types = sorted(it["type"] for it in items)
        assert types == ["issue_comment", "pr_review_comment"]
        assert {it["id"] for it in items} == {11, 22}

    def test_sort_is_deterministic(self) -> None:
        raw_issues = [
            {"id": 3, "number": 30, "title": "", "body": "", "user": {}},
            {"id": 1, "number": 10, "title": "", "body": "", "user": {}},
            {"id": 2, "number": 20, "title": "", "body": "", "user": {}},
        ]
        items = backup.normalise_items(raw_issues, [], [])
        assert [it["id"] for it in items] == [1, 2, 3]


# ---------------------------------------------------------------------------
# serialise + gzip + sha256: reproducibility
# ---------------------------------------------------------------------------


class TestReproducibility:
    def test_same_payload_same_sha(self) -> None:
        payload = backup.build_payload(
            repo="x/y",
            items=[
                {"type": "issue", "id": 1, "number": 1, "comment_id": None,
                 "title": "t", "body": "b", "author": "a", "state": "open",
                 "author_association": "OWNER"}
            ],
            captured_at="2026-05-24T00:00:00Z",
        )
        a = backup.gzip_bytes(backup.serialise_payload(payload))
        b = backup.gzip_bytes(backup.serialise_payload(payload))
        assert backup.sha256_hex(a) == backup.sha256_hex(b)
        # 64 hex chars
        assert len(backup.sha256_hex(a)) == 64

    def test_gzip_round_trip(self) -> None:
        payload = backup.build_payload(repo="x/y", items=[], captured_at="t")
        raw = backup.serialise_payload(payload)
        blob = backup.gzip_bytes(raw)
        with gzip.GzipFile(fileobj=io.BytesIO(blob), mode="rb") as gz:
            restored = gz.read()
        assert restored == raw
        assert json.loads(restored.decode("utf-8")) == payload

    def test_non_ascii_body_preserved_through_round_trip(self) -> None:
        body = "日本語"
        payload = backup.build_payload(
            repo="x/y",
            items=[{
                "type": "issue", "id": 1, "number": 1, "comment_id": None,
                "title": "", "body": body, "author": "a", "state": "open",
                "author_association": "OWNER",
            }],
            captured_at="t",
        )
        blob = backup.gzip_bytes(backup.serialise_payload(payload))
        with gzip.GzipFile(fileobj=io.BytesIO(blob), mode="rb") as gz:
            restored = json.loads(gz.read().decode("utf-8"))
        assert restored["items"][0]["body"] == body


# ---------------------------------------------------------------------------
# cmd_capture: end-to-end with fake runner, deterministic captured_at
# ---------------------------------------------------------------------------


class TestCmdCapture:
    def test_writes_gz_and_prints_sha(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setenv("REPO", "x/y")
        monkeypatch.setenv("GH_TOKEN", "fake-token")
        monkeypatch.setenv("BACKUP_CAPTURED_AT", "2026-05-24T00:00:00Z")

        items_by_path: dict[str, list[dict[str, Any]]] = {
            "/repos/x/y/issues?state=all": [
                {"id": 1, "number": 1, "title": "T", "body": "B",
                 "user": {"login": "a"}, "state": "open",
                 "author_association": "OWNER"}
            ],
            "/repos/x/y/issues/comments": [],
            "/repos/x/y/pulls/comments": [],
        }
        monkeypatch.setattr(backup, "paginate", _make_paginate(items_by_path))

        out_path = tmp_path / "snap.json.gz"
        rc = backup.main(["capture", "--out", str(out_path)])
        assert rc == 0
        assert out_path.exists()
        captured = capsys.readouterr().out
        assert "sha256:" in captured
        assert "items: 1" in captured

        # Determinism: regenerate with same env, expect identical bytes.
        out_path2 = tmp_path / "snap2.json.gz"
        backup.main(["capture", "--out", str(out_path2)])
        assert out_path.read_bytes() == out_path2.read_bytes()

    def test_missing_repo_env_returns_2(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.delenv("REPO", raising=False)
        monkeypatch.setenv("GH_TOKEN", "fake")
        rc = backup.main(["capture", "--out", str(tmp_path / "x.gz")])
        assert rc == 2


# ---------------------------------------------------------------------------
# cmd_sha256
# ---------------------------------------------------------------------------


class TestCmdSha256:
    def test_prints_expected_digest(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        path = tmp_path / "blob.bin"
        path.write_bytes(b"hello")
        expected = backup.sha256_hex(b"hello")
        rc = backup.main(["sha256", "--in", str(path)])
        assert rc == 0
        assert capsys.readouterr().out.strip() == expected


# ---------------------------------------------------------------------------
# argparse error path
# ---------------------------------------------------------------------------


class TestArgparse:
    def test_unknown_subcommand_exits_nonzero(self) -> None:
        with pytest.raises(SystemExit) as excinfo:
            backup.main(["bogus"])
        assert excinfo.value.code != 0


# ---------------------------------------------------------------------------
# Missing branch coverage
# ---------------------------------------------------------------------------


class TestParentNumberFromUrl:
    def test_none_url_returns_none(self) -> None:
        assert backup._parent_number_from_url(None) is None

    def test_non_numeric_tail_returns_none(self) -> None:
        # Line 47-48: ValueError branch
        assert backup._parent_number_from_url("https://example.com/issues/abc") is None


class TestNowIso:
    def test_returns_iso_string(self) -> None:
        # Line 152: _now_iso coverage
        result = backup._now_iso()
        assert "T" in result
        assert result.endswith("Z")


class TestCmdCaptureMissingToken:
    def test_missing_gh_token_returns_2(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        # Lines 209-210: GH_TOKEN missing branch
        monkeypatch.setenv("REPO", "x/y")
        monkeypatch.delenv("GH_TOKEN", raising=False)
        rc = backup.main(["capture", "--out", str(tmp_path / "x.gz")])
        assert rc == 2


class TestMainIfName:
    def test_main_raises_system_exit(self) -> None:
        with pytest.raises(SystemExit):
            backup.main(["unknown-cmd"])


class TestBackupMainDunderName:
    def test_if_name_main(self) -> None:
        # Line 272-273: __main__ guard
        import runpy

        with pytest.raises(SystemExit):
            runpy.run_path(
                str(
                    __import__("pathlib").Path(__file__).parent.parent
                    / "scripts"
                    / "backup_non_ascii.py"
                ),
                run_name="__main__",
            )
