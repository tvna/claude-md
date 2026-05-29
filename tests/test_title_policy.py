"""Tests for ``scripts/title_policy.py``.

Refs #199 -- ``TestPropertyInvariants`` below is the narrow Hypothesis
pilot documented in ``docs/standards/workflow-script-quality.md`` O1.
"""

from __future__ import annotations

import pytest
import title_policy
import tomllib
from hypothesis import given
from hypothesis import strategies as st

pytestmark = pytest.mark.shard_policy


class TestTitlePolicyConfig:
    def test_config_lives_under_github(self) -> None:
        assert title_policy.TITLE_POLICY_CONFIG.parts[-2:] == (
            ".github",
            "title-policy.toml",
        )

    def test_allowed_types_are_loaded_from_toml(self) -> None:
        data = tomllib.loads(title_policy.TITLE_POLICY_CONFIG.read_text(encoding="utf-8"))
        configured = data["title_policy"]["types"]
        assert configured == title_policy.allowed_types_csv().split(", ")

    def test_scope_pattern_is_loaded_from_toml(self) -> None:
        data = tomllib.loads(title_policy.TITLE_POLICY_CONFIG.read_text(encoding="utf-8"))
        assert data["title_policy"]["scope_pattern"] == title_policy._SCOPE_PATTERN


class TestIsAsciiTitle:
    @pytest.mark.parametrize(
        "title",
        [
            "",
            "ci(github): enable title policy validation",
            "fix: require Refs #155 in PR body",
            "docs: update ruleset smoke test",
        ],
    )
    def test_ascii_titles_pass(self, title: str) -> None:
        assert title_policy.is_ascii_title(title) is True

    @pytest.mark.parametrize(
        "title",
        [
            "ci: reject 日本語 titles",
            "ci: reject emoji \U0001f6a8",
            "ci: reject zero\u200bwidth",
            "ci: reject rtl \u202eoverride",
            "ci: reject fullwidth ＡＢＣ",
        ],
    )
    def test_non_ascii_titles_fail(self, title: str) -> None:
        assert title_policy.is_ascii_title(title) is False


class TestFollowsNamingConvention:
    @pytest.mark.parametrize(
        "title",
        [
            "fix(non-ascii): notify title policy violations",
            "chore: regenerate agent instructions",
            "docs(rulesets): update smoke tests",
            "fix(ruleset-drift): align issue titles with policy",
        ],
    )
    def test_pr_titles_pass(self, title: str) -> None:
        assert (
            title_policy.follows_naming_convention(
                title,
                kind="pull_request",
            )
            is True
        )

    @pytest.mark.parametrize(
        "title",
        [
            "Notify title policy violations from non-ASCII scan #163",
            "fix(non_ascii): notify title policy violations (#163)",
            "fix(non-ascii):",
        ],
    )
    def test_pr_titles_fail(self, title: str) -> None:
        assert (
            title_policy.follows_naming_convention(
                title,
                kind="pull_request",
            )
            is False
        )

    @pytest.mark.parametrize(
        "title",
        [
            "fix(non-ascii): notify title policy violations",
            "tracking: coordinate non-ascii defense",
        ],
    )
    def test_issue_titles_pass(self, title: str) -> None:
        assert (
            title_policy.follows_naming_convention(title, kind="issue")
            is True
        )

    @pytest.mark.parametrize(
        "title",
        [
            "Notify title policy violations",
            "fix(non-ascii):",
            "[legacy] title format",
        ],
    )
    def test_issue_titles_fail(self, title: str) -> None:
        assert (
            title_policy.follows_naming_convention(title, kind="issue")
            is False
        )


class TestTypeFitFindings:
    @pytest.mark.parametrize(
        "title",
        [
            "perf(devcontainer): cache image builds",
            "perf(agent): reduce startup latency",
            "docs(devcontainer): document prebuilt image cache",
            "ci(devcontainer): cache image build workflow",
            "build(devcontainer): cache image builds",
            "fix(devcontainer): fix image build cache regression",
            "feat(performance): add benchmark metrics",
        ],
    )
    def test_performance_adjacent_titles_can_fit(self, title: str) -> None:
        assert title_policy.type_fit_findings(title, kind="pull_request") == []

    @pytest.mark.parametrize(
        "title",
        [
            "fix(devcontainer): cache image builds",
            "feat(devcontainer): speed up prebuilt images",
            "chore(devcontainer): reduce startup latency",
        ],
    )
    def test_performance_mismatch_returns_finding(self, title: str) -> None:
        findings = title_policy.type_fit_findings(title, kind="pull_request")
        assert len(findings) == 1
        assert "performance" in findings[0].reason
        assert "perf" in findings[0].expected_types

    def test_body_can_supply_performance_signal(self) -> None:
        findings = title_policy.type_fit_findings(
            "fix(devcontainer): improve image setup",
            kind="issue",
            body="Fact: this speeds up devcontainer startup by caching images.",
        )
        assert len(findings) == 1


