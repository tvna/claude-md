"""Tests for ``scripts/plan_language_context.py`` (SessionStart hook).

The ``scripts/`` directory is added to ``sys.path`` via the ``pythonpath``
key under ``[tool.pytest.ini_options]`` in ``pyproject.toml``.

Mirrors the table-driven style of ``tests/test_preflight_non_ascii.py``.
Pure functions get focused unit tests; the file-IO boundary in
:func:`plan_language_context.main` is exercised by writing fixture
files into a ``tmp_path`` repo root and pointing the hook at it via
the ``CLAUDE_PROJECT_DIR`` env var.

Refs #211.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import plan_language_context as plc


# ---------------------------------------------------------------------------
# parse_codeowners
# ---------------------------------------------------------------------------


class TestParseCodeowners:
    def test_skips_comments_and_blank_lines(self) -> None:
        text = "\n".join(
            [
                "# top comment",
                "",
                "   ",
                "*  @alice",
                "    # indented comment",
                "docs/  @bob @alice",
            ]
        )
        assert plc.parse_codeowners(text) == [
            ("*", ["@alice"]),
            ("docs/", ["@bob", "@alice"]),
        ]

    def test_keeps_at_prefix(self) -> None:
        rules = plc.parse_codeowners("*  @tvna")
        assert rules == [("*", ["@tvna"])]

    def test_drops_non_at_tokens(self) -> None:
        # An email-style entry has no leading '@'; CODEOWNERS allows it
        # but our resolver only matches handle-prefixed entries.
        rules = plc.parse_codeowners("*  user@example.com @alice")
        assert rules == [("*", ["@alice"])]

    def test_pattern_without_owners_is_dropped(self) -> None:
        # CODEOWNERS treats `path/` with no owner as "unset"; for our
        # purposes there's no handle to count, so the line is skipped.
        assert plc.parse_codeowners("docs/") == []

    def test_empty_input(self) -> None:
        assert plc.parse_codeowners("") == []


# ---------------------------------------------------------------------------
# primary_owner
# ---------------------------------------------------------------------------


class TestPrimaryOwner:
    def test_single_owner_repo(self) -> None:
        rules = [("a", ["@tvna"]), ("b", ["@tvna"])]
        assert plc.primary_owner(rules) == "@tvna"

    def test_most_frequent_wins(self) -> None:
        rules = [
            ("a", ["@alice"]),
            ("b", ["@bob"]),
            ("c", ["@alice"]),
        ]
        assert plc.primary_owner(rules) == "@alice"

    def test_tie_broken_by_first_appearance(self) -> None:
        rules = [("a", ["@alice"]), ("b", ["@bob"])]
        assert plc.primary_owner(rules) == "@alice"

    def test_empty_rules_returns_none(self) -> None:
        assert plc.primary_owner([]) is None

    def test_multi_owner_line_counted_per_handle(self) -> None:
        rules = [
            ("a", ["@alice", "@bob"]),
            ("b", ["@bob"]),
        ]
        assert plc.primary_owner(rules) == "@bob"


# ---------------------------------------------------------------------------
# load_owner_languages
# ---------------------------------------------------------------------------


class TestLoadOwnerLanguages:
    def test_happy_path(self) -> None:
        text = '"@tvna": ja\n"@alice": en\n'
        assert plc.load_owner_languages(text) == {"@tvna": "ja", "@alice": "en"}

    def test_empty_text(self) -> None:
        assert plc.load_owner_languages("") == {}

    def test_whitespace_only(self) -> None:
        assert plc.load_owner_languages("   \n  \n") == {}

    def test_yaml_null(self) -> None:
        assert plc.load_owner_languages("---\n") == {}

    def test_non_mapping_top_level_raises(self) -> None:
        with pytest.raises(ValueError, match="must be a mapping"):
            plc.load_owner_languages("- one\n- two\n")

    def test_drops_non_string_values(self) -> None:
        # ``ja`` -> string, ``42`` -> int (dropped), nested mapping dropped.
        text = '"@tvna": ja\n"@bot": 42\n"@x":\n  nested: y\n'
        assert plc.load_owner_languages(text) == {"@tvna": "ja"}


# ---------------------------------------------------------------------------
# resolve_language
# ---------------------------------------------------------------------------


class TestResolveLanguage:
    def test_happy_path(self) -> None:
        codeowners = "*  @tvna\n"
        owners = '"@tvna": ja\n'
        assert plc.resolve_language(codeowners, owners) == ("@tvna", "ja")

    def test_owner_not_in_owners_yaml(self) -> None:
        owner, iso = plc.resolve_language("*  @nobody\n", '"@tvna": ja\n')
        assert owner == "@nobody"
        assert iso is None

    def test_empty_codeowners(self) -> None:
        assert plc.resolve_language("", '"@tvna": ja\n') == (None, None)


# ---------------------------------------------------------------------------
# build_context_message
# ---------------------------------------------------------------------------


class TestBuildContextMessage:
    def test_contains_plan_path_and_iso(self) -> None:
        msg = plc.build_context_message("@tvna", "ja")
        assert "/root/.claude/plans/" in msg
        assert "'ja'" in msg
        assert "@tvna" in msg

    def test_contains_github_carveout(self) -> None:
        msg = plc.build_context_message("@tvna", "ja")
        # The carve-out must name the tool prefix AND the ASCII rule so
        # the model cannot misread the policy as relaxing Layer 2.5.
        assert "mcp__github__" in msg
        assert "ASCII" in msg
        assert "preflight_non_ascii.py" in msg

    def test_contains_normative_must(self) -> None:
        # Refs #269: descriptive "write ... in" wording let agents drift
        # back to English; the message must read as binding.
        msg = plc.build_context_message("@tvna", "ja")
        assert "MUST" in msg

    def test_contains_self_correction_rule(self) -> None:
        # Refs #269: mid-output drift must trigger a STOP-and-re-emit,
        # not a silent continuation in the wrong language.
        msg = plc.build_context_message("@tvna", "ja")
        assert "STOP" in msg
        assert "drift" in msg


# ---------------------------------------------------------------------------
# decide
# ---------------------------------------------------------------------------


class TestDecide:
    def test_happy_path_emits_session_start_output(self) -> None:
        out = plc.decide("*  @tvna\n", '"@tvna": ja\n')
        assert out is not None
        assert out["hookSpecificOutput"]["hookEventName"] == "SessionStart"
        assert "ja" in out["hookSpecificOutput"]["additionalContext"]

    def test_unmapped_owner_returns_none(self) -> None:
        assert plc.decide("*  @nobody\n", '"@tvna": ja\n') is None

    def test_empty_codeowners_returns_none(self) -> None:
        assert plc.decide("", '"@tvna": ja\n') is None

    def test_empty_owners_yaml_returns_none(self) -> None:
        assert plc.decide("*  @tvna\n", "") is None


# ---------------------------------------------------------------------------
# main (file-IO boundary)
# ---------------------------------------------------------------------------


class TestMain:
    def _setup_repo(
        self,
        tmp_path: Path,
        codeowners: str | None,
        owners_yaml: str | None,
    ) -> Path:
        """Build a fake repo root with optional config files."""
        gh = tmp_path / ".github"
        gh.mkdir()
        if codeowners is not None:
            (gh / "CODEOWNERS").write_text(codeowners, encoding="utf-8")
        if owners_yaml is not None:
            (gh / "owners.yaml").write_text(owners_yaml, encoding="utf-8")
        return tmp_path

    def _run(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        root: Path,
    ) -> tuple[int, str, str]:
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(root))
        rc = plc.main([])
        captured = capsys.readouterr()
        return rc, captured.out, captured.err

    def test_happy_path_emits_session_start_json(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
    ) -> None:
        root = self._setup_repo(tmp_path, "*  @tvna\n", '"@tvna": ja\n')
        rc, out, err = self._run(monkeypatch, capsys, root)
        assert rc == 0
        assert err == ""
        decision = json.loads(out)
        assert decision["hookSpecificOutput"]["hookEventName"] == "SessionStart"
        ctx = decision["hookSpecificOutput"]["additionalContext"]
        assert "'ja'" in ctx
        assert "mcp__github__" in ctx

    def test_missing_codeowners_fails_open(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
    ) -> None:
        root = self._setup_repo(tmp_path, None, '"@tvna": ja\n')
        rc, out, err = self._run(monkeypatch, capsys, root)
        assert rc == 0
        assert out == ""
        assert "::error::" in err
        assert "cannot read config" in err

    def test_missing_owners_yaml_fails_open(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
    ) -> None:
        root = self._setup_repo(tmp_path, "*  @tvna\n", None)
        rc, out, err = self._run(monkeypatch, capsys, root)
        assert rc == 0
        assert out == ""
        assert "::error::" in err

    def test_malformed_yaml_fails_open(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
    ) -> None:
        root = self._setup_repo(tmp_path, "*  @tvna\n", "not: yaml: [::\n")
        rc, out, err = self._run(monkeypatch, capsys, root)
        assert rc == 0
        assert out == ""
        assert "::error::" in err
        assert "cannot parse owners.yaml" in err

    def test_unmapped_owner_emits_nothing(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
    ) -> None:
        root = self._setup_repo(tmp_path, "*  @nobody\n", '"@tvna": ja\n')
        rc, out, err = self._run(monkeypatch, capsys, root)
        assert rc == 0
        assert out == ""
        assert err == ""
