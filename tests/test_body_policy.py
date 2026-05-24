"""Tests for ``scripts/body_policy.py``.

The ``scripts/`` directory is added to ``sys.path`` via the
``pythonpath`` key under ``[tool.pytest.ini_options]`` in
``pyproject.toml``.
"""

from __future__ import annotations

from pathlib import Path

import body_policy
import pytest

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
