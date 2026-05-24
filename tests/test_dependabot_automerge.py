from __future__ import annotations

import json
from pathlib import Path

import dependabot_automerge as da
import pytest

POLICY = {
    "enabled": False,
    "allow": [
        {
            "ecosystem": "github-actions",
            "update_types": ["patch", "minor"],
            "paths": [".github/workflows/*"],
        },
        {
            "ecosystem": "uv",
            "update_types": ["patch"],
            "paths": ["pyproject.toml", "uv.lock"],
        },
    ],
}


def event(
    *,
    author: str = "dependabot[bot]",
    ref: str = "dependabot/github_actions/actions-checkout-6.0.2",
    title: str = "chore(deps): bump actions/checkout from 5.0.1 to 5.1.0",
    labels: list[str] | None = None,
    draft: bool = False,
) -> dict[str, object]:
    return {
        "pull_request": {
            "title": title,
            "draft": draft,
            "user": {"login": author},
            "head": {"ref": ref},
            "labels": [{"name": label} for label in labels or []],
        }
    }


def test_classify_update_type() -> None:
    assert da.classify_update_type("bump x from 1.2.3 to 1.2.4") == "patch"
    assert da.classify_update_type("bump x from v1.2.3 to v1.3.0") == "minor"
    assert da.classify_update_type("bump x from 1.2.3 to 2.0.0") == "major"
    assert da.classify_update_type("manual dependency update") is None


def test_infer_ecosystem() -> None:
    assert da.infer_ecosystem([".github/workflows/ci.yml"]) == "github-actions"
    assert da.infer_ecosystem(["pyproject.toml", "uv.lock"]) == "uv"
    assert da.infer_ecosystem(["README.md"]) is None


def test_audit_eligible_but_not_enabled() -> None:
    result = da.audit(event(), POLICY, [".github/workflows/verify.yml"])
    assert result.eligible is True
    assert result.enabled is False
    assert result.should_enable is False
    assert result.reasons == []


def test_enabled_policy_requests_automerge() -> None:
    policy = dict(POLICY, enabled=True)
    result = da.audit(event(), policy, [".github/workflows/verify.yml"])
    assert result.should_enable is True


def test_major_update_is_blocked() -> None:
    result = da.audit(
        event(title="chore(deps): bump actions/checkout from 5.0.1 to 6.0.2"),
        POLICY,
        [".github/workflows/verify.yml"],
    )
    assert result.eligible is False
    assert "github-actions major updates are not allowed" in result.reasons


def test_severity_label_blocks() -> None:
    result = da.audit(event(labels=["severity:non-ascii-content"]), POLICY, ["uv.lock"])
    assert result.eligible is False
    assert "manual-review label present: severity:non-ascii-content" in result.reasons


def test_unexpected_path_blocks() -> None:
    result = da.audit(event(), POLICY, [".github/workflows/verify.yml", "README.md"])
    assert result.eligible is False
    assert "changed files do not match an allowed ecosystem" in result.reasons


def test_non_dependabot_author_blocks() -> None:
    result = da.audit(event(author="octocat"), POLICY, [".github/workflows/verify.yml"])
    assert result.eligible is False
    assert "author is not trusted: octocat" in result.reasons


def test_cli_writes_summary_and_outputs(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    event_path = tmp_path / "event.json"
    policy_path = tmp_path / "policy.json"
    changed_files_path = tmp_path / "changed-files.txt"
    summary_path = tmp_path / "summary.md"
    output_path = tmp_path / "output.txt"

    event_path.write_text(json.dumps(event()), encoding="utf-8")
    policy_path.write_text(json.dumps(POLICY), encoding="utf-8")
    changed_files_path.write_text(".github/workflows/verify.yml\n", encoding="utf-8")

    rc = da.main(
        [
            "audit",
            "--event",
            str(event_path),
            "--policy",
            str(policy_path),
            "--changed-files",
            str(changed_files_path),
            "--summary-file",
            str(summary_path),
            "--output",
            str(output_path),
        ]
    )

    assert rc == 0
    assert "Dependabot auto-merge audit" in capsys.readouterr().out
    assert "eligible: `true`" in summary_path.read_text(encoding="utf-8")
    assert "should_enable=false" in output_path.read_text(encoding="utf-8")
