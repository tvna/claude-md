"""Tests for ``scripts/preflight_pr_body_required_sections.py``.

The ``scripts/`` directory is added to ``sys.path`` via the ``pythonpath``
key under ``[tool.pytest.ini_options]`` in ``pyproject.toml``.

Mirrors the structure of ``tests/test_preflight_pr_template_shape.py``:
pure decision function tested in isolation, then the stdin/stdout
boundary of :func:`main` with monkeypatched ``sys.stdin``.

Acceptance criteria from issue #382:

* all ``_PR_REQUIRED`` sections present -> allow,
* one section missing -> deny,
* multiple sections missing -> deny, reason lists all,
* empty body -> deny.

Refs #382. Builds on PR #350 (title-side preflight precedent) and
PR #372 (sibling shape preflight ``preflight_pr_template_shape.py``).
"""

from __future__ import annotations

import io
import json
from typing import Any

import body_policy
import preflight_pr_body_required_sections as preflight
import pytest

pytestmark = pytest.mark.shard_preflight
# ---------------------------------------------------------------------------
# Fixture bodies
# ---------------------------------------------------------------------------


def _build_body(*, drop: tuple[str, ...] = ()) -> str:
    """Return a PR body containing every ``_PR_REQUIRED`` H2 except *drop*.

    Sections in *drop* are omitted entirely. Section bodies stay minimal
    (a single ``-`` bullet) since this module only checks heading
    existence -- shape is enforced by ``preflight_pr_template_shape``.
    """
    lines: list[str] = []
    for name in body_policy._PR_REQUIRED:
        if name in drop:
            continue
        lines.append(f"## {name}")
        lines.append("")
        lines.append("- placeholder")
        lines.append("")
    return "\n".join(lines)


_GOOD_BODY = _build_body()


# ---------------------------------------------------------------------------
# evaluate
# ---------------------------------------------------------------------------


class TestEvaluate:
    def test_all_present_returns_empty(self) -> None:
        assert preflight.evaluate(_GOOD_BODY) == []

    def test_one_missing_returns_singleton(self) -> None:
        body = _build_body(drop=("Rollback",))
        assert preflight.evaluate(body) == ["Rollback"]

    def test_multiple_missing_returns_all(self) -> None:
        body = _build_body(drop=("Facts", "Rollback"))
        missing = preflight.evaluate(body)
        assert set(missing) == {"Facts", "Rollback"}

    def test_empty_body_returns_all_required(self) -> None:
        missing = preflight.evaluate("")
        assert set(missing) == set(body_policy._PR_REQUIRED)

    def test_h3_satisfies_required(self) -> None:
        # body_policy.extract_headings accepts H2 or H3; the hook must
        # mirror that, so an H3 heading is also accepted.
        body = _GOOD_BODY.replace("## Facts", "### Facts")
        assert preflight.evaluate(body) == []

    def test_risk_and_form_satisfies_ampersand_form(self) -> None:
        # body_policy._normalize_heading treats ``&`` and ``and`` as
        # interchangeable (refs #332). The hook delegates so it inherits
        # that behavior.
        body = _GOOD_BODY.replace(
            "## Risk & blast radius", "## Risk and blast radius"
        )
        assert preflight.evaluate(body) == []


# ---------------------------------------------------------------------------
# build_deny_reason
# ---------------------------------------------------------------------------


class TestBuildDenyReason:
    def test_lists_every_missing_section(self) -> None:
        reason = preflight.build_deny_reason(
            "mcp__github__create_pull_request",
            ["Facts", "Rollback", "Verification"],
        )
        assert "Facts" in reason
        assert "Rollback" in reason
        assert "Verification" in reason

    def test_includes_tool_name(self) -> None:
        reason = preflight.build_deny_reason(
            "mcp__github__update_pull_request", ["Facts"]
        )
        assert "mcp__github__update_pull_request" in reason

    def test_cites_server_side_authority(self) -> None:
        reason = preflight.build_deny_reason(
            "mcp__github__create_pull_request", ["Facts"]
        )
        assert "body_policy.py" in reason
        assert "verify-body-policy.yml" in reason

    def test_points_operator_to_template_and_docs(self) -> None:
        reason = preflight.build_deny_reason(
            "mcp__github__create_pull_request", ["Facts"]
        )
        assert "PULL_REQUEST_TEMPLATE.md" in reason

    def test_mentions_retrigger_loop_rationale(self) -> None:
        # The whole reason this hook exists -- retro #356 row 1 / PR #355
        # ran three trigger waves on a single head SHA.
        reason = preflight.build_deny_reason(
            "mcp__github__create_pull_request", ["Facts"]
        )
        assert "#356" in reason


# ---------------------------------------------------------------------------
# decide
# ---------------------------------------------------------------------------