class TestPrTitleHasIssueRef:
    @pytest.mark.parametrize(
        "title",
        [
            "fix(x): summary (#1)",
            "fix(x): summary (#42)",
            "fix(x): summary (#203) (#213)",
            "feat: drop (#999) anywhere in the line",
        ],
    )
    def test_titles_with_issue_ref_detected(self, title: str) -> None:
        assert title_policy.pr_title_has_issue_ref(title) is True

    @pytest.mark.parametrize(
        "title",
        [
            "fix(x): summary",
            "feat(harness): add Issue Forms aligned with triage axes",
            "docs: mention #167 in body text (no parens)",
            "ci: empty parens () should not match",
            "ci: (#abc) is not a digit ref",
        ],
    )
    def test_titles_without_issue_ref_pass(self, title: str) -> None:
        assert title_policy.pr_title_has_issue_ref(title) is False


class TestDescribeNonAscii:
    def test_reports_codepoint_positions(self) -> None:
        assert title_policy.describe_non_ascii("A\u200bB\u202e") == [
            "index 1: U+200B",
            "index 3: U+202E",
        ]

    def test_limit(self) -> None:
        assert title_policy.describe_non_ascii("あいう", limit=2) == [
            "index 0: U+3042",
            "index 1: U+3044",
        ]


class TestVerifyTitle:
    def test_ascii_exit_zero(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert title_policy.verify_title("docs: update", kind="issue") == 0
        out = capsys.readouterr().out
        assert "OK: issue title is ASCII-only and follows naming convention." in out

    def test_non_ascii_exit_one(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert title_policy.verify_title(
            "ci: reject zero\u200bwidth",
            kind="pull_request",
        ) == 1
        out = capsys.readouterr().out
        assert "::error::pull_request title must be ASCII-only" in out
        assert "U+200B" in out

    def test_pr_without_issue_number_exits_zero(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert (
            title_policy.verify_title(
                "fix(non-ascii): notify title policy violations",
                kind="pull_request",
            )
            == 0
        )
        out = capsys.readouterr().out
        assert (
            "OK: pull_request title is ASCII-only and follows naming convention."
            in out
        )

    def test_pr_with_issue_ref_in_title_exits_one(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert (
            title_policy.verify_title(
                "fix(harness): summary (#203)",
                kind="pull_request",
            )
            == 1
        )
        out = capsys.readouterr().out
        assert (
            "::error::pull_request title must not contain issue references "
            "like (#NNN)" in out
        )

    def test_type_fit_mismatch_exits_one(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        assert (
            title_policy.verify_title(
                "fix(devcontainer): cache image builds",
                kind="pull_request",
            )
            == 1
        )
        out = capsys.readouterr().out
        assert "::error::pull_request title type does not fit the work" in out
        assert "Expected title type" in out

    def test_body_participates_in_type_fit_check(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        assert (
            title_policy.verify_title(
                "fix(devcontainer): improve image setup",
                kind="issue",
                body="Fact: this speeds up startup by caching images.",
            )
            == 1
        )
        assert "title type does not fit" in capsys.readouterr().out

    def test_issue_with_issue_ref_in_title_still_passes(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert (
            title_policy.verify_title(
                "fix(harness): summary (#203)",
                kind="issue",
            )
            == 0
        )
        out = capsys.readouterr().out
        assert "OK: issue title is ASCII-only and follows naming convention." in out


class TestPropertyInvariants:
    """Hypothesis pilot for the four pure parsers in ``title_policy``.

    The pilot is documented in ``docs/standards/workflow-script-quality.md``
    O1 (#199). Each property names the invariant it pins so a failure
    report points at the spec, not the implementation detail.
    """

    @given(st.text())
    def test_is_ascii_title_matches_str_isascii(self, title: str) -> None:
        assert title_policy.is_ascii_title(title) is title.isascii()

    @given(st.text())
    def test_has_ref_iff_findall_nonempty(self, title: str) -> None:
        assert title_policy.pr_title_has_issue_ref(title) is bool(
            title_policy.pr_title_issue_refs(title)
        )

    @given(st.text())
    def test_strip_removes_every_issue_ref(self, title: str) -> None:
        stripped = title_policy.pr_title_strip_issue_refs(title)
        assert title_policy.pr_title_has_issue_ref(stripped) is False
        assert title_policy.pr_title_issue_refs(stripped) == []

    @given(st.text())
    def test_strip_is_idempotent(self, title: str) -> None:
        once = title_policy.pr_title_strip_issue_refs(title)
        twice = title_policy.pr_title_strip_issue_refs(once)
        assert once == twice


class TestCLI:
    def test_uses_title_env(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setenv("TITLE", "ci: ascii only")
        assert title_policy.main(["verify", "--kind", "pull_request"]) == 0
        assert (
            "OK: pull_request title is ASCII-only and follows naming convention."
            in capsys.readouterr().out
        )

    def test_title_arg_overrides_env(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setenv("TITLE", "ci: ascii only")
        assert (
            title_policy.main(
                [
                    "verify",
                    "--kind",
                    "issue",
                    "--title",
                    "bad \U0001f6a8",
                ]
            )
            == 1
        )
        assert "U+1F6A8" in capsys.readouterr().out
