"""Regression tests for the title-policy workflow/ruleset contract."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "verify-title-policy.yml"
MAIN_RULESET = ROOT / ".github" / "rulesets" / "main.json"


def _workflow_name(text: str) -> str:
    match = re.search(r"^name:\s*(.+)$", text, flags=re.MULTILINE)
    assert match is not None
    return match.group(1).strip()


def _job_ids(text: str) -> list[str]:
    match = re.search(r"^jobs:\n(?P<body>(?:  .+\n?)+)", text, flags=re.MULTILINE)
    assert match is not None
    return re.findall(r"^  ([A-Za-z0-9_-]+):$", match.group("body"), flags=re.MULTILINE)


def _required_contexts() -> list[str]:
    data = json.loads(MAIN_RULESET.read_text())
    for rule in data["rules"]:
        if rule["type"] == "required_status_checks":
            checks = rule["parameters"]["required_status_checks"]
            return [check["context"] for check in checks]
    raise AssertionError("required_status_checks rule missing")


def test_ruleset_requires_title_policy_gate_context() -> None:
    # Post-issue-#468 step 2: title-policy verification is required via
    # the grouped `Verify GitHub content / gate` context. The standalone
    # `Verify title policy / gate` context is intentionally absent from
    # SoT pending standalone-workflow deletion in step 3 of 3.
    assert "Verify GitHub content / gate" in _required_contexts()


def test_required_context_matches_workflow_name_and_job_id() -> None:
    text = WORKFLOW.read_text()
    expected_context = f"{_workflow_name(text)} / gate"

    assert "gate" in _job_ids(text)
    # Post-issue-#468 step 2: this standalone workflow's context is no
    # longer SoT-required (coverage moved to verify-github-content.yml).
    # Step 3 of 3 deletes this workflow file.
    assert expected_context not in _required_contexts()


def test_workflow_validates_issue_and_pr_titles() -> None:
    text = WORKFLOW.read_text()

    assert "issues:" in text
    assert "pull_request:" in text
    assert "pull_request_target:" not in text
    assert "TITLE:" in text
    assert "github.event.issue.title" in text
    assert "github.event.pull_request.title" in text
    assert 'python3 scripts/title_policy.py verify --kind "$KIND"' in text
