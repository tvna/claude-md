"""Tests for ``scripts/body_policy.py``.

The ``scripts/`` directory is added to ``sys.path`` via the
``pythonpath`` key under ``[tool.pytest.ini_options]`` in
``pyproject.toml``.
"""

from __future__ import annotations

from pathlib import Path

import body_policy
import pytest

pytestmark = pytest.mark.shard_policy
# ---------------------------------------------------------------------------
# Fixture bodies
# ---------------------------------------------------------------------------


_CANONICAL_PR_BODY = """## Summary

- one-liner

## Related Issue

Refs #205

## Facts

- one fact

## Assumptions

- one assumption

## Risk & blast radius

- isolated to CI

## Rollback

- git revert <sha>

## Verification

- [x] tests pass

## Checklist

- [x] item
"""

_CANONICAL_ISSUE_BODY_H2 = """## Scope

prose

## Facts

- Fact: one

## Proposed work

- step

## Verification

- run pytest

## Acceptance criteria

- [ ] done
"""

_CANONICAL_ISSUE_BODY_H3 = """### Scope

prose

### Facts

- Fact: one

### Proposed work

- step

### Verification

- run pytest

### Acceptance criteria

- [ ] done
"""

_CANONICAL_TRACKING_BODY = """## Scope

umbrella

## Facts

- Fact: one

## Initial child issues

- #100

## Completion criteria

- [ ] No open child issues remain
"""


# ---------------------------------------------------------------------------
# extract_headings
# ---------------------------------------------------------------------------


class TestExtractHeadings:
    def test_empty(self) -> None:
        assert body_policy.extract_headings("") == []

    def test_h2_only(self) -> None:
        assert body_policy.extract_headings("## Scope\n\nprose\n") == [
            (2, "Scope"),
        ]

    def test_h3_only(self) -> None:
        assert body_policy.extract_headings("### Facts\n\n- f\n") == [
            (3, "Facts"),
        ]

    def test_mixed_levels(self) -> None:
        body = "## A\n\n### B\n\n## C\n"
        assert body_policy.extract_headings(body) == [
            (2, "A"),
            (3, "B"),
            (2, "C"),
        ]

    def test_h1_and_h4_ignored(self) -> None:
        body = "# Top\n\n## Keep\n\n#### Too deep\n"
        assert body_policy.extract_headings(body) == [(2, "Keep")]

    def test_html_commented_heading_ignored(self) -> None:
        body = "<!-- ## Hidden -->\n## Visible\n"
        assert body_policy.extract_headings(body) == [(2, "Visible")]

    def test_trailing_colon_stripped(self) -> None:
        assert body_policy.extract_headings("## Scope:\n") == [(2, "Scope")]

    def test_trailing_whitespace_stripped(self) -> None:
        assert body_policy.extract_headings("##  Scope   \n") == [
            (2, "Scope"),
        ]

    def test_crlf_normalised(self) -> None:
        body = "## Scope\r\n\r\nprose\r\n"
        assert body_policy.extract_headings(body) == [(2, "Scope")]


# ---------------------------------------------------------------------------
# required_sections
# ---------------------------------------------------------------------------


class TestRequiredSections:
    def test_pull_request_fixed_list(self) -> None:
        assert body_policy.required_sections(
            "pull_request", body=""
        ) == (
            "Facts",
            "Assumptions",
            "Risk & blast radius",
            "Rollback",
            "Verification",
            "Checklist",
        )

    def test_issue_common(self) -> None:
        assert body_policy.required_sections(
            "issue", body=_CANONICAL_ISSUE_BODY_H2
        ) == (
            "Scope",
            "Facts",
            "Proposed work",
            "Verification",
            "Acceptance criteria",
        )

    def test_issue_tracking_switch(self) -> None:
        assert body_policy.required_sections(
            "issue", body=_CANONICAL_TRACKING_BODY
        ) == (
            "Scope",
            "Facts",
            "Initial child issues",
            "Completion criteria",
        )

    def test_tracking_marker_case_insensitive(self) -> None:
        body = "## scope\n## initial CHILD issues\n"
        assert body_policy.required_sections("issue", body=body)[2] == (
            "Initial child issues"
        )

    def test_tracking_marker_inside_html_comment_ignored(self) -> None:
        body = (
            "<!-- ## Initial child issues -->\n"
            "## Scope\n\n## Facts\n\n## Proposed work\n"
            "\n## Verification\n\n## Acceptance criteria\n"
        )
        assert body_policy.required_sections("issue", body=body) == (
            "Scope",
            "Facts",
            "Proposed work",
            "Verification",
            "Acceptance criteria",
        )

    def test_unknown_kind(self) -> None:
        with pytest.raises(ValueError):
            body_policy.required_sections("comment", body="")


