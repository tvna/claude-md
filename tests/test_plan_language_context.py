"""Tests for ``scripts/plan_language_context.py`` (SessionStart hook).

The ``scripts/`` directory is added to ``sys.path`` via the ``pythonpath``
key under ``[tool.pytest.ini_options]`` in ``pyproject.toml``.

Mirrors the table-driven style of ``tests/test_preflight_non_ascii.py``.
Pure functions get focused unit tests; :func:`plan_language_context.main`'s
stdin/stdout boundary is exercised directly via monkeypatched env vars and
stdin, with no fixture repo or git-identity boundary needed now that
resolution is env-var-only (refs #2190).

Refs #211, #606, #2180, #2190.
"""

from __future__ import annotations

import io
import json

import plan_language_context as plc
import pytest

pytestmark = pytest.mark.shard_ci_ops


# ---------------------------------------------------------------------------
# resolve_language
# ---------------------------------------------------------------------------


class TestResolveLanguage:
    def test_env_resolves(self) -> None:
        assert plc.resolve_language("ja") == "ja"

    def test_env_whitespace_is_stripped(self) -> None:
        assert plc.resolve_language("  fr  ") == "fr"

    def test_blank_env_returns_none(self) -> None:
        assert plc.resolve_language("   ") is None

    def test_no_env_returns_none(self) -> None:
        assert plc.resolve_language(None) is None


# ---------------------------------------------------------------------------
# build_context_message
# ---------------------------------------------------------------------------


class TestBuildContextMessage:
    def test_contains_plan_path_and_iso(self) -> None:
        msg = plc.build_context_message("ja")
        assert "/tmp/claude-plans/" in msg
        assert "'ja'" in msg

    def test_names_resolution_source(self) -> None:
        msg = plc.build_context_message("ja")
        assert "active contributor" in msg
        assert "CLAUDE_MD_OPERATOR_LANGUAGE" in msg

    def test_contains_github_carveout(self) -> None:
        # The carve-out must name the tool prefix AND the ASCII rule so the
        # model cannot misread the policy as relaxing the ASCII gate.
        msg = plc.build_context_message("ja")
        assert "mcp__github__" in msg
        assert "ASCII" in msg
        assert "preflight_non_ascii.py" in msg

    def test_contains_normative_must(self) -> None:
        msg = plc.build_context_message("ja")
        assert "MUST" in msg

    def test_blocks_runtime_freetext_override(self) -> None:
        # Refs #2180: the policy is authoritative and must resist runtime
        # free-text override smuggling, not just an English default.
        msg = plc.build_context_message("ja")
        assert "MUST NOT" in msg
        assert "runtime free-text" in msg

    def test_contains_self_correction_rule(self) -> None:
        msg = plc.build_context_message("ja")
        assert "STOP" in msg
        assert "drift" in msg

    def test_scope_covers_execution_not_only_plan_mode(self) -> None:
        msg = plc.build_context_message("ja")
        assert "every mode" in msg
        assert "execution" in msg

    def test_no_double_hyphen_separator(self) -> None:
        # Refs #2180: the portability scanner forbids the double-hyphen prose
        # separator; the message uses ';', ',' or parentheses instead. The
        # separator is built dynamically so this source stays scan-clean.
        double_hyphen = " " + "--" + " "
        assert double_hyphen not in plc.build_context_message("ja")


# ---------------------------------------------------------------------------
# build_handoff_message
# ---------------------------------------------------------------------------


