"""Tests for ``scripts/title_policy.py``.

Refs #199; ``TestPropertyInvariants`` below is the narrow Hypothesis
pilot documented in ``docs/standards/workflow-script-quality.md`` O1.
"""

from __future__ import annotations

import tomllib

import pytest
import title_policy
from hypothesis import given
from hypothesis import strategies as st

pytestmark = pytest.mark.shard_policy


@pytest.fixture(autouse=True)
def _clear_body_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate every test from an ambient ``PR_BODY`` / ``ISSUE_BODY``.

    ``verify_title`` falls back to ``title_policy._body_from_env`` (which
    reads ``PR_BODY`` then ``ISSUE_BODY``) whenever it is called with an
    empty body and a non-trusted-bot author. The single-process pre-push
    preflight (``scripts/preflight_all.py``) exports ``PR_BODY`` for the body
    gates and then runs pytest in the same process, so without this fixture
    that ambient body would suppress (or spuriously raise) the type-fit
    finding and make these tests non-deterministic. In CI the body gates and
    the pytest matrix run in separate jobs, so the conflict is local-only;
    clearing the vars here keeps the tests deterministic in both. Refs #1451.
    """
    monkeypatch.delenv("PR_BODY", raising=False)
    monkeypatch.delenv("ISSUE_BODY", raising=False)


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
            "chore: coordinate non-ascii defense",
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

    def test_body_phrase_supplies_performance_signal(self) -> None:
        # The body escalates only on a multi-word performance phrase, not on a
        # lone word (#1424). "speed up" is in _PERFORMANCE_PHRASES.
        findings = title_policy.type_fit_findings(
            "fix(devcontainer): improve image setup",
            kind="issue",
            body="Fact: this is a clear speed up of devcontainer image setup.",
        )
        assert len(findings) == 1

    def test_resource_consumption_section_does_not_trip_type_fit(self) -> None:
        # The required boilerplate ## Resource Consumption section carries the
        # word "resource" but never describes the PR's own work; a chore PR
        # that merely carries it must not be forced onto a perf title. Refs #1413.
        body = (
            "## Summary\n\n- Bump a pinned dependency.\n\n"
            "## Resource Consumption\n\n"
            "- Elapsed (since previous PR or session start): 0:01:00\n"
            "- Total tokens: 1,000 (input 1 / output 1 / cache-create 1 / cache-read 1)\n"
            "- Cost (USD): $0.0100\n"
            "- Model(s): claude-opus-4-8\n"
        )
        assert (
            title_policy.type_fit_findings(
                "chore(deps): bump pinned dependency",
                kind="pull_request",
                body=body,
            )
            == []
        )

    def test_resource_wording_outside_the_section_still_trips(self) -> None:
        # Perf vocabulary in the PR's own prose still classifies the work,
        # even when the boilerplate section is also present and stripped.
        body = (
            "## Summary\n\n- Speed up the resource cache for faster startup.\n\n"
            "## Resource Consumption\n\n- Cost (USD): $0.0100\n"
        )
        findings = title_policy.type_fit_findings(
            "chore(x): tidy things", kind="pull_request", body=body
        )
        assert len(findings) == 1

    def test_strip_resource_section_stops_at_next_h2(self) -> None:
        body = (
            "## Resource Consumption\n\n- resource cost\n\n"
            "## Related Issue\n\nCloses #1\n"
        )
        stripped = title_policy._strip_resource_consumption_section(body)
        assert "Resource Consumption" not in stripped
        assert "## Related Issue" in stripped

    @pytest.mark.parametrize(
        "title",
        [
            "chore(harness): tidy operator notes",
            "feat(harness): add operator notes",
        ],
    )
    def test_lone_body_word_does_not_trip(self, title: str) -> None:
        # #1424 / #1054: a lone performance word in the body ("memory" here) is
        # too weak a signal and must not misclassify a non-performance title.
        findings = title_policy.type_fit_findings(
            title,
            kind="issue",
            body="This improves operator memory of past runs.",
        )
        assert findings == []


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


class TestPrTitleRefIsExempt:
    @pytest.mark.parametrize(
        "title",
        [
            "revert: undo prior change (#1122)",
            "revert(automerge): restore non-ascii label exemption (#1122)",
            "revert(scope): drop change (#203) (#213)",
        ],
    )
    def test_revert_titles_are_exempt(self, title: str) -> None:
        assert title_policy.pr_title_ref_is_exempt(title) is True

    @pytest.mark.parametrize(
        "title",
        [
            "fix(x): summary (#42)",
            "feat: add gate (#7)",
            # ``revert`` substring outside the type slot must not exempt.
            "fix(revert): summary (#9)",
            # Malformed shape parses to no type, so it stays banned.
            "revert this thing (#9)",
        ],
    )
    def test_non_revert_titles_are_not_exempt(self, title: str) -> None:
        assert title_policy.pr_title_ref_is_exempt(title) is False


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
                body="Fact: this is a clear speed up of devcontainer image setup.",
            )
            == 1
        )
        assert "title type does not fit" in capsys.readouterr().out

    def test_revert_pr_title_with_ref_exits_zero(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # A revert title may name the reverted PR/commit; the dedup ban
        # (#167 / #214) does not apply, but ASCII/naming still would.
        assert (
            title_policy.verify_title(
                "revert(automerge): restore label exemption (#1122)",
                kind="pull_request",
            )
            == 0
        )
        out = capsys.readouterr().out
        assert (
            "OK: pull_request title is ASCII-only and follows naming convention."
            in out
        )

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


class TestTrustedBotTypeFitCarveOut:
    """#1127: a trusted-bot author drops the relayed body from type-fit.

    Dependabot relays upstream release notes whose performance wording must
    not mis-classify a correct ``chore(deps):`` title as performance work.
    Title-only checks still apply to bots. The body carries a performance
    *phrase* ("build cache") so that a non-bot author still trips the gate --
    that contrast is what proves the carve-out drops the bot body (#1424
    narrowed body signal to phrases, so a lone word no longer trips either).
    """

    _DEPENDABOT_TITLE = "chore(deps): bump actions/setup-go from 5.6.0 to 6.4.0"
    _PERF_BODY = "Update the Go module build cache to use go.mod."

    def test_trusted_bot_body_does_not_trip_type_fit(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert (
            title_policy.verify_title(
                self._DEPENDABOT_TITLE,
                kind="pull_request",
                body=self._PERF_BODY,
                author="dependabot[bot]",
            )
            == 0
        )
        assert "title type does not fit" not in capsys.readouterr().out

    def test_non_bot_author_body_still_trips_type_fit(self) -> None:
        assert (
            title_policy.verify_title(
                self._DEPENDABOT_TITLE,
                kind="pull_request",
                body=self._PERF_BODY,
                author="octocat",
            )
            == 1
        )

    def test_trusted_bot_perf_signal_in_title_still_fails(self) -> None:
        # The carve-out drops only the body; a perf signal in the bot's own
        # title is still its own authored content and must be checked.
        assert (
            title_policy.verify_title(
                "chore(deps): cache image builds",
                kind="pull_request",
                body="",
                author="dependabot[bot]",
            )
            == 1
        )


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