class TestDecide:
    def test_well_formed_body_allows(self) -> None:
        assert (
            preflight.decide(
                "mcp__github__create_pull_request", {"body": _GOOD_BODY}
            )
            is None
        )

    def test_one_section_missing_denies(self) -> None:
        body = _build_body(drop=("Rollback",))
        decision = preflight.decide(
            "mcp__github__create_pull_request", {"body": body}
        )
        assert decision is not None
        spec = decision["hookSpecificOutput"]
        assert spec["hookEventName"] == "PreToolUse"
        assert spec["permissionDecision"] == "deny"
        assert "Rollback" in spec["permissionDecisionReason"]

    def test_multiple_missing_listed_in_reason(self) -> None:
        body = _build_body(drop=("Facts", "Assumptions", "Rollback"))
        decision = preflight.decide(
            "mcp__github__update_pull_request", {"body": body}
        )
        assert decision is not None
        reason = decision["hookSpecificOutput"]["permissionDecisionReason"]
        assert "Facts" in reason
        assert "Assumptions" in reason
        assert "Rollback" in reason

    def test_empty_body_denies_with_all_sections(self) -> None:
        decision = preflight.decide(
            "mcp__github__create_pull_request", {"body": ""}
        )
        assert decision is not None
        spec = decision["hookSpecificOutput"]
        assert spec["permissionDecision"] == "deny"
        reason = spec["permissionDecisionReason"]
        for name in body_policy._PR_REQUIRED:
            assert name in reason

    @pytest.mark.parametrize(
        "tool_name",
        [
            "mcp__github__create_pull_request",
            "mcp__github__update_pull_request",
        ],
    )
    def test_every_targeted_tool_is_gated(self, tool_name: str) -> None:
        decision = preflight.decide(tool_name, {"body": ""})
        assert decision is not None
        assert (
            decision["hookSpecificOutput"]["permissionDecision"] == "deny"
        )

    @pytest.mark.parametrize(
        "tool_name",
        [
            # Other GitHub MCP write tools that take a body but are not
            # PR-body events.
            "mcp__github__issue_write",
            "mcp__github__add_issue_comment",
            "mcp__github__add_reply_to_pull_request_comment",
            "mcp__github__pull_request_review_write",
            "mcp__github__sub_issue_write",
            # Non-write tools.
            "mcp__github__pull_request_read",
            "Bash",
            "Read",
        ],
    )
    def test_off_target_tools_allow(self, tool_name: str) -> None:
        # Even a body that would be denied on a PR call must pass on an
        # off-target tool, so the matcher in settings.json is the only
        # surface that decides which calls this hook covers.
        assert preflight.decide(tool_name, {"body": ""}) is None

    def test_missing_body_allows(self) -> None:
        # A payload without a ``body`` key is fail-open; another hook or
        # the server gate handles the no-body branch.
        assert (
            preflight.decide(
                "mcp__github__create_pull_request", {"title": "feat: x"}
            )
            is None
        )

    def test_non_string_body_allows(self) -> None:
        assert (
            preflight.decide(
                "mcp__github__create_pull_request", {"body": None}
            )
            is None
        )
        assert (
            preflight.decide(
                "mcp__github__create_pull_request", {"body": 42}
            )
            is None
        )


# ---------------------------------------------------------------------------
# main: stdin/stdout boundary
# ---------------------------------------------------------------------------


def _run_main(
    monkeypatch: pytest.MonkeyPatch,
    event: dict[str, Any] | str,
    capsys: pytest.CaptureFixture[str],
) -> tuple[int, str, str]:
    payload = event if isinstance(event, str) else json.dumps(event)
    monkeypatch.setattr("sys.stdin", io.StringIO(payload))
    rc = preflight.main([])
    captured = capsys.readouterr()
    return rc, captured.out, captured.err


class TestMain:
    def test_good_body_returns_0_silently(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        rc, out, err = _run_main(
            monkeypatch,
            {
                "tool_name": "mcp__github__create_pull_request",
                "tool_input": {"body": _GOOD_BODY},
            },
            capsys,
        )
        assert rc == 0
        assert out == ""
        assert err == ""

    def test_bad_body_emits_deny_json(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        rc, out, _ = _run_main(
            monkeypatch,
            {
                "tool_name": "mcp__github__create_pull_request",
                "tool_input": {"body": ""},
            },
            capsys,
        )
        assert rc == 0
        decision = json.loads(out)
        spec = decision["hookSpecificOutput"]
        assert spec["permissionDecision"] == "deny"
        assert spec["hookEventName"] == "PreToolUse"

    def test_off_target_tool_emits_nothing(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        rc, out, _ = _run_main(
            monkeypatch,
            {
                "tool_name": "mcp__github__add_issue_comment",
                "tool_input": {"body": ""},
            },
            capsys,
        )
        assert rc == 0
        assert out == ""

    def test_non_string_body_emits_nothing(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        rc, out, _ = _run_main(
            monkeypatch,
            {
                "tool_name": "mcp__github__create_pull_request",
                "tool_input": {"body": None},
            },
            capsys,
        )
        assert rc == 0
        assert out == ""

    def test_malformed_stdin_logs_and_returns_0(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        rc, out, err = _run_main(monkeypatch, "{not json", capsys)
        assert rc == 0
        assert out == ""
        assert "::error::" in err
        assert "malformed stdin JSON" in err

    def test_missing_tool_name_logs_and_returns_0(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        rc, out, err = _run_main(monkeypatch, {"tool_input": {}}, capsys)
        assert rc == 0
        assert out == ""
        assert "::error::" in err
        assert "missing tool_name" in err

    def test_empty_stdin_returns_0(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        rc, out, err = _run_main(monkeypatch, "", capsys)
        assert rc == 0
        assert out == ""
        # Empty stdin -> event is {} -> missing tool_name -> error log.
        assert "::error::" in err


# ---------------------------------------------------------------------------
# ASCII contract (deny reason must be ASCII so server gate can echo it)
# ---------------------------------------------------------------------------


class TestASCIIContract:
    def test_deny_reason_is_ascii(self) -> None:
        decision = preflight.decide(
            "mcp__github__create_pull_request", {"body": ""}
        )
        assert decision is not None
        reason = decision["hookSpecificOutput"]["permissionDecisionReason"]
        assert reason.isascii(), reason
