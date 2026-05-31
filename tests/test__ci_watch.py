"""Tests for ``scripts/_ci_watch.py``.

``_ci_watch.py`` is the detached CI-poll helper launched by
``post_pr_create_ci_monitor.py``. It shipped without a dedicated test file
(0% coverage in the suite-wide report); this module covers its REST wrapper,
the ``poll_ci`` settle/fail/timeout branches, and the ``main`` CLI argument
plumbing. All GitHub I/O is faked so no network call is made.

Refs #1032.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import _ci_watch as cw

pytestmark = pytest.mark.shard_ci_ops


# ---------------------------------------------------------------------------
# _rest_get
# ---------------------------------------------------------------------------


class TestRestGet:
    def test_returns_code_and_parsed_json(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(cw, "apply_call", lambda **kw: (200, '{"a": 1}'))
        code, data = cw._rest_get("https://api.github.com/x", token="t")
        assert code == 200
        assert data == {"a": 1}

    def test_apply_call_exception_returns_zero_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _boom(**kw: Any) -> tuple[int, str]:
            raise RuntimeError("network down")

        monkeypatch.setattr(cw, "apply_call", _boom)
        assert cw._rest_get("https://api.github.com/x", token="t") == (0, None)

    def test_bad_json_returns_code_and_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(cw, "apply_call", lambda **kw: (200, "not json"))
        code, data = cw._rest_get("https://api.github.com/x", token="t")
        assert code == 200
        assert data is None


# ---------------------------------------------------------------------------
# poll_ci
# ---------------------------------------------------------------------------


def _pr_payload(sha: str | None = "deadbeefcafe") -> dict[str, Any]:
    return {"head": {"sha": sha}} if sha is not None else {"head": {}}


class TestPollCi:
    def test_pr_fetch_failure_returns_one(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(cw, "_rest_get", lambda url, *, token: (404, None))
        rc = cw.poll_ci("o", "r", "5", token="t")
        assert rc == 1
        assert "error: HTTP 404" in capsys.readouterr().out

    def test_missing_head_sha_returns_one(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(cw, "_rest_get", lambda url, *, token: (200, _pr_payload(sha=None)))
        rc = cw.poll_ci("o", "r", "5", token="t")
        assert rc == 1
        assert "no head SHA" in capsys.readouterr().out

    def test_all_checks_pass(self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        def fake(url: str, *, token: str) -> tuple[int, Any]:
            if "/pulls/" in url:
                return 200, _pr_payload()
            return 200, {"check_runs": [{"status": "completed", "conclusion": "success"}]}

        monkeypatch.setattr(cw, "_rest_get", fake)
        rc = cw.poll_ci("o", "r", "5", token="t")
        out = capsys.readouterr().out
        assert rc == 0
        assert "CI PASSED" in out

    def test_failed_check_reported(self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        def fake(url: str, *, token: str) -> tuple[int, Any]:
            if "/pulls/" in url:
                return 200, _pr_payload()
            return 200, {
                "check_runs": [
                    {"status": "completed", "conclusion": "success", "name": "lint"},
                    {"status": "completed", "conclusion": "failure", "name": "tests"},
                ]
            }

        monkeypatch.setattr(cw, "_rest_get", fake)
        rc = cw.poll_ci("o", "r", "5", token="t")
        out = capsys.readouterr().out
        assert rc == 0
        assert "CI FAILED" in out
        assert "FAILED: tests" in out

    def test_check_runs_http_error_is_skipped_then_timeout(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # PR resolves, but every check-runs poll returns a non-2xx: the loop
        # logs each poll and ultimately times out with rc 0.
        monkeypatch.setattr(cw, "_MAX_POLLS", 2)

        def fake(url: str, *, token: str) -> tuple[int, Any]:
            if "/pulls/" in url:
                return 200, _pr_payload()
            return 503, None

        monkeypatch.setattr(cw, "_rest_get", fake)
        rc = cw.poll_ci("o", "r", "5", token="t")
        out = capsys.readouterr().out
        assert rc == 0
        assert "TIMEOUT" in out

    def test_incomplete_checks_time_out(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(cw, "_MAX_POLLS", 2)

        def fake(url: str, *, token: str) -> tuple[int, Any]:
            if "/pulls/" in url:
                return 200, _pr_payload()
            return 200, {"check_runs": [{"status": "in_progress"}]}

        monkeypatch.setattr(cw, "_rest_get", fake)
        rc = cw.poll_ci("o", "r", "5", token="t")
        assert rc == 0
        assert "TIMEOUT" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


class TestMain:
    def test_missing_token_returns_one(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.delenv("GH_TOKEN", raising=False)
        rc = cw.main(["--pr", "https://github.com/tvna/claude-md/pull/5"])
        assert rc == 1
        assert "GH_TOKEN not set" in capsys.readouterr().err

    def test_pr_url_is_parsed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GH_TOKEN", "t")
        captured: dict[str, Any] = {}

        def fake_poll(owner: str, repo: str, pr_number: str, *, token: str) -> int:
            captured.update(owner=owner, repo=repo, pr_number=pr_number, token=token)
            return 0

        monkeypatch.setattr(cw, "poll_ci", fake_poll)
        rc = cw.main(["--pr", "https://github.com/tvna/claude-md/pull/42"])
        assert rc == 0
        assert captured == {"owner": "tvna", "repo": "claude-md", "pr_number": "42", "token": "t"}

    def test_pr_number_with_repo(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GH_TOKEN", "t")
        captured: dict[str, Any] = {}
        monkeypatch.setattr(
            cw,
            "poll_ci",
            lambda owner, repo, pr_number, *, token: captured.update(
                owner=owner, repo=repo, pr_number=pr_number
            )
            or 0,
        )
        rc = cw.main(["--pr", "99", "--repo", "tvna/claude-md"])
        assert rc == 0
        assert captured == {"owner": "tvna", "repo": "claude-md", "pr_number": "99"}

    def test_pr_number_without_repo_returns_one(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setenv("GH_TOKEN", "t")
        rc = cw.main(["--pr", "99"])
        assert rc == 1
        assert "--repo owner/repo required" in capsys.readouterr().err
