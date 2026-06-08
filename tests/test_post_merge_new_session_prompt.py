"""Tests for scripts/post_merge_new_session_prompt.py.

Verifies that the PostToolUse hook detects a merge of session-affecting
configuration (hook config, SessionStart provisioning scripts, the
DevContainer tree), emits a verbatim paste-ready prompt for a new session,
and stays silent (fail-open) for non-merge tools, non-session-affecting
diffs, missing coordinates, or API failures. Refs issue #1291.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import post_merge_new_session_prompt as hook
import pytest

pytestmark = pytest.mark.shard_preflight


# ---------------------------------------------------------------------------
# extract_merge_coords
# ---------------------------------------------------------------------------


class TestExtractMergeCoords:
    def test_pr_number_from_tool_input_int(self) -> None:
        tool_input = {"owner": "tvna", "repo": "claude-md", "pullRequestNumber": 1291}
        assert hook.extract_merge_coords(tool_input, None) == ("tvna", "claude-md", "1291")

    def test_pr_number_from_response_url(self) -> None:
        response = {"url": "https://github.com/tvna/claude-md/pull/1291"}
        assert hook.extract_merge_coords({}, response) == ("tvna", "claude-md", "1291")

    def test_missing_all_returns_none_triple(self) -> None:
        assert hook.extract_merge_coords({}, None) == (None, None, None)

    def test_zero_pr_number_ignored(self) -> None:
        _, _, number = hook.extract_merge_coords({"pullRequestNumber": 0}, None)
        assert number is None


# ---------------------------------------------------------------------------
# classify
# ---------------------------------------------------------------------------


class TestClassify:
    PROV = frozenset({"scripts/install-uv.sh", "scripts/_session_path.sh"})

    def test_hook_config_files_classified(self) -> None:
        result = hook.classify([".claude/settings.json", ".codex/hooks.json"], self.PROV)
        assert result == {"hook_config": [".claude/settings.json", ".codex/hooks.json"]}

    def test_provisioning_scripts_classified(self) -> None:
        result = hook.classify(["scripts/install-uv.sh", "scripts/foo.py"], self.PROV)
        assert result == {"provisioning": ["scripts/install-uv.sh"]}

    def test_devcontainer_tree_classified_by_prefix(self) -> None:
        result = hook.classify([".devcontainer/images/claude/devcontainer.json"], self.PROV)
        assert result == {"devcontainer": [".devcontainer/images/claude/devcontainer.json"]}

    def test_multiple_categories(self) -> None:
        result = hook.classify(
            [".claude/settings.json", "scripts/install-uv.sh", ".devcontainer/x"], self.PROV
        )
        assert set(result) == {"hook_config", "provisioning", "devcontainer"}

    def test_non_session_affecting_returns_empty(self) -> None:
        assert hook.classify(["README.md", "scripts/foo.py", "src/app.ts"], self.PROV) == {}

    def test_sorted_output(self) -> None:
        result = hook.classify([".codex/hooks.json", ".claude/settings.json"], self.PROV)
        assert result["hook_config"] == [".claude/settings.json", ".codex/hooks.json"]


# ---------------------------------------------------------------------------
# provisioning_scripts (dynamic derivation)
# ---------------------------------------------------------------------------


class TestProvisioningScripts:
    def test_derives_referenced_and_sourced_scripts(self, tmp_path: Path) -> None:
        repo = tmp_path
        (repo / ".claude").mkdir()
        (repo / "scripts").mkdir()
        # install-uv.sh sources a helper via ${SCRIPT_DIR}/_session_path.sh.
        (repo / "scripts" / "install-uv.sh").write_text(
            '. "${SCRIPT_DIR}/_session_path.sh"\n', encoding="utf-8"
        )
        (repo / "scripts" / "_session_path.sh").write_text("# helper\n", encoding="utf-8")
        settings = repo / ".claude" / "settings.json"
        settings.write_text(
            json.dumps(
                {
                    "hooks": {
                        "SessionStart": [
                            {"hooks": [{"type": "command", "command": "scripts/install-uv.sh"}]},
                            {"hooks": [{"type": "command", "command": "python3 scripts/x.py"}]},
                        ]
                    }
                }
            ),
            encoding="utf-8",
        )
        result = hook.provisioning_scripts(settings)
        assert result == frozenset({"scripts/install-uv.sh", "scripts/_session_path.sh"})

    def test_missing_settings_returns_empty(self, tmp_path: Path) -> None:
        assert hook.provisioning_scripts(tmp_path / "nope.json") == frozenset()

    def test_real_repo_settings_includes_known_provisioners(self) -> None:
        # Grounded in the live config, not a fixture: the SessionStart shell
        # provisioners must be derived from the actual .claude/settings.json.
        result = hook.provisioning_scripts()
        assert "scripts/install-uv.sh" in result
        assert "scripts/_session_path.sh" in result


# ---------------------------------------------------------------------------
# decide
# ---------------------------------------------------------------------------


class TestDecide:
    PROV_SETTINGS = None  # use real repo settings by default

    def _merge_event(self) -> dict[str, object]:
        return {
            "tool_name": hook.TARGET_TOOL,
            "tool_input": {"owner": "tvna", "repo": "claude-md", "pullRequestNumber": 1291},
            "tool_response": {},
        }

    def test_non_merge_tool_returns_none(self) -> None:
        event = {"tool_name": "mcp__github__create_pull_request", "tool_input": {}}
        assert hook.decide(event, list_files=lambda *a, **k: [".claude/settings.json"], token="t") is None

    def test_missing_coords_returns_none(self) -> None:
        event = {"tool_name": hook.TARGET_TOOL, "tool_input": {}, "tool_response": {}}
        assert hook.decide(event, list_files=lambda *a, **k: [".claude/settings.json"], token="t") is None

    def test_api_failure_returns_none(self) -> None:
        assert hook.decide(self._merge_event(), list_files=lambda *a, **k: None, token="t") is None

    def test_no_session_affecting_files_returns_none(self) -> None:
        out = hook.decide(self._merge_event(), list_files=lambda *a, **k: ["README.md"], token="t")
        assert out is None

    def test_session_affecting_files_emit_prompt(self) -> None:
        out = hook.decide(
            self._merge_event(),
            list_files=lambda *a, **k: [".claude/settings.json", ".devcontainer/x"],
            token="t",
        )
        assert out is not None
        ctx = out["hookSpecificOutput"]["additionalContext"]
        assert out["hookSpecificOutput"]["hookEventName"] == "PostToolUse"
        assert "NEW SESSION REQUIRED" in ctx
        assert "tvna/claude-md#1291" in ctx
        # Paste-ready block is present, delimited, and in the owner language (ja).
        assert "--- BEGIN PASTE-READY PROMPT ---" in ctx
        assert "--- END PASTE-READY PROMPT ---" in ctx
        assert "新規セッション" in ctx
        assert ".claude/settings.json" in ctx
        assert ".devcontainer/x" in ctx

    def test_token_from_env_when_not_passed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: dict[str, object] = {}

        def fake_list(owner: str, repo: str, pr: str, *, token: str) -> list[str]:
            captured["token"] = token
            return [".claude/settings.json"]

        monkeypatch.setenv("GH_TOKEN", "env-token")
        out = hook.decide(self._merge_event(), list_files=fake_list)
        assert out is not None
        assert captured["token"] == "env-token"


# ---------------------------------------------------------------------------
# _list_pr_files
# ---------------------------------------------------------------------------


class TestListPrFiles:
    def test_no_token_returns_none(self) -> None:
        assert hook._list_pr_files("o", "r", "1", token="") is None

    def test_single_page(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[str] = []

        def fake_apply(*, method: str, url: str, payload: object, token: str, opener: object) -> tuple[int, str]:
            calls.append(url)
            return 200, json.dumps([{"filename": "a.py"}, {"filename": ".claude/settings.json"}])

        monkeypatch.setattr(hook, "apply_call", fake_apply)
        result = hook._list_pr_files("o", "r", "1", token="t", opener=lambda r: None)
        assert result == ["a.py", ".claude/settings.json"]
        assert "pulls/1/files" in calls[0]
        assert len(calls) == 1  # short page (< per_page) stops pagination

    def test_paginates_until_short_page(self, monkeypatch: pytest.MonkeyPatch) -> None:
        full_page = json.dumps([{"filename": f"f{i}.py"} for i in range(hook._PER_PAGE)])
        last_page = json.dumps([{"filename": ".devcontainer/x"}])
        bodies = [full_page, last_page]

        def fake_apply(*, method: str, url: str, payload: object, token: str, opener: object) -> tuple[int, str]:
            return 200, bodies.pop(0)

        monkeypatch.setattr(hook, "apply_call", fake_apply)
        result = hook._list_pr_files("o", "r", "1", token="t", opener=lambda r: None)
        assert result is not None
        assert result[-1] == ".devcontainer/x"
        assert len(result) == hook._PER_PAGE + 1

    def test_http_error_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def fake_apply(**kwargs: object) -> tuple[int, str]:
            return 404, "not found"

        monkeypatch.setattr(hook, "apply_call", fake_apply)
        assert hook._list_pr_files("o", "r", "1", token="t", opener=lambda r: None) is None


# ---------------------------------------------------------------------------
# main / wire protocol
# ---------------------------------------------------------------------------


class TestMain:
    def test_main_silent_on_non_merge(self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"tool_name": "Bash"})))
        assert hook.main([]) == 0
        assert capsys.readouterr().out == ""

    def test_main_silent_on_malformed_json(self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        monkeypatch.setattr("sys.stdin", io.StringIO("{not json"))
        assert hook.main([]) == 0
        assert capsys.readouterr().out == ""