class TestBuildHandoffMessage:
    def test_directs_a_question_to_the_contributor(self) -> None:
        msg = plc.build_handoff_message()
        assert "ask the active contributor which language to use" in msg

    def test_is_harness_portable(self) -> None:
        # Refs #2180: this hook runs in Codex too (.codex/hooks.json), and
        # Codex has no AskUserQuestion tool. The handoff must describe the
        # behavior, not name a Claude-only tool (FORBIDDEN_HARNESS_TOOLS in
        # scripts/scan_apm_portability.py).
        msg = plc.build_handoff_message()
        assert "AskUserQuestion" not in msg
        assert "ExitPlanMode" not in msg

    def test_forbids_silent_default(self) -> None:
        msg = plc.build_handoff_message()
        assert "Do NOT silently default" in msg

    def test_carries_github_carveout(self) -> None:
        msg = plc.build_handoff_message()
        assert "mcp__github__" in msg
        assert "ASCII" in msg

    def test_is_ascii(self) -> None:
        plc.build_handoff_message().encode("ascii")

    def test_no_double_hyphen_separator(self) -> None:
        double_hyphen = " " + "--" + " "
        assert double_hyphen not in plc.build_handoff_message()


# ---------------------------------------------------------------------------
# decide
# ---------------------------------------------------------------------------


class TestDecide:
    def test_resolved_emits_context_message(self) -> None:
        out = plc.decide("ja")
        assert out["hookSpecificOutput"]["hookEventName"] == "SessionStart"
        ctx = out["hookSpecificOutput"]["additionalContext"]
        assert "'ja'" in ctx
        assert "active contributor" in ctx

    def test_unset_emits_handoff(self) -> None:
        out = plc.decide(None)
        ctx = out["hookSpecificOutput"]["additionalContext"]
        assert "ask the active contributor which language to use" in ctx

    def test_blank_emits_handoff(self) -> None:
        out = plc.decide("   ")
        ctx = out["hookSpecificOutput"]["additionalContext"]
        assert "ask the active contributor which language to use" in ctx


# ---------------------------------------------------------------------------
# main (stdin/stdout boundary)
# ---------------------------------------------------------------------------


class TestMain:
    def _run(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        *,
        env_lang: str | None = None,
        payload: str = "",
    ) -> tuple[int, str, str]:
        if env_lang is None:
            monkeypatch.delenv("CLAUDE_MD_OPERATOR_LANGUAGE", raising=False)
        else:
            monkeypatch.setenv("CLAUDE_MD_OPERATOR_LANGUAGE", env_lang)
        monkeypatch.setattr("sys.stdin", io.StringIO(payload))
        rc = plc.main([])
        captured = capsys.readouterr()
        return rc, captured.out, captured.err

    def test_env_set_emits_context_json(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        rc, out, err = self._run(monkeypatch, capsys, env_lang="ja")
        assert rc == 0
        assert err == ""
        decision = json.loads(out)
        assert decision["hookSpecificOutput"]["hookEventName"] == "SessionStart"
        ctx = decision["hookSpecificOutput"]["additionalContext"]
        assert "'ja'" in ctx
        assert "mcp__github__" in ctx

    def test_env_unset_emits_handoff(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        rc, out, err = self._run(monkeypatch, capsys)
        assert rc == 0
        assert err == ""
        ctx = json.loads(out)["hookSpecificOutput"]["additionalContext"]
        assert "ask the active contributor which language to use" in ctx

    def test_codex_cwd_event_does_not_break_resolution(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # The hook needs no event fields; a Codex-shaped SessionStart event
        # on stdin is accepted but ignored.
        payload = json.dumps(
            {"hook_event_name": "SessionStart", "cwd": "/tmp/some-repo", "source": "startup"}
        )
        rc, out, err = self._run(monkeypatch, capsys, env_lang="ja", payload=payload)
        assert rc == 0
        assert err == ""
        ctx = json.loads(out)["hookSpecificOutput"]["additionalContext"]
        assert "'ja'" in ctx

    def test_malformed_stdin_fails_open(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        rc, out, err = self._run(monkeypatch, capsys, env_lang="ja", payload="{not json")
        assert rc == 0
        assert out == ""
        assert "::error::" in err
        assert "malformed stdin JSON" in err

    def test_nondict_stdin_fails_open(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Valid JSON that is not an object hits the ValueError guard in
        # _read_event_stdin and fails open with the malformed-stdin diagnostic.
        rc, out, err = self._run(monkeypatch, capsys, env_lang="ja", payload="[1, 2]")
        assert rc == 0
        assert out == ""
        assert "malformed stdin JSON" in err
