"""Pin PR Verification result wording that feeds auto-retro.

Issue #573 showed that ambiguous success prose and local ``blocked:``
toolchain rows in a PR body become auto-retro repair-history rows. These
tests keep the PR-facing docs aligned with ``scripts/auto_retro.py``'s
pass-marker contract.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.shard_ci_ops

REPO_ROOT = Path(__file__).resolve().parents[1]
PR_TEMPLATE = REPO_ROOT / ".github" / "PULL_REQUEST_TEMPLATE.md"
BODY_STANDARD = REPO_ROOT / "docs" / "standards" / "issue-pr-body-standard.md"
SCRIPT_STANDARD = REPO_ROOT / "docs" / "standards" / "workflow-script-quality.md"


def test_pr_template_names_pass_markers_not_short_observations() -> None:
    text = PR_TEMPLATE.read_text(encoding="utf-8")
    assert "N passed summary" in text
    assert "short observation" not in text


def test_body_standard_warns_against_free_form_success_prose() -> None:
    text = BODY_STANDARD.read_text(encoding="utf-8")
    assert "Do not use free-form success prose" in text
    assert "outside `## Verification`" in text


def test_workflow_script_standard_warns_against_blocked_verification() -> None:
    text = SCRIPT_STANDARD.read_text(encoding="utf-8")
    assert "Do not quote a local `blocked:` result as successful verification." in text