# ---------------------------------------------------------------------------
# missing_sections
# ---------------------------------------------------------------------------


class TestMissingSections:
    def test_all_present(self) -> None:
        headings = [(2, "Scope"), (2, "Facts")]
        assert (
            body_policy.missing_sections(("Scope", "Facts"), headings) == []
        )

    @pytest.mark.parametrize(
        "drop",
        list(body_policy._PR_REQUIRED),
    )
    def test_each_pr_section_missing(self, drop: str) -> None:
        headings = [
            (2, name) for name in body_policy._PR_REQUIRED if name != drop
        ]
        assert (
            body_policy.missing_sections(body_policy._PR_REQUIRED, headings)
            == [drop]
        )

    def test_case_sensitive_match(self) -> None:
        # "facts" must not satisfy "Facts".
        headings = [(2, "facts")]
        assert body_policy.missing_sections(("Facts",), headings) == [
            "Facts",
        ]

    def test_level_irrelevant_for_match(self) -> None:
        headings = [(3, "Scope")]
        assert body_policy.missing_sections(("Scope",), headings) == []

    def test_and_heading_satisfies_ampersand_required(self) -> None:
        # "Risk and blast radius" (the AI agent default) satisfies the
        # canonical "Risk & blast radius" required slot. Refs #332.
        headings = [(2, "Risk and blast radius")]
        assert body_policy.missing_sections(
            ("Risk & blast radius",), headings
        ) == []

    def test_ampersand_heading_satisfies_and_required(self) -> None:
        # The reverse direction also matches (defensive symmetry).
        headings = [(2, "Risk & blast radius")]
        assert body_policy.missing_sections(
            ("Risk and blast radius",), headings
        ) == []

    def test_ampersand_normalization_preserves_case(self) -> None:
        # Case sensitivity is still enforced after & normalization.
        headings = [(2, "risk and blast radius")]
        assert body_policy.missing_sections(
            ("Risk & blast radius",), headings
        ) == ["Risk & blast radius"]


# ---------------------------------------------------------------------------
# _normalize_heading
# ---------------------------------------------------------------------------


class TestNormalizeHeading:
    def test_replaces_ampersand_with_and(self) -> None:
        assert (
            body_policy._normalize_heading("Risk & blast radius")
            == "Risk and blast radius"
        )

    def test_handles_missing_whitespace_around_ampersand(self) -> None:
        assert (
            body_policy._normalize_heading("Risk&blast radius")
            == "Risk and blast radius"
        )

    def test_preserves_case(self) -> None:
        assert body_policy._normalize_heading("Facts") == "Facts"

    def test_leaves_unrelated_text_unchanged(self) -> None:
        assert (
            body_policy._normalize_heading("Verification")
            == "Verification"
        )

    def test_idempotent_on_and_form(self) -> None:
        # Already in the "and" form: no change.
        assert (
            body_policy._normalize_heading("Risk and blast radius")
            == "Risk and blast radius"
        )


# ---------------------------------------------------------------------------
# is_within_gate_window
# ---------------------------------------------------------------------------


class TestGateWindow:
    def test_before_cutoff_returns_false(self) -> None:
        assert (
            body_policy.is_within_gate_window(
                "2026-05-22T00:00:00Z", "2026-05-23T00:00:00Z"
            )
            is False
        )

    def test_at_cutoff_returns_true(self) -> None:
        assert (
            body_policy.is_within_gate_window(
                "2026-05-23T00:00:00Z", "2026-05-23T00:00:00Z"
            )
            is True
        )

    def test_after_cutoff_returns_true(self) -> None:
        assert (
            body_policy.is_within_gate_window(
                "2026-05-24T00:00:00Z", "2026-05-23T00:00:00Z"
            )
            is True
        )

    def test_missing_created_at_defaults_to_enforce(self) -> None:
        assert (
            body_policy.is_within_gate_window("", "2026-05-23T00:00:00Z")
            is True
        )

    def test_missing_cutoff_defaults_to_enforce(self) -> None:
        assert (
            body_policy.is_within_gate_window("2026-05-22T00:00:00Z", "")
            is True
        )

    def test_unparseable_inputs_default_to_enforce(self) -> None:
        assert (
            body_policy.is_within_gate_window("yesterday", "tomorrow") is True
        )


