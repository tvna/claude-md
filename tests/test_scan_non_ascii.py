"""Tests for ``scripts/scan_non_ascii.py``.

The `scripts/` directory is added to ``sys.path`` via the ``pythonpath``
key under ``[tool.pytest.ini_options]`` in ``pyproject.toml``.

Mirrors the structure of ``tests/test_uv_pin.py`` per the strategy in
issue #123: pure functions get table-driven tests; the subprocess
boundary (:func:`scan_non_ascii.gh_api`) is monkeypatched.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
import scan_non_ascii as san

pytestmark = pytest.mark.shard_policy
# ---------------------------------------------------------------------------
# extract_event
# ---------------------------------------------------------------------------


class TestExtractEvent:
    def test_issues(self) -> None:
        event = {
            "issue": {
                "number": 42,
                "title": "Hello",
                "body": "Body",
                "author_association": "OWNER",
                "user": {"login": "alice"},
            }
        }
        out = san.extract_event(event, "issues")
        assert out == {
            "kind": "issue",
            "number": 42,
            "title": "Hello",
            "body": "Body",
            "association": "OWNER",
            "login": "alice",
        }

    def test_login_extracted_from_pull_request(self) -> None:
        event = {
            "pull_request": {
                "number": 7,
                "title": "T",
                "body": "B",
                "author_association": "NONE",
                "user": {"login": "dependabot[bot]"},
            }
        }
        out = san.extract_event(event, "pull_request_target")
        assert out["login"] == "dependabot[bot]"

    def test_login_extracted_from_comment(self) -> None:
        event = {
            "issue": {"number": 9, "pull_request": {"url": "..."}},
            "comment": {
                "body": "hi",
                "author_association": "NONE",
                "user": {"login": "dependabot[bot]"},
            },
        }
        out = san.extract_event(event, "issue_comment")
        assert out["login"] == "dependabot[bot]"

    def test_missing_user_yields_none_login(self) -> None:
        """A payload without `.issue.user` keeps `login=None` (no crash)."""
        event = {"issue": {"number": 1, "title": "x", "body": "y"}}
        out = san.extract_event(event, "issues")
        assert out["login"] is None

    def test_pull_request_target(self) -> None:
        event = {
            "pull_request": {
                "number": 7,
                "title": "T",
                "body": "B",
                "author_association": "CONTRIBUTOR",
            }
        }
        out = san.extract_event(event, "pull_request_target")
        assert out["kind"] == "pull_request"
        assert out["number"] == 7
        assert out["association"] == "CONTRIBUTOR"

    def test_issue_comment_on_issue(self) -> None:
        event = {
            "issue": {"number": 5},
            "comment": {"body": "hi", "author_association": "MEMBER"},
        }
        out = san.extract_event(event, "issue_comment")
        assert out["kind"] == "issue_comment"
        assert out["number"] == 5
        assert out["title"] == ""
        assert out["body"] == "hi"

    def test_issue_comment_on_pr(self) -> None:
        """issue_comment event on a PR: `.issue.pull_request` is present."""
        event = {
            "issue": {"number": 9, "pull_request": {"url": "..."}},
            "comment": {"body": "hi", "author_association": "MEMBER"},
        }
        out = san.extract_event(event, "issue_comment")
        assert out["kind"] == "pr_comment"
        assert out["number"] == 9

    def test_pull_request_review_comment(self) -> None:
        event = {
            "pull_request": {"number": 11},
            "comment": {"body": "review", "author_association": "NONE"},
        }
        out = san.extract_event(event, "pull_request_review_comment")
        assert out["kind"] == "pr_review_comment"
        assert out["number"] == 11
        assert out["association"] == "NONE"

    def test_missing_fields_default_to_empty(self) -> None:
        """null title/body coerce to '' (matches the `// ""` jq fallback)."""
        event = {"issue": {"number": 1, "title": None, "body": None}}
        out = san.extract_event(event, "issues")
        assert out["title"] == ""
        assert out["body"] == ""

    def test_unsupported_event_raises(self) -> None:
        with pytest.raises(ValueError, match="unsupported event"):
            san.extract_event({}, "push")


# ---------------------------------------------------------------------------
# detect_non_ascii
# ---------------------------------------------------------------------------


class TestDetectNonAscii:
    @pytest.mark.parametrize(
        "text",
        [
            "",
            "plain ascii",
            "123 ABC !@#$%^&*()_+-=",
            "tabs\tand\nnewlines",
        ],
    )
    def test_pure_ascii_is_false(self, text: str) -> None:
        assert san.detect_non_ascii(text) is False

    @pytest.mark.parametrize(
        "text",
        [
            "日本語",          # Japanese: nihongo
            "hello \U0001f3af",            # 4-byte emoji (target)
            "before​after",           # zero-width space
            "abc‮def",                # RTL override
            "ＡＢＣ",          # fullwidth Latin
            "homoglyph: а",           # Cyrillic 'a'
            "tag char \U000e0041",         # tag character
        ],
    )
    def test_non_ascii_is_true(self, text: str) -> None:
        assert san.detect_non_ascii(text) is True


# ---------------------------------------------------------------------------
# has_ack_marker
# ---------------------------------------------------------------------------


class TestHasAckMarker:
    def test_present(self) -> None:
        assert san.has_ack_marker("reviewed <!-- non-ascii-ack --> ok")

    def test_absent(self) -> None:
        assert san.has_ack_marker("no marker here") is False

    def test_empty(self) -> None:
        assert san.has_ack_marker("") is False

    def test_custom_marker(self) -> None:
        assert san.has_ack_marker("xyz", marker="xyz")


# ---------------------------------------------------------------------------
# trust_class / classify_action
# ---------------------------------------------------------------------------


class TestTrustClass:
    @pytest.mark.parametrize("assoc", ["OWNER", "MEMBER", "COLLABORATOR"])
    def test_trusted(self, assoc: str) -> None:
        assert san.trust_class(assoc) == "trusted"

    @pytest.mark.parametrize(
        "assoc",
        [
            "CONTRIBUTOR",
            "FIRST_TIME_CONTRIBUTOR",
            "FIRST_TIMER",
            "NONE",
            "MANNEQUIN",
            "UNKNOWN_VALUE",
            "",
            None,
        ],
    )
    def test_external_fail_closed(self, assoc: str | None) -> None:
        assert san.trust_class(assoc) == "external"


class TestClassifyAction:
    def test_no_non_ascii_is_none(self) -> None:
        # Even an external author + non-ascii=False -> none.
        assert san.classify_action(False, False, "NONE") == "none"

    def test_trusted_with_ack_skips(self) -> None:
        assert san.classify_action(True, True, "OWNER") == "skip"

    def test_trusted_title_violation_with_ack_still_advises(self) -> None:
        assert (
            san.classify_action(
                True,
                True,
                "OWNER",
                has_title_violation=True,
            )
            == "advisory"
        )

    def test_trusted_without_ack_is_advisory(self) -> None:
        assert san.classify_action(True, False, "MEMBER") == "advisory"

    def test_external_blocks(self) -> None:
        assert san.classify_action(True, False, "NONE") == "block"

    def test_external_with_ack_still_blocks(self) -> None:
        """Ack marker is ignored for external authors (per the spec)."""
        assert san.classify_action(True, True, "NONE") == "block"

    def test_unknown_assoc_blocks_fail_closed(self) -> None:
        assert san.classify_action(True, False, None) == "block"
        assert san.classify_action(True, False, "WHO_IS_THIS") == "block"

    def test_trusted_bot_non_ascii_is_advisory_not_block(self) -> None:
        """dependabot[bot] reports assoc=NONE but is on the trusted-bot
        allowlist (#137). A would-be block demotes to advisory; the scan
        and the advisory comment still happen."""
        assert (
            san.classify_action(True, False, "NONE", "dependabot[bot]")
            == "advisory"
        )

    @pytest.mark.parametrize("login", ["codecov", "codecov[bot]"])
    def test_codecov_non_ascii_is_advisory_not_block(self, login: str) -> None:
        """Codecov reports assoc=NONE but is trusted for generated comments."""
        assert san.classify_action(True, False, "NONE", login) == "advisory"

    def test_trusted_bot_ascii_only_is_none(self) -> None:
        """No non-ASCII -> none regardless of login (cheap-exit guard)."""
        assert (
            san.classify_action(False, False, "NONE", "dependabot[bot]")
            == "none"
        )

    def test_unknown_bot_still_blocks(self) -> None:
        """The allowlist is exact-match; renovate[bot] is not on it."""
        assert (
            san.classify_action(True, False, "NONE", "renovate[bot]")
            == "block"
        )


# ---------------------------------------------------------------------------
# Trusted bot allowlist invariants
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "login",
    sorted(san._TRUSTED_BOT_LOGINS),
)
def test_every_shared_trusted_bot_login_ends_with_bot_suffix(login: str) -> None:
    """Shared trusted bots keep the GitHub-canonical ``<name>[bot]`` shape."""
    assert login.endswith("[bot]"), (
        f"Trusted bot login {login!r} missing canonical '[bot]' suffix"
    )


def test_codecov_scanner_aliases_are_exact_observed_shapes() -> None:
    """Regression guard for #504 / #620: Codecov has appeared both ways."""
    assert frozenset({"codecov", "codecov[bot]"}) == san._CODECOV_BOT_LOGINS


# ---------------------------------------------------------------------------
# escape_for_comment
# ---------------------------------------------------------------------------


class TestEscapeForComment:
    def test_ascii_passes_through(self) -> None:
        assert san.escape_for_comment("plain ascii") == "plain ascii"

    def test_bmp_codepoint_uses_uxxxx(self) -> None:
        # Hiragana 'a' (U+3042) -> literal six chars: \ u 3 0 4 2
        assert san.escape_for_comment("あ") == "\\u3042"

    def test_non_bmp_codepoint_uses_surrogate_pair(self) -> None:
        # U+1F3AF (target emoji) -> literal surrogate-pair escape.
        assert san.escape_for_comment("\U0001f3af") == "\\ud83c\\udfaf"

    def test_internal_quotes_are_escaped(self) -> None:
        assert san.escape_for_comment('say "hi"') == r'say \"hi\"'

    def test_backslash_is_escaped(self) -> None:
        assert san.escape_for_comment("a\\b") == r"a\\b"

    def test_truncation(self) -> None:
        long = "a" * 100
        out = san.escape_for_comment(long, max_len=10)
        assert out == "a" * 10 + "... [truncated]"

    def test_no_truncation_at_boundary(self) -> None:
        out = san.escape_for_comment("a" * 10, max_len=10)
        assert out == "a" * 10


# ---------------------------------------------------------------------------
# build_advisory_comment
# ---------------------------------------------------------------------------


class TestBuildAdvisoryComment:
    def test_advisory_branch(self) -> None:
        body = san.build_advisory_comment(
            action="advisory",
            association="OWNER",
            kind="issue",
            escaped=r"あ",
        )
        assert body.startswith(san.COMMENT_MARKER)
        assert "Trusted author (`OWNER`)" in body
        assert san.NON_ASCII_LABEL in body
        assert san.ACK_MARKER in body
        assert r"あ" in body
        assert "issue" in body

    def test_block_branch(self) -> None:
        body = san.build_advisory_comment(
            action="block",
            association="NONE",
            kind="pull_request",
            escaped=r"🎯",
        )
        assert body.startswith(san.COMMENT_MARKER)
        assert "External author (`NONE`)" in body
        assert "blocked pending" in body
        # Ack marker is still mentioned (saying it doesn't apply).
        assert san.ACK_MARKER in body
        assert r"🎯" in body

    def test_title_violation_notice(self) -> None:
        body = san.build_advisory_comment(
            action="advisory",
            association="OWNER",
            kind="issue",
            escaped=r"\u3042",
            has_title_violation=True,
        )
        assert "Title policy violation" in body
        assert "must be ASCII-only" in body
        assert "does not dismiss a non-ASCII title" in body


# ---------------------------------------------------------------------------
# build_summary
# ---------------------------------------------------------------------------


class TestBuildSummary:
    def test_contains_all_fields(self) -> None:
        out = san.build_summary(
            event_name="issues",
            number=42,
            kind="issue",
            association="OWNER",
            trust="trusted",
            has_non_ascii=True,
            has_title_violation=True,
            has_ack=False,
            action="advisory",
        )
        assert "## scan-non-ascii summary" in out
        assert "`issues`" in out
        assert "#42" in out
        assert "`issue`" in out
        assert "`OWNER`" in out
        assert "`trusted`" in out
        assert "`true`" in out
        assert "`false`" in out
        assert "| Title violation | `true` |" in out
        assert "`advisory`" in out

    def test_handles_missing_number_and_assoc(self) -> None:
        out = san.build_summary(
            event_name="issues",
            number=None,
            kind="issue",
            association=None,
            trust="external",
            has_non_ascii=False,
            has_title_violation=False,
            has_ack=False,
            action="none",
        )
        assert "| Number | # |" in out
        assert "| Author association | `` |" in out


# ---------------------------------------------------------------------------
# gh_api (subprocess boundary)
# ---------------------------------------------------------------------------


def _fake_run_capture():
    """Return (recorder, fake_run). recorder collects call kwargs."""
    calls: list[dict[str, Any]] = []

    class _Result:
        def __init__(self, stdout: str = "", returncode: int = 0) -> None:
            self.stdout = stdout
            self.returncode = returncode
            self.stderr = ""

    def fake_run(cmd, **kwargs):
        calls.append({"cmd": cmd, **kwargs})
        return _Result(stdout="OK")

    return calls, fake_run


class TestGhApi:
    def test_get_uses_no_input(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls, fake_run = _fake_run_capture()
        monkeypatch.setattr(subprocess, "run", fake_run)
        out = san.gh_api("GET", "/repos/x/y/issues/1/comments")
        assert out == "OK"
        assert calls[0]["cmd"] == [
            "gh", "api", "--method", "GET", "/repos/x/y/issues/1/comments"
        ]
        assert "input" not in calls[0]

    def test_post_passes_json_on_stdin(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls, fake_run = _fake_run_capture()
        monkeypatch.setattr(subprocess, "run", fake_run)
        san.gh_api("POST", "/repos/x/y/issues/1/labels", {"labels": ["L"]})
        assert "--input" in calls[0]["cmd"]
        assert calls[0]["cmd"][-1] == "-"
        assert json.loads(calls[0]["input"]) == {"labels": ["L"]}

    def test_nonzero_exit_raises_loudly(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _raise(*_a, **_kw):
            raise subprocess.CalledProcessError(1, "gh", stderr="boom")

        monkeypatch.setattr(subprocess, "run", _raise)
        with pytest.raises(subprocess.CalledProcessError):
            san.gh_api("GET", "/x")


# ---------------------------------------------------------------------------
# find_existing_comment_id / post_or_update_comment / apply_label / block_external
# ---------------------------------------------------------------------------


class TestFindExistingCommentId:
    def test_match_by_marker(self, monkeypatch: pytest.MonkeyPatch) -> None:
        body = san.COMMENT_MARKER + "\n\nadvisory..."
        monkeypatch.setattr(
            san,
            "gh_api",
            lambda *_a, **_kw: json.dumps(
                [{"id": 101, "body": "unrelated"}, {"id": 202, "body": body}]
            ),
        )
        assert san.find_existing_comment_id("o/r", 1) == 202

    def test_no_match_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            san,
            "gh_api",
            lambda *_a, **_kw: json.dumps([{"id": 1, "body": "hi"}]),
        )
        assert san.find_existing_comment_id("o/r", 1) is None

    def test_empty_page_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(san, "gh_api", lambda *_a, **_kw: "[]")
        assert san.find_existing_comment_id("o/r", 1) is None


class TestPostOrUpdateComment:
    def test_creates_when_none_exists(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen: list[tuple] = []

        def fake_api(method, path, body=None, **_kw):
            seen.append((method, path, body))
            if method == "GET":
                return "[]"
            return ""

        monkeypatch.setattr(san, "gh_api", fake_api)
        out = san.post_or_update_comment("o/r", 5, "hello")
        assert out == "created"
        # GET first, then POST.
        assert seen[0][0] == "GET"
        assert seen[1] == ("POST", "/repos/o/r/issues/5/comments", {"body": "hello"})

    def test_updates_when_exists(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        existing = [{"id": 77, "body": san.COMMENT_MARKER + "\n\nold"}]
        seen: list[tuple] = []

        def fake_api(method, path, body=None, **_kw):
            seen.append((method, path, body))
            if method == "GET":
                return json.dumps(existing)
            return ""

        monkeypatch.setattr(san, "gh_api", fake_api)
        out = san.post_or_update_comment("o/r", 5, "new")
        assert out == "updated 77"
        assert seen[1] == ("PATCH", "/repos/o/r/issues/comments/77", {"body": "new"})


class TestApplyLabel:
    def test_posts_label(self, monkeypatch: pytest.MonkeyPatch) -> None:
        seen: list[tuple] = []
        monkeypatch.setattr(
            san,
            "gh_api",
            lambda method, path, body=None, **_kw: seen.append(
                (method, path, body)
            ),
        )
        san.apply_label("o/r", 9)
        assert seen == [
            ("POST", "/repos/o/r/issues/9/labels", {"labels": [san.NON_ASCII_LABEL]})
        ]


class TestBlockExternal:
    @pytest.mark.parametrize(
        "kind", ["pull_request", "pr_comment", "pr_review_comment"]
    )
    def test_pr_kinds_request_changes(
        self, monkeypatch: pytest.MonkeyPatch, kind: str
    ) -> None:
        seen: list[tuple] = []
        monkeypatch.setattr(
            san,
            "gh_api",
            lambda method, path, body=None, **_kw: seen.append(
                (method, path, body)
            ),
        )
        out = san.block_external("o/r", 12, kind)
        assert out == "requested-changes on PR #12"
        assert seen[0][0] == "POST"
        assert seen[0][1] == "/repos/o/r/pulls/12/reviews"
        assert seen[0][2]["event"] == "REQUEST_CHANGES"

    @pytest.mark.parametrize("kind", ["issue", "issue_comment"])
    def test_issue_kinds_close_not_planned(
        self, monkeypatch: pytest.MonkeyPatch, kind: str
    ) -> None:
        seen: list[tuple] = []
        monkeypatch.setattr(
            san,
            "gh_api",
            lambda method, path, body=None, **_kw: seen.append(
                (method, path, body)
            ),
        )
        out = san.block_external("o/r", 12, kind)
        assert out == "closed issue #12 (not_planned)"
        assert seen[0] == (
            "PATCH",
            "/repos/o/r/issues/12",
            {"state": "closed", "state_reason": "not_planned"},
        )

    def test_unknown_kind_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(san, "gh_api", lambda *_a, **_kw: "")
        with pytest.raises(ValueError, match="cannot block"):
            san.block_external("o/r", 1, "weird")


# ---------------------------------------------------------------------------
# run (orchestrator)
# ---------------------------------------------------------------------------


def _capture_gh_api(monkeypatch: pytest.MonkeyPatch) -> list[tuple]:
    """Replace san.gh_api with a recorder and return the calls list.

    The GET for find_existing_comment_id returns "[]" (no existing comment).
    """
    seen: list[tuple] = []

    def fake_api(method, path, body=None, **_kw):
        seen.append((method, path, body))
        if method == "GET":
            return "[]"
        return ""

    monkeypatch.setattr(san, "gh_api", fake_api)
    return seen


class TestRun:
    def test_action_none_does_no_api_calls(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        seen = _capture_gh_api(monkeypatch)
        event = {
            "issue": {
                "number": 1,
                "title": "plain",
                "body": "all ascii",
                "author_association": "NONE",
            }
        }
        assert san.run(event, "issues", "o/r") == 0
        assert seen == []
        assert "action=none" in capsys.readouterr().out

    def test_action_skip_does_no_api_calls(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen = _capture_gh_api(monkeypatch)
        event = {
            "issue": {
                "number": 1,
                "title": "ascii title",
                "body": "日本 " + san.ACK_MARKER,
                "author_association": "OWNER",
            }
        }
        assert san.run(event, "issues", "o/r") == 0
        assert seen == []

    def test_title_violation_with_ack_still_comments(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen = _capture_gh_api(monkeypatch)
        event = {
            "issue": {
                "number": 10,
                "title": "日本",
                "body": "ok " + san.ACK_MARKER,
                "author_association": "OWNER",
            }
        }
        assert san.run(event, "issues", "o/r") == 0
        methods_paths = [(c[0], c[1]) for c in seen]
        assert ("POST", "/repos/o/r/issues/10/labels") in methods_paths
        assert ("POST", "/repos/o/r/issues/10/comments") in methods_paths
        comment = next(
            c[2]["body"]
            for c in seen
            if c[0] == "POST" and c[1] == "/repos/o/r/issues/10/comments"
        )
        assert "Title policy violation" in comment
        assert "does not dismiss a non-ASCII title" in comment

    def test_action_advisory_labels_and_comments(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen = _capture_gh_api(monkeypatch)
        event = {
            "issue": {
                "number": 2,
                "title": "あ",
                "body": "ok",
                "author_association": "MEMBER",
            }
        }
        assert san.run(event, "issues", "o/r") == 0
        # Expected: POST label, GET comments, POST new comment.
        methods = [c[0] for c in seen]
        assert methods == ["POST", "GET", "POST"]
        # Label POST
        assert seen[0][1] == "/repos/o/r/issues/2/labels"
        # Comment POST
        assert seen[2][1] == "/repos/o/r/issues/2/comments"
        # No block call (no PR review POST, no issue close PATCH).
        assert all(c[0] != "PATCH" for c in seen)

    def test_action_block_external_pr(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen = _capture_gh_api(monkeypatch)
        event = {
            "pull_request": {
                "number": 3,
                "title": "あ",
                "body": "",
                "author_association": "NONE",
            }
        }
        assert san.run(event, "pull_request_target", "o/r") == 0
        methods_paths = [(c[0], c[1]) for c in seen]
        # Label, GET comments, POST new comment, POST request-changes review.
        assert ("POST", "/repos/o/r/issues/3/labels") in methods_paths
        assert ("POST", "/repos/o/r/issues/3/comments") in methods_paths
        assert ("POST", "/repos/o/r/pulls/3/reviews") in methods_paths

    def test_action_block_external_issue_closes(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen = _capture_gh_api(monkeypatch)
        event = {
            "issue": {
                "number": 4,
                "title": "あ",
                "body": "",
                "author_association": "FIRST_TIMER",
            }
        }
        assert san.run(event, "issues", "o/r") == 0
        # The close PATCH must be present.
        assert any(
            c[0] == "PATCH" and c[1] == "/repos/o/r/issues/4" for c in seen
        )

    def test_action_block_with_ack_still_blocks(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Ack marker is ignored for external authors."""
        seen = _capture_gh_api(monkeypatch)
        event = {
            "pull_request": {
                "number": 5,
                "title": "あ",
                "body": "i acked " + san.ACK_MARKER,
                "author_association": "NONE",
            }
        }
        assert san.run(event, "pull_request_target", "o/r") == 0
        assert any(
            c[0] == "POST" and c[1] == "/repos/o/r/pulls/5/reviews" for c in seen
        )

    def test_step_summary_written(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        summary = tmp_path / "summary.md"
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
        _capture_gh_api(monkeypatch)
        event = {
            "issue": {
                "number": 6,
                "title": "plain",
                "body": "",
                "author_association": "OWNER",
            }
        }
        san.run(event, "issues", "o/r")
        text = summary.read_text(encoding="utf-8")
        assert "## scan-non-ascii summary" in text
        assert "`action`" in text or "`none`" in text

    def test_trusted_bot_pr_advises_does_not_block(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """End-to-end (#137): dependabot[bot] PR with non-ASCII content gets
        the advisory comment and label but no REQUEST_CHANGES review."""
        seen = _capture_gh_api(monkeypatch)
        event = {
            "pull_request": {
                "number": 119,
                "title": "ci(actions): bump actions/checkout v5.0.0 -> v5.0.1",
                "body": "Release notes mention @user with a zero-width​space.",
                "author_association": "NONE",
                "user": {"login": "dependabot[bot]"},
            }
        }
        assert san.run(event, "pull_request_target", "o/r") == 0
        methods_paths = [(c[0], c[1]) for c in seen]
        # Advisory path: label + comment.
        assert ("POST", "/repos/o/r/issues/119/labels") in methods_paths
        assert ("POST", "/repos/o/r/issues/119/comments") in methods_paths
        # Block path must NOT fire: no REQUEST_CHANGES review.
        assert all(
            path != "/repos/o/r/pulls/119/reviews" for _, path in methods_paths
        )

    @pytest.mark.parametrize("login", ["codecov", "codecov[bot]"])
    def test_codecov_pr_comment_advises_does_not_block(
        self, monkeypatch: pytest.MonkeyPatch, login: str
    ) -> None:
        """Regression for #480/#504/#620: Codecov comments may include non-ASCII."""
        seen = _capture_gh_api(monkeypatch)
        event = {
            "issue": {"number": 478, "pull_request": {"url": "..."}},
            "comment": {
                "body": "Test analytics footer includes clipboard \U0001f4cb.",
                "author_association": "NONE",
                "user": {"login": login},
            },
        }
        assert san.run(event, "issue_comment", "o/r") == 0
        methods_paths = [(c[0], c[1]) for c in seen]
        assert ("POST", "/repos/o/r/issues/478/labels") in methods_paths
        assert ("POST", "/repos/o/r/issues/478/comments") in methods_paths
        assert all(
            path != "/repos/o/r/pulls/478/reviews" for _, path in methods_paths
        )

    def test_unknown_bot_pr_still_blocks(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A bot not on the allowlist (renovate[bot]) keeps the block path."""
        seen = _capture_gh_api(monkeypatch)
        event = {
            "pull_request": {
                "number": 120,
                "title": "あ",
                "body": "",
                "author_association": "NONE",
                "user": {"login": "renovate[bot]"},
            }
        }
        assert san.run(event, "pull_request_target", "o/r") == 0
        methods_paths = [(c[0], c[1]) for c in seen]
        assert ("POST", "/repos/o/r/pulls/120/reviews") in methods_paths

    def test_advisory_updates_existing_comment(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Idempotency: a prior advisory is PATCHed, not duplicated."""
        seen: list[tuple] = []

        def fake_api(method, path, body=None, **_kw):
            seen.append((method, path, body))
            if method == "GET":
                return json.dumps(
                    [{"id": 999, "body": san.COMMENT_MARKER + "\nold"}]
                )
            return ""

        monkeypatch.setattr(san, "gh_api", fake_api)
        event = {
            "issue": {
                "number": 7,
                "title": "あ",
                "body": "",
                "author_association": "OWNER",
            }
        }
        assert san.run(event, "issues", "o/r") == 0
        # Label POST, GET comments, PATCH existing comment 999.
        assert any(
            c[0] == "PATCH" and c[1] == "/repos/o/r/issues/comments/999"
            for c in seen
        )
        # No new POST to /comments.
        assert not any(
            c[0] == "POST" and c[1].endswith("/issues/7/comments") for c in seen
        )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


class TestCLI:
    def test_run_reads_event_file_and_acts(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        event = {
            "issue": {
                "number": 8,
                "title": "plain ascii",
                "body": "",
                "author_association": "OWNER",
            }
        }
        event_file = tmp_path / "event.json"
        event_file.write_text(json.dumps(event))
        seen = _capture_gh_api(monkeypatch)
        exit_code = san.main(
            [
                "run",
                "--event-file", str(event_file),
                "--event-name", "issues",
                "--repo", "o/r",
            ]
        )
        assert exit_code == 0
        # action=none -> no API calls
        assert seen == []

    def test_run_uses_env_vars_when_no_flags(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        event = {
            "issue": {
                "number": 9,
                "title": "",
                "body": "",
                "author_association": "OWNER",
            }
        }
        event_file = tmp_path / "event.json"
        event_file.write_text(json.dumps(event))
        monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_file))
        monkeypatch.setenv("GITHUB_EVENT_NAME", "issues")
        monkeypatch.setenv("REPO", "o/r")
        _capture_gh_api(monkeypatch)
        assert san.main(["run"]) == 0

    def test_run_missing_event_path_errors(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        monkeypatch.delenv("GITHUB_EVENT_PATH", raising=False)
        monkeypatch.setenv("GITHUB_EVENT_NAME", "issues")
        monkeypatch.setenv("REPO", "o/r")
        assert san.main(["run"]) == 1
        assert "GITHUB_EVENT_PATH" in capsys.readouterr().err

    def test_run_missing_event_name_errors(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        capsys: pytest.CaptureFixture,
    ) -> None:
        event_file = tmp_path / "event.json"
        event_file.write_text("{}")
        monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_file))
        monkeypatch.delenv("GITHUB_EVENT_NAME", raising=False)
        monkeypatch.setenv("REPO", "o/r")
        assert san.main(["run"]) == 1
        assert "GITHUB_EVENT_NAME" in capsys.readouterr().err

    def test_run_missing_repo_errors(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        capsys: pytest.CaptureFixture,
    ) -> None:
        event_file = tmp_path / "event.json"
        event_file.write_text("{}")
        monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_file))
        monkeypatch.setenv("GITHUB_EVENT_NAME", "issues")
        monkeypatch.delenv("REPO", raising=False)
        monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
        assert san.main(["run"]) == 1
        assert "REPO" in capsys.readouterr().err

    def test_run_malformed_event_file_errors(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        capsys: pytest.CaptureFixture,
    ) -> None:
        event_file = tmp_path / "event.json"
        event_file.write_text("{not json")
        exit_code = san.main(
            [
                "run",
                "--event-file", str(event_file),
                "--event-name", "issues",
                "--repo", "o/r",
            ]
        )
        assert exit_code == 1
        assert "cannot read event file" in capsys.readouterr().err

    def test_run_unsupported_event_name_errors(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        capsys: pytest.CaptureFixture,
    ) -> None:
        event_file = tmp_path / "event.json"
        event_file.write_text("{}")
        exit_code = san.main(
            [
                "run",
                "--event-file", str(event_file),
                "--event-name", "push",
                "--repo", "o/r",
            ]
        )
        assert exit_code == 1
        assert "unsupported event" in capsys.readouterr().err

    def test_run_gh_api_failure_is_loud(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        capsys: pytest.CaptureFixture,
    ) -> None:
        def _raise(*_a, **_kw):
            raise subprocess.CalledProcessError(1, "gh", stderr="auth fail")

        monkeypatch.setattr(san, "gh_api", _raise)
        event = {
            "issue": {
                "number": 1,
                "title": "あ",
                "body": "",
                "author_association": "OWNER",
            }
        }
        event_file = tmp_path / "event.json"
        event_file.write_text(json.dumps(event))
        exit_code = san.main(
            [
                "run",
                "--event-file", str(event_file),
                "--event-name", "issues",
                "--repo", "o/r",
            ]
        )
        assert exit_code == 1
        assert "gh api failed" in capsys.readouterr().err
