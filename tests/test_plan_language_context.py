"""Tests for ``scripts/plan_language_context.py`` (SessionStart hook).

The ``scripts/`` directory is added to ``sys.path`` via the ``pythonpath``
key under ``[tool.pytest.ini_options]`` in ``pyproject.toml``.

Mirrors the table-driven style of ``tests/test_preflight_non_ascii.py``.
Pure functions get focused unit tests; the file-IO and git-identity
boundary in :func:`plan_language_context.main` is exercised by writing a
fixture ``contributors.toml`` into a ``tmp_path`` repo root, pointing the
hook at it via ``CLAUDE_PROJECT_DIR``, and monkeypatching
:func:`plan_language_context._git_identity`.

Refs #211, #606, #2180.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import plan_language_context as plc
import pytest

pytestmark = pytest.mark.shard_ci_ops

# A generic non-human git identity, used to prove the resolver treats an
# unmapped identity as "ask", never as a silent owner/English default.
_BOT_EMAIL = "automation@ci.example.invalid"
_BOT_NAME = "CI Bot"


# ---------------------------------------------------------------------------
# load_contributor_languages
# ---------------------------------------------------------------------------


class TestLoadContributorLanguages:
    def test_happy_path(self) -> None:
        text = '"alice@example.com" = "en"\n"bob@example.com" = "fr"\n'
        assert plc.load_contributor_languages(text) == {
            "alice@example.com": "en",
            "bob@example.com": "fr",
        }

    def test_lowercases_keys(self) -> None:
        # Keys are lowercased so git-identity lookups are case-insensitive.
        text = '"Alice@Example.COM" = "en"\n"Jane Doe" = "ja"\n'
        assert plc.load_contributor_languages(text) == {
            "alice@example.com": "en",
            "jane doe": "ja",
        }

    def test_empty_text(self) -> None:
        assert plc.load_contributor_languages("") == {}

    def test_whitespace_only(self) -> None:
        assert plc.load_contributor_languages("   \n  \n") == {}

    def test_drops_non_string_values(self) -> None:
        text = '"alice@example.com" = "en"\n"count" = 42\n'
        assert plc.load_contributor_languages(text) == {"alice@example.com": "en"}

    def test_comments_are_ignored(self) -> None:
        text = '# comment\n"alice@example.com" = "en"\n'
        assert plc.load_contributor_languages(text) == {"alice@example.com": "en"}


# ---------------------------------------------------------------------------
# resolve_language
# ---------------------------------------------------------------------------


class TestResolveLanguage:
    def test_env_takes_priority(self) -> None:
        # The env var wins even when the toml would resolve a different code.
        source, iso = plc.resolve_language(
            "de", "alice@example.com", "Alice", '"alice@example.com" = "en"\n'
        )
        assert (source, iso) == ("env", "de")

    def test_env_whitespace_is_stripped(self) -> None:
        source, iso = plc.resolve_language("  fr  ", None, None, "")
        assert (source, iso) == ("env", "fr")

    def test_blank_env_falls_through_to_toml(self) -> None:
        source, iso = plc.resolve_language(
            "   ", "alice@example.com", None, '"alice@example.com" = "en"\n'
        )
        assert (source, iso) == ("email", "en")

    def test_email_match(self) -> None:
        source, iso = plc.resolve_language(
            None, "alice@example.com", "Alice", '"alice@example.com" = "en"\n'
        )
        assert (source, iso) == ("email", "en")

    def test_email_match_is_case_insensitive(self) -> None:
        source, iso = plc.resolve_language(
            None, "Alice@Example.COM", None, '"alice@example.com" = "en"\n'
        )
        assert (source, iso) == ("email", "en")

    def test_name_match_when_email_absent(self) -> None:
        source, iso = plc.resolve_language(
            None, None, "Jane Doe", '"jane doe" = "ja"\n'
        )
        assert (source, iso) == ("name", "ja")

    def test_name_match_is_case_insensitive(self) -> None:
        source, iso = plc.resolve_language(
            None, None, "JANE DOE", '"jane doe" = "ja"\n'
        )
        assert (source, iso) == ("name", "ja")

    def test_email_preferred_over_name(self) -> None:
        toml = '"alice@example.com" = "en"\n"alice" = "fr"\n'
        source, iso = plc.resolve_language(
            None, "alice@example.com", "Alice", toml
        )
        assert (source, iso) == ("email", "en")

    def test_unmapped_identity_returns_none(self) -> None:
        source, iso = plc.resolve_language(
            None, _BOT_EMAIL, _BOT_NAME, '"alice@example.com" = "en"\n'
        )
        assert source is None
        assert iso is None

    def test_no_identity_and_no_env_returns_none(self) -> None:
        assert plc.resolve_language(None, None, None, "") == (None, None)


# ---------------------------------------------------------------------------
# build_context_message
# ---------------------------------------------------------------------------


class TestBuildContextMessage:
    def test_contains_plan_path_and_iso(self) -> None:
        msg = plc.build_context_message("email", "ja")
        assert "/tmp/claude-plans/" in msg
        assert "'ja'" in msg

    def test_names_active_contributor_and_toml_source(self) -> None:
        msg = plc.build_context_message("email", "ja")
        assert "active contributor" in msg
        assert "contributors.toml" in msg

    def test_contains_github_carveout(self) -> None:
        # The carve-out must name the tool prefix AND the ASCII rule so the
        # model cannot misread the policy as relaxing the ASCII gate.
        msg = plc.build_context_message("name", "ja")
        assert "mcp__github__" in msg
        assert "ASCII" in msg
        assert "preflight_non_ascii.py" in msg

    def test_contains_normative_must(self) -> None:
        msg = plc.build_context_message("env", "ja")
        assert "MUST" in msg

    def test_blocks_runtime_freetext_override(self) -> None:
        # Refs #2180: the policy is authoritative and must resist runtime
        # free-text override smuggling, not just an English default.
        msg = plc.build_context_message("email", "ja")
        assert "MUST NOT" in msg
        assert "runtime free-text" in msg

    def test_contains_self_correction_rule(self) -> None:
        msg = plc.build_context_message("email", "ja")
        assert "STOP" in msg
        assert "drift" in msg

    def test_scope_covers_execution_not_only_plan_mode(self) -> None:
        msg = plc.build_context_message("email", "ja")
        assert "every mode" in msg
        assert "execution" in msg

    def test_no_double_hyphen_separator(self) -> None:
        # Refs #2180: the portability scanner forbids the double-hyphen prose
        # separator; the message uses ';', ',' or parentheses instead. The
        # separator is built dynamically so this source stays scan-clean.
        double_hyphen = " " + "--" + " "
        assert double_hyphen not in plc.build_context_message("email", "ja")


# ---------------------------------------------------------------------------
# build_handoff_message
# ---------------------------------------------------------------------------


class TestBuildHandoffMessage:
    def test_directs_askuserquestion(self) -> None:
        msg = plc.build_handoff_message()
        assert "AskUserQuestion" in msg

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
        out = plc.decide(
            None, "alice@example.com", "Alice", '"alice@example.com" = "ja"\n'
        )
        assert out["hookSpecificOutput"]["hookEventName"] == "SessionStart"
        ctx = out["hookSpecificOutput"]["additionalContext"]
        assert "'ja'" in ctx
        assert "active contributor" in ctx

    def test_env_override_emits_context_message(self) -> None:
        out = plc.decide("ja", None, None, "")
        ctx = out["hookSpecificOutput"]["additionalContext"]
        assert "'ja'" in ctx

    def test_unmapped_identity_emits_handoff(self) -> None:
        out = plc.decide(None, _BOT_EMAIL, _BOT_NAME, '"alice@example.com" = "en"\n')
        ctx = out["hookSpecificOutput"]["additionalContext"]
        assert "AskUserQuestion" in ctx
        assert "Do NOT silently default" in ctx

    def test_no_metadata_emits_handoff(self) -> None:
        out = plc.decide(None, None, None, "")
        assert "AskUserQuestion" in out["hookSpecificOutput"]["additionalContext"]


# ---------------------------------------------------------------------------
# main (file-IO and git-identity boundary)
# ---------------------------------------------------------------------------


class TestMain:
    def _setup_repo(
        self, tmp_path: Path, contributors_toml: str | None
    ) -> Path:
        """Build a fake repo root with an optional contributors.toml."""
        gh = tmp_path / ".github"
        gh.mkdir()
        if contributors_toml is not None:
            (gh / "contributors.toml").write_text(
                contributors_toml, encoding="utf-8"
            )
        return tmp_path

    def _run(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        root: Path,
        *,
        email: str | None = None,
        name: str | None = None,
        env_lang: str | None = None,
        payload: str = "",
    ) -> tuple[int, str, str]:
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(root))
        if env_lang is None:
            monkeypatch.delenv("CLAUDE_MD_OPERATOR_LANGUAGE", raising=False)
        else:
            monkeypatch.setenv("CLAUDE_MD_OPERATOR_LANGUAGE", env_lang)
        monkeypatch.setattr(plc, "_git_identity", lambda _root: (email, name))
        monkeypatch.setattr("sys.stdin", io.StringIO(payload))
        rc = plc.main([])
        captured = capsys.readouterr()
        return rc, captured.out, captured.err

    def test_email_match_emits_context_json(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
    ) -> None:
        root = self._setup_repo(tmp_path, '"alice@example.com" = "ja"\n')
        rc, out, err = self._run(
            monkeypatch, capsys, root, email="alice@example.com"
        )
        assert rc == 0
        assert err == ""
        decision = json.loads(out)
        assert decision["hookSpecificOutput"]["hookEventName"] == "SessionStart"
        ctx = decision["hookSpecificOutput"]["additionalContext"]
        assert "'ja'" in ctx
        assert "mcp__github__" in ctx

    def test_env_override_wins(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
    ) -> None:
        root = self._setup_repo(tmp_path, '"alice@example.com" = "en"\n')
        rc, out, err = self._run(
            monkeypatch,
            capsys,
            root,
            email="alice@example.com",
            env_lang="ja",
        )
        assert rc == 0
        assert err == ""
        ctx = json.loads(out)["hookSpecificOutput"]["additionalContext"]
        assert "'ja'" in ctx

    def test_unmapped_identity_emits_handoff(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
    ) -> None:
        root = self._setup_repo(tmp_path, '"alice@example.com" = "en"\n')
        rc, out, err = self._run(
            monkeypatch, capsys, root, email=_BOT_EMAIL, name=_BOT_NAME
        )
        assert rc == 0
        assert err == ""
        ctx = json.loads(out)["hookSpecificOutput"]["additionalContext"]
        assert "AskUserQuestion" in ctx

    def test_missing_contributors_toml_emits_handoff(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
    ) -> None:
        # Absence is not an error: with no env value and no toml the hook
        # still emits the question handoff rather than failing.
        root = self._setup_repo(tmp_path, None)
        rc, out, err = self._run(
            monkeypatch, capsys, root, email="alice@example.com"
        )
        assert rc == 0
        assert err == ""
        ctx = json.loads(out)["hookSpecificOutput"]["additionalContext"]
        assert "AskUserQuestion" in ctx

    def test_missing_toml_with_env_emits_context(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
    ) -> None:
        root = self._setup_repo(tmp_path, None)
        rc, out, err = self._run(monkeypatch, capsys, root, env_lang="ja")
        assert rc == 0
        assert err == ""
        ctx = json.loads(out)["hookSpecificOutput"]["additionalContext"]
        assert "'ja'" in ctx

    def test_malformed_toml_fails_open(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
    ) -> None:
        root = self._setup_repo(tmp_path, "[invalid\n")
        rc, out, err = self._run(
            monkeypatch, capsys, root, email="alice@example.com"
        )
        assert rc == 0
        assert out == ""
        assert "::error::" in err
        assert "cannot parse contributors.toml" in err

    def test_codex_cwd_event_used_when_claude_env_absent(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
    ) -> None:
        root = self._setup_repo(tmp_path, '"alice@example.com" = "ja"\n')
        monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
        monkeypatch.delenv("CLAUDE_MD_OPERATOR_LANGUAGE", raising=False)
        monkeypatch.setattr(
            plc, "_git_identity", lambda _root: ("alice@example.com", None)
        )
        payload = json.dumps(
            {"hook_event_name": "SessionStart", "cwd": str(root), "source": "startup"}
        )
        monkeypatch.setattr("sys.stdin", io.StringIO(payload))
        rc = plc.main([])
        captured = capsys.readouterr()
        assert rc == 0
        assert captured.err == ""
        ctx = json.loads(captured.out)["hookSpecificOutput"]["additionalContext"]
        assert "'ja'" in ctx

    def test_malformed_stdin_fails_open(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
    ) -> None:
        root = self._setup_repo(tmp_path, '"alice@example.com" = "ja"\n')
        rc, out, err = self._run(
            monkeypatch, capsys, root, email="alice@example.com", payload="{not json"
        )
        assert rc == 0
        assert out == ""
        assert "::error::" in err
        assert "malformed stdin JSON" in err

    def test_nondict_stdin_fails_open(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
    ) -> None:
        # Valid JSON that is not an object hits the ValueError guard in
        # _read_event_stdin and fails open with the malformed-stdin diagnostic.
        root = self._setup_repo(tmp_path, '"alice@example.com" = "ja"\n')
        rc, out, err = self._run(
            monkeypatch, capsys, root, email="alice@example.com", payload="[1, 2]"
        )
        assert rc == 0
        assert out == ""
        assert "malformed stdin JSON" in err

    def test_unreadable_contributors_toml_fails_open(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
    ) -> None:
        # A contributors.toml that is a directory raises IsADirectoryError (an
        # OSError) on read; main fails open with the read diagnostic.
        gh = tmp_path / ".github"
        gh.mkdir()
        (gh / "contributors.toml").mkdir()
        rc, out, err = self._run(monkeypatch, capsys, tmp_path, email="alice@example.com")
        assert rc == 0
        assert out == ""
        assert "cannot read contributors.toml" in err


# ---------------------------------------------------------------------------
# _project_root
# ---------------------------------------------------------------------------


class TestProjectRoot:
    def test_env_var_wins(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", "/tmp/env-root")
        assert plc._project_root({"cwd": "/tmp/event-root"}) == Path("/tmp/env-root")

    def test_event_cwd_used_when_env_absent(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
        assert plc._project_root({"cwd": "/tmp/event-root"}) == Path("/tmp/event-root")

    def test_falls_back_to_cwd(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # No env var and no usable event cwd: the resolver falls back to the
        # process working directory.
        monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
        assert plc._project_root(None) == Path.cwd()
        assert plc._project_root({"hook_event_name": "SessionStart"}) == Path.cwd()


# ---------------------------------------------------------------------------
# _git_identity (real subprocess boundary)
# ---------------------------------------------------------------------------


class TestGitIdentity:
    def test_reads_local_git_config(self, tmp_path: Path) -> None:
        import subprocess

        subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
        subprocess.run(
            ["git", "-C", str(tmp_path), "config", "user.email", "x@example.com"],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(tmp_path), "config", "user.name", "X Y"], check=True
        )
        assert plc._git_identity(tmp_path) == ("x@example.com", "X Y")

    def test_missing_value_returns_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # A non-zero git exit (e.g. the key is unset) yields None for the field.
        class _Result:
            returncode = 1
            stdout = ""

        monkeypatch.setattr(plc.subprocess, "run", lambda *a, **k: _Result())
        assert plc._git_identity(Path()) == (None, None)

    def test_subprocess_error_returns_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # git not on PATH (OSError) degrades to None rather than raising.
        def _boom(*_a: object, **_k: object) -> None:
            raise OSError("git not found")

        monkeypatch.setattr(plc.subprocess, "run", _boom)
        assert plc._git_identity(Path()) == (None, None)