# ---------------------------------------------------------------------------
# _verify -- PR
# ---------------------------------------------------------------------------


class TestVerifyPRBody:
    def test_canonical_passes(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert (
            body_policy._verify("pull_request", _CANONICAL_PR_BODY) == 0
        )
        out = capsys.readouterr().out
        assert (
            "OK: pull_request body contains all required sections." in out
        )

    def test_and_form_heading_passes(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # PR body that writes "## Risk and blast radius" instead of
        # "## Risk & blast radius" still satisfies the gate. Refs #332.
        body = _CANONICAL_PR_BODY.replace(
            "## Risk & blast radius", "## Risk and blast radius"
        )
        assert body_policy._verify("pull_request", body) == 0
        assert (
            "OK: pull_request body contains all required sections."
            in capsys.readouterr().out
        )

    @pytest.mark.parametrize("drop", list(body_policy._PR_REQUIRED))
    def test_per_section_failure(
        self, drop: str, capsys: pytest.CaptureFixture[str]
    ) -> None:
        broken = _CANONICAL_PR_BODY.replace(f"## {drop}", f"## NOT-{drop}")
        assert body_policy._verify("pull_request", broken) == 1
        out = capsys.readouterr().out
        assert (
            f"::error::pull_request body is missing required section: "
            f"## {drop} (or ### {drop})." in out
        )


# ---------------------------------------------------------------------------
# _verify -- issue
# ---------------------------------------------------------------------------


class TestVerifyIssueBody:
    def test_h2_canonical_passes(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert body_policy._verify("issue", _CANONICAL_ISSUE_BODY_H2) == 0
        assert (
            "OK: issue body contains all required sections."
            in capsys.readouterr().out
        )

    def test_h3_canonical_passes(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert body_policy._verify("issue", _CANONICAL_ISSUE_BODY_H3) == 0
        assert (
            "OK: issue body contains all required sections."
            in capsys.readouterr().out
        )

    def test_tracking_canonical_passes(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert body_policy._verify("issue", _CANONICAL_TRACKING_BODY) == 0
        assert (
            "OK: issue body contains all required sections."
            in capsys.readouterr().out
        )

    @pytest.mark.parametrize("drop", list(body_policy._ISSUE_COMMON_REQUIRED))
    def test_common_per_section_failure(
        self, drop: str, capsys: pytest.CaptureFixture[str]
    ) -> None:
        broken = _CANONICAL_ISSUE_BODY_H2.replace(
            f"## {drop}", f"## NOT-{drop}"
        )
        assert body_policy._verify("issue", broken) == 1
        out = capsys.readouterr().out
        assert (
            f"::error::issue body is missing required section: "
            f"## {drop} (or ### {drop})." in out
        )

    def test_tracking_missing_initial_children(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Remove the marker entirely so the body falls back to the common
        # set, which is missing Proposed work / Acceptance criteria.
        broken = _CANONICAL_TRACKING_BODY.replace(
            "Initial child issues", "Children list"
        ).replace("Completion criteria", "Done when")
        assert body_policy._verify("issue", broken) == 1
        out = capsys.readouterr().out
        assert "missing required section: ## Proposed work" in out
        assert "missing required section: ## Acceptance criteria" in out


# ---------------------------------------------------------------------------
# _verify -- bypass paths
# ---------------------------------------------------------------------------


class TestTrustedBotBypass:
    def test_dependabot_passes_with_empty_body(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert (
            body_policy._verify(
                "pull_request", "", author="dependabot[bot]"
            )
            == 0
        )
        assert (
            "skipped: trusted bot author (dependabot[bot])"
            in capsys.readouterr().out
        )

    def test_unknown_bot_not_bypassed(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert (
            body_policy._verify(
                "pull_request", "", author="renovate[bot]"
            )
            == 1
        )


class TestGateCutoffShortCircuit:
    def test_before_cutoff_skips(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert (
            body_policy._verify(
                "issue",
                "",
                created_at="2026-05-22T00:00:00Z",
                cutoff="2026-05-23T00:00:00Z",
            )
            == 0
        )
        assert "predates gate cutoff" in capsys.readouterr().out

    def test_after_cutoff_enforces(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert (
            body_policy._verify(
                "issue",
                "",
                created_at="2026-06-01T00:00:00Z",
                cutoff="2026-05-23T00:00:00Z",
            )
            == 1
        )

    def test_missing_cutoff_enforces(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert (
            body_policy._verify(
                "issue", "", created_at="2026-05-22T00:00:00Z", cutoff=""
            )
            == 1
        )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


class TestCLI:
    def test_pr_body_env_var(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setenv("PR_BODY", _CANONICAL_PR_BODY)
        monkeypatch.delenv("BODY_POLICY_CUTOFF", raising=False)
        assert (
            body_policy.main(["verify", "--kind", "pull_request"]) == 0
        )
        assert (
            "OK: pull_request body contains all required sections."
            in capsys.readouterr().out
        )

    def test_issue_body_env_var(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setenv("ISSUE_BODY", _CANONICAL_ISSUE_BODY_H3)
        monkeypatch.delenv("BODY_POLICY_CUTOFF", raising=False)
        assert body_policy.main(["verify", "--kind", "issue"]) == 0
        assert (
            "OK: issue body contains all required sections."
            in capsys.readouterr().out
        )

    def test_body_file_overrides_env(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setenv("PR_BODY", "this should be ignored")
        body_file = tmp_path / "body.md"
        body_file.write_text(_CANONICAL_PR_BODY, encoding="utf-8")
        assert (
            body_policy.main(
                [
                    "verify",
                    "--kind",
                    "pull_request",
                    "--body-file",
                    str(body_file),
                ]
            )
            == 0
        )
        assert (
            "OK: pull_request body contains all required sections."
            in capsys.readouterr().out
        )

    def test_author_arg_bypasses(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setenv("PR_BODY", "")
        assert (
            body_policy.main(
                [
                    "verify",
                    "--kind",
                    "pull_request",
                    "--author",
                    "dependabot[bot]",
                ]
            )
            == 0
        )
        assert (
            "skipped: trusted bot author (dependabot[bot])"
            in capsys.readouterr().out
        )

    def test_cutoff_env_var_skips_back_catalog(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setenv("PR_BODY", "")
        monkeypatch.setenv("PR_CREATED_AT", "2026-05-22T00:00:00Z")
        monkeypatch.setenv("BODY_POLICY_CUTOFF", "2026-05-23T00:00:00Z")
        assert (
            body_policy.main(["verify", "--kind", "pull_request"]) == 0
        )
        assert "predates gate cutoff" in capsys.readouterr().out

    def test_missing_kind_errors(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with pytest.raises(SystemExit):
            body_policy.main(["verify"])


# ---------------------------------------------------------------------------
# ASCII contract
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Post-2026-05-26 PR shape: Verification command/result pairs
# ---------------------------------------------------------------------------


_NEW_SHAPE_VERIFICATION_OK = """## Verification

- command: `pytest -q`
  result: `exit 0 (684 passed)`
- command: `python3 scripts/body_policy.py verify --kind pull_request`
  result: `OK: pull_request body contains all required sections.`
"""

_NEW_SHAPE_CHECKLIST_OK = """## Checklist

### Bootstrap

- [ ] Facts vs Assumptions split is honest
- [ ] Risk assessed; Rollback runnable

### After-merge (CI)

- [ ] `pytest -q` exits 0 (paired in Verification above)
- [ ] CI green on the merge commit

### Post-merge (auto-retro signal)

- [ ] Linked issue closed by the merge
- [ ] auto-retro issue opened
"""

_AGENT_ATTRIBUTION_FOOTER = (
    "_Generated by [Codex](https://openai.com/codex) using GPT-5._"
)


_NEW_SHAPE_PR_BODY = """## Summary

- one-liner

## Related Issue

Refs #205

## Facts

- one fact

## Assumptions

- one assumption

## Risk & blast radius

- isolated

## Rollback

- git revert <sha>

""" + _NEW_SHAPE_VERIFICATION_OK + "\n" + _NEW_SHAPE_CHECKLIST_OK
_NEW_SHAPE_PR_BODY += "\n" + _AGENT_ATTRIBUTION_FOOTER + "\n"


class TestExtractSectionBody:
    def test_returns_empty_when_heading_absent(self) -> None:
        assert body_policy.extract_section_body("## Other\n", "Missing") == ""

    def test_slices_to_next_h2(self) -> None:
        body = "## A\n\nalpha\n\n## B\n\nbeta\n"
        assert "alpha" in body_policy.extract_section_body(body, "A")
        assert "beta" not in body_policy.extract_section_body(body, "A")

    def test_includes_h3_subsections(self) -> None:
        body = "## Checklist\n\n### Bootstrap\n\n- [ ] x\n\n## Next\n"
        slice_ = body_policy.extract_section_body(body, "Checklist")
        assert "### Bootstrap" in slice_
        assert "- [ ] x" in slice_

    def test_case_insensitive(self) -> None:
        body = "## verification\n\n- command: `c`\n  result: `r`\n"
        slice_ = body_policy.extract_section_body(body, "Verification")
        assert "command:" in slice_

    def test_ignores_html_commented_heading(self) -> None:
        body = "<!-- ## Verification -->\n## Verification\n\n- x\n"
        slice_ = body_policy.extract_section_body(body, "Verification")
        assert "- x" in slice_

    def test_handles_crlf(self) -> None:
        body = "## A\r\n\r\nalpha\r\n## B\r\n"
        slice_ = body_policy.extract_section_body(body, "A")
        assert "alpha" in slice_


class TestVerifyPrVerificationPairs:
    def test_well_formed_single_pair(self) -> None:
        body = "## Verification\n\n- command: `pytest -q`\n  result: `exit 0`\n"
        assert body_policy.verify_pr_verification_pairs(body) == []

    def test_well_formed_two_pairs(self) -> None:
        assert (
            body_policy.verify_pr_verification_pairs(
                _NEW_SHAPE_VERIFICATION_OK
            )
            == []
        )

    def test_missing_section_fails(self) -> None:
        errors = body_policy.verify_pr_verification_pairs("## Other\n")
        assert errors
        assert "empty" in errors[0]

    def test_command_without_result_fails(self) -> None:
        body = "## Verification\n\n- command: `pytest`\n"
        errors = body_policy.verify_pr_verification_pairs(body)
        assert any("not followed by" in e for e in errors)

    def test_command_followed_by_blank_line_fails(self) -> None:
        body = "## Verification\n\n- command: `pytest`\n\n  result: `exit 0`\n"
        errors = body_policy.verify_pr_verification_pairs(body)
        assert any("not followed by" in e for e in errors)

    def test_result_without_command_fails(self) -> None:
        body = "## Verification\n\n  result: `orphan`\n"
        errors = body_policy.verify_pr_verification_pairs(body)
        assert any("without a preceding" in e for e in errors)

    def test_command_without_backticks_fails(self) -> None:
        body = "## Verification\n\n- command: pytest\n  result: `exit 0`\n"
        errors = body_policy.verify_pr_verification_pairs(body)
        assert errors

    def test_result_with_wrong_indent_fails(self) -> None:
        body = "## Verification\n\n- command: `pytest`\nresult: `exit 0`\n"
        errors = body_policy.verify_pr_verification_pairs(body)
        assert errors

    def test_html_commented_content_ignored(self) -> None:
        body = (
            "## Verification\n\n"
            "<!-- - command: `fake`\n  result: `fake` -->\n"
            "- command: `pytest`\n  result: `exit 0`\n"
        )
        assert body_policy.verify_pr_verification_pairs(body) == []


class TestVerifyPrChecklistSubsections:
    def test_well_formed_passes(self) -> None:
        assert (
            body_policy.verify_pr_checklist_subsections(
                _NEW_SHAPE_CHECKLIST_OK
            )
            == []
        )

    @pytest.mark.parametrize(
        "drop",
        list(body_policy._CHECKLIST_SUBSECTIONS),
    )
    def test_each_subsection_missing(self, drop: str) -> None:
        broken = _NEW_SHAPE_CHECKLIST_OK.replace(
            f"### {drop}", f"### NOT-{drop}"
        )
        errors = body_policy.verify_pr_checklist_subsections(broken)
        assert any(f"### {drop}" in e for e in errors)

    def test_subsection_without_items_fails(self) -> None:
        body = """## Checklist

### Bootstrap

(no items)

### After-merge

- [ ] x

### Post-merge

- [ ] y
"""
        errors = body_policy.verify_pr_checklist_subsections(body)
        assert any("Bootstrap" in e and "no" in e for e in errors)

    def test_empty_section_fails(self) -> None:
        errors = body_policy.verify_pr_checklist_subsections("## Other\n")
        assert errors
        assert "empty" in errors[0]

    def test_clarifier_in_heading_tolerated(self) -> None:
        # "After-merge (CI)" matches as After-merge.
        assert (
            body_policy.verify_pr_checklist_subsections(
                _NEW_SHAPE_CHECKLIST_OK
            )
            == []
        )

    def test_checked_items_count(self) -> None:
        body = """## Checklist

### Bootstrap

- [x] done

### After-merge

- [x] CI green

### Post-merge

- [x] auto-retro opened
"""
        assert body_policy.verify_pr_checklist_subsections(body) == []


class TestVerifyPrAgentAttributionFooter:
    def test_trailing_codex_footer_passes(self) -> None:
        body = _NEW_SHAPE_PR_BODY
        assert body_policy.verify_pr_agent_attribution_footer(body) == []

    def test_trailing_claude_code_footer_passes(self) -> None:
        body = (
            "## Summary\n\nx\n\n"
            "_Generated by [Claude Code](https://claude.ai/code/session_1)_\n"
        )
        assert body_policy.verify_pr_agent_attribution_footer(body) == []

    def test_missing_footer_fails(self) -> None:
        errors = body_policy.verify_pr_agent_attribution_footer(
            _NEW_SHAPE_CHECKLIST_OK
        )
        assert errors
        assert "agent-attribution footer" in errors[0]

    def test_footer_must_be_final_non_empty_line(self) -> None:
        body = _AGENT_ATTRIBUTION_FOOTER + "\n\n## Checklist\n"
        errors = body_policy.verify_pr_agent_attribution_footer(body)
        assert errors

    def test_footer_requires_url_form(self) -> None:
        body = "_Generated by [Codex](codex-session)_\n"
        errors = body_policy.verify_pr_agent_attribution_footer(body)
        assert errors

    def test_duplicate_footer_fails(self) -> None:
        # Manual footer + harness auto-appended session footer (#784).
        manual = "_Generated by [Claude Code](https://claude.ai/code/s1)_"
        appended = "_Generated by [Claude Code](https://claude.ai/code/s2)_"
        body = f"## Summary\n\nx\n\n{manual}\n\n{appended}\n"
        errors = body_policy.verify_pr_agent_attribution_footer(body)
        assert errors
        assert "multiple" in errors[0]


class TestVerifyCodexAttributionFooter:
    def test_trailing_codex_model_footer_passes(self) -> None:
        body = (
            "body\n\n"
            "_Generated by [Codex](https://openai.com/codex) using GPT-5._\n"
        )
        assert (
            body_policy.verify_codex_attribution_footer(body, model="GPT-5")
            == []
        )

    def test_missing_footer_fails_with_expected_line(self) -> None:
        errors = body_policy.verify_codex_attribution_footer(
            "body\n", model="GPT-5"
        )
        assert errors
        assert (
            "_Generated by [Codex](https://openai.com/codex) using GPT-5._"
            in errors[0]
        )

    def test_footer_must_be_final_non_empty_line(self) -> None:
        body = (
            "_Generated by [Codex](https://openai.com/codex) using GPT-5._"
            "\n\nbody\n"
        )
        errors = body_policy.verify_codex_attribution_footer(body, model="GPT-5")
        assert errors

    def test_duplicate_footer_fails(self) -> None:
        footer = "_Generated by [Codex](https://openai.com/codex) using GPT-5._"
        errors = body_policy.verify_codex_attribution_footer(
            f"body\n\n{footer}\n\n{footer}\n", model="GPT-5"
        )
        assert errors
        assert "multiple" in errors[0]

    def test_empty_model_fails(self) -> None:
        errors = body_policy.verify_codex_attribution_footer("body\n", model="")
        assert errors
        assert "must not be empty" in errors[0]

    def test_non_ascii_model_fails(self) -> None:
        errors = body_policy.verify_codex_attribution_footer(
            "body\n", model="モデル"
        )
        assert errors
        assert "printable ASCII" in errors[0]


class TestShapeCutoffWindow:
    def test_before_shape_cutoff_skipped(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # An old-shape PR created before the shape cutoff still passes
        # because the baseline (H2) check is satisfied by _CANONICAL_PR_BODY.
        assert (
            body_policy._verify(
                "pull_request",
                _CANONICAL_PR_BODY,
                created_at="2026-05-22T00:00:00Z",
                shape_cutoff="2026-05-26T00:00:00Z",
            )
            == 0
        )
        assert (
            "OK: pull_request body contains all required sections."
            in capsys.readouterr().out
        )

    def test_after_shape_cutoff_old_shape_fails(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Old-shape body with checkbox in Verification fails when the
        # shape gate is enabled for a PR created after the cutoff.
        assert (
            body_policy._verify(
                "pull_request",
                _CANONICAL_PR_BODY,
                created_at="2026-05-27T00:00:00Z",
                shape_cutoff="2026-05-26T00:00:00Z",
            )
            == 1
        )
        out = capsys.readouterr().out
        assert "::error::" in out

    def test_after_shape_cutoff_new_shape_passes(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert (
            body_policy._verify(
                "pull_request",
                _NEW_SHAPE_PR_BODY,
                created_at="2026-05-27T00:00:00Z",
                shape_cutoff="2026-05-26T00:00:00Z",
            )
            == 0
        )
        assert (
            "OK: pull_request body contains all required sections."
            in capsys.readouterr().out
        )

    def test_empty_shape_cutoff_disables_gate(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Without shape_cutoff, the new gate is off (back-compat for the
        # original baseline-only callers).
        assert (
            body_policy._verify(
                "pull_request",
                _CANONICAL_PR_BODY,
                shape_cutoff="",
            )
            == 0
        )

    def test_shape_cutoff_does_not_apply_to_issues(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Shape gate is PR-only; issues are unaffected even when the
        # cutoff is set.
        assert (
            body_policy._verify(
                "issue",
                _CANONICAL_ISSUE_BODY_H2,
                created_at="2026-05-27T00:00:00Z",
                shape_cutoff="2026-05-26T00:00:00Z",
            )
            == 0
        )


class TestShapeCutoffCLI:
    def test_shape_cutoff_env_var(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setenv("PR_BODY", _CANONICAL_PR_BODY)
        monkeypatch.setenv("PR_CREATED_AT", "2026-05-27T00:00:00Z")
        monkeypatch.setenv("BODY_POLICY_SHAPE_CUTOFF", "2026-05-26T00:00:00Z")
        monkeypatch.delenv("BODY_POLICY_CUTOFF", raising=False)
        assert (
            body_policy.main(["verify", "--kind", "pull_request"]) == 1
        )

    def test_shape_cutoff_flag_overrides_env(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setenv("BODY_POLICY_SHAPE_CUTOFF", "2026-01-01T00:00:00Z")
        body_file = tmp_path / "body.md"
        body_file.write_text(_NEW_SHAPE_PR_BODY, encoding="utf-8")
        assert (
            body_policy.main(
                [
                    "verify",
                    "--kind",
                    "pull_request",
                    "--body-file",
                    str(body_file),
                    "--shape-cutoff",
                    "2026-05-26T00:00:00Z",
                    "--created-at",
                    "2026-05-27T00:00:00Z",
                ]
            )
            == 0
        )


# ---------------------------------------------------------------------------
# ASCII contract
# ---------------------------------------------------------------------------


class TestASCIIContract:
    def test_success_output_is_ascii(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        body_policy._verify("pull_request", _CANONICAL_PR_BODY)
        out = capsys.readouterr().out
        assert out.isascii(), out

    def test_failure_output_is_ascii(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        body_policy._verify("pull_request", "")
        out = capsys.readouterr().out
        assert out.isascii(), out

    def test_bot_skip_output_is_ascii(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        body_policy._verify(
            "pull_request", "", author="dependabot[bot]"
        )
        out = capsys.readouterr().out
        assert out.isascii(), out

    def test_cutoff_skip_output_is_ascii(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        body_policy._verify(
            "issue",
            "",
            created_at="2026-05-22T00:00:00Z",
            cutoff="2026-05-23T00:00:00Z",
        )
        out = capsys.readouterr().out
        assert out.isascii(), out
