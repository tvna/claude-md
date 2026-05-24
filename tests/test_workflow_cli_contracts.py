"""CLI contract tests for scripts invoked directly by GitHub workflows.

These tests pin the argv/env/file shapes used by ``.github/workflows`` so
script-level unit tests cannot pass while an Actions invocation drifts.
"""

from __future__ import annotations

import base64
import json
import re
from pathlib import Path
from typing import Any

import auto_retro
import body_policy
import branch_cleanup
import dependabot_automerge
import dependabot_labels
import issue_link
import labels_apply
import pytest
import ruleset_drift
import rulesets_apply
import scan_apm_portability
import scan_design_philosophy_drift
import scan_non_ascii
import security_drift_report
import threat_intel_triage
import title_policy
import uv_pin
import verify_required_check_contexts
import verify_ruleset_sync

REPO = "owner/repo"


def test_workflow_python_script_inventory_is_pinned() -> None:
    workflows = Path(".github/workflows")
    pattern = re.compile(r"python3\s+scripts/([A-Za-z0-9_-]+\.py)")
    found = {
        match.group(1)
        for path in workflows.glob("*.yml")
        for match in pattern.finditer(path.read_text(encoding="utf-8"))
    }

    assert found == {
        "auto_retro.py",
        "body_policy.py",
        "branch_cleanup.py",
        "dependabot_automerge.py",
        "dependabot_labels.py",
        "issue_link.py",
        "labels_apply.py",
        "ruleset_drift.py",
        "rulesets_apply.py",
        "scan_apm_portability.py",
        "scan_design_philosophy_drift.py",
        "scan_non_ascii.py",
        "security_drift_report.py",
        "threat_intel_triage.py",
        "title_policy.py",
        "uv_pin.py",
        "verify_required_check_contexts.py",
        "verify_ruleset_sync.py",
    }


def test_auto_retro_run_matches_workflow_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    event = {
        "pull_request": {
            "number": 12,
            "title": "fix(ci): repair gate",
            "merged": False,
        }
    }
    event_path = tmp_path / "event.json"
    event_path.write_text(json.dumps(event), encoding="utf-8")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_path))
    monkeypatch.setenv("REPO", REPO)

    assert auto_retro.main(["run"]) == 0


def test_body_policy_verify_matches_workflow_body_file(tmp_path: Path) -> None:
    body_file = tmp_path / "body.md"
    body_file.write_text(
        "\n".join(
            [
                "## Scope",
                "prose",
                "## Facts",
                "- Fact: one",
                "## Proposed work",
                "- step",
                "## Verification",
                "- pytest",
                "## Acceptance criteria",
                "- [ ] done",
            ]
        ),
        encoding="utf-8",
    )

    assert body_policy.main(["verify", "--kind", "issue", "--body-file", str(body_file)]) == 0


def test_branch_cleanup_survey_matches_workflow_args(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        branch_cleanup,
        "list_branches",
        lambda repo, **kwargs: [("main", "abc")],
    )

    assert branch_cleanup.main(
        [
            "survey",
            "--repo",
            REPO,
            "--dry-run",
            "true",
            "--min-age-days",
            "60",
            "--default-branch",
            "main",
            "--event-name",
            "workflow_dispatch",
            "--run-url",
            "https://example.test/run",
            "--out",
            str(tmp_path / "cleanup-comment.md"),
            "--github-output",
            str(tmp_path / "output"),
        ]
    ) == 0


def test_branch_cleanup_reconcile_matches_workflow_args(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(branch_cleanup, "find_rolling_issue", lambda repo, title: None)

    assert branch_cleanup.main(
        [
            "reconcile",
            "--repo",
            REPO,
            "--title",
            "Branch cleanup rolling summary",
            "--candidate-count",
            "0",
            "--comment-file",
            str(tmp_path / "cleanup-comment.md"),
            "--idle-close-days",
            "28",
            "--run-url",
            "https://example.test/run",
        ]
    ) == 0


def test_dependabot_automerge_audit_matches_workflow_files(tmp_path: Path) -> None:
    event = {
        "pull_request": {
            "user": {"login": "dependabot[bot]"},
            "head": {"ref": "dependabot/github-actions/actions-checkout-6"},
            "title": "Bump actions/checkout from v5 to v6",
            "labels": [],
            "draft": False,
        }
    }
    policy = {
        "enabled": False,
        "allow": [
            {
                "ecosystem": "github-actions",
                "update_types": ["major"],
                "paths": [".github/workflows/*"],
            }
        ],
    }
    event_file = tmp_path / "event.json"
    policy_file = tmp_path / "policy.json"
    changed_files = tmp_path / "changed-files.txt"
    event_file.write_text(json.dumps(event), encoding="utf-8")
    policy_file.write_text(json.dumps(policy), encoding="utf-8")
    changed_files.write_text(".github/workflows/verify.yml\n", encoding="utf-8")

    assert dependabot_automerge.main(
        [
            "audit",
            "--event",
            str(event_file),
            "--policy",
            str(policy_file),
            "--changed-files",
            str(changed_files),
            "--summary-file",
            str(tmp_path / "summary.md"),
            "--output",
            str(tmp_path / "output"),
        ]
    ) == 0


def test_dependabot_labels_verify_matches_workflow_paths(tmp_path: Path) -> None:
    dependabot = tmp_path / "dependabot.yml"
    labels = tmp_path / "labels.json"
    dependabot.write_text("updates:\n  - labels:\n      - dependencies\n", encoding="utf-8")
    labels.write_text(json.dumps([{"name": "dependencies"}]), encoding="utf-8")

    assert dependabot_labels.main(
        ["verify", "--dependabot", str(dependabot), "--labels", str(labels)]
    ) == 0


def test_issue_link_verify_matches_workflow_body_file_and_author(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    body_file = tmp_path / "body.md"
    body_file.write_text("Closes #189\n", encoding="utf-8")
    monkeypatch.setattr(issue_link, "issue_exists", lambda repo, number: True)

    assert issue_link.main(
        [
            "verify",
            "--repo",
            REPO,
            "--body-file",
            str(body_file),
            "--author",
            "octocat",
        ]
    ) == 0


def test_labels_apply_validate_and_plan_match_workflow_args(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sot = tmp_path / "labels.json"
    sot.write_text(
        json.dumps([{"name": "type:fix", "color": "d73a4a", "description": "Bug fix"}]),
        encoding="utf-8",
    )
    monkeypatch.setenv("GH_TOKEN", "token")
    monkeypatch.setattr(labels_apply, "fetch_live_labels", lambda repo, token: [])

    assert labels_apply.main(["validate", "--sot", str(sot)]) == 0
    assert labels_apply.main(
        [
            "plan",
            "--repo",
            REPO,
            "--sot",
            str(sot),
            "--prune",
            "false",
            "--dry-run",
            "true",
            "--summary-file",
            str(tmp_path / "labels-summary.md"),
        ]
    ) == 0


def test_ruleset_drift_detect_and_file_issue_match_workflow_args(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sot_dir = _write_ruleset_sot(tmp_path)
    monkeypatch.setenv("GH_TOKEN_API", "token")
    monkeypatch.setattr(
        ruleset_drift,
        "fetch_live_rulesets_list",
        lambda repo, token: [
            {"id": 1, "name": "main-protection", "target": "branch", "enforcement": "active"},
            {"id": 2, "name": "all-branches-no-force-push", "target": "branch", "enforcement": "active"},
            {"id": 3, "name": "dependabot-protection", "target": "branch", "enforcement": "active"},
        ],
    )
    monkeypatch.setattr(
        ruleset_drift,
        "fetch_live_ruleset",
        lambda repo, ruleset_id, token: _ruleset_for_id(ruleset_id),
    )
    calls: list[dict[str, Any]] = []

    def fake_file_issue(
        repo: str,
        title: str,
        body_file: Path,
        labels: tuple[str, ...] = ruleset_drift.ISSUE_LABELS,
    ) -> None:
        calls.append(
            {"repo": repo, "title": title, "body_file": body_file, "labels": labels}
        )

    monkeypatch.setattr(ruleset_drift, "file_issue", fake_file_issue)

    assert ruleset_drift.main(
        [
            "detect",
            "--repo",
            REPO,
            "--sot-dir",
            str(sot_dir),
            "--run-url",
            "https://example.test/run",
            "--summary-file",
            str(tmp_path / "summary.md"),
            "--sot-body-file",
            str(tmp_path / "drift-sot.md"),
            "--unknown-body-file",
            str(tmp_path / "drift-unknown.md"),
        ]
    ) == 0
    assert ruleset_drift.main(
        [
            "file-sot-issue",
            "--repo",
            REPO,
            "--run-date",
            "2026-05-24",
            "--body-file",
            str(tmp_path / "drift-sot.md"),
        ]
    ) == 0
    assert calls[-1]["repo"] == REPO
    assert calls[-1]["title"].startswith("fix(ruleset-drift): SoT vs live drift")


def test_rulesets_apply_plan_and_auto_delete_match_workflow_args(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sot_dir = _write_ruleset_sot(tmp_path)
    monkeypatch.setenv("GH_TOKEN", "token")
    monkeypatch.setattr(
        rulesets_apply,
        "fetch_live_rulesets",
        lambda repo, token, **kwargs: [],
    )
    monkeypatch.setattr(
        rulesets_apply,
        "get_repo_setting",
        lambda repo, key, token, **kwargs: False,
    )

    assert rulesets_apply.main(
        [
            "plan",
            "--repo",
            REPO,
            "--sot-dir",
            str(sot_dir),
            "--choice",
            "main",
            "--enable-auto-delete",
            "true",
            "--summary-file",
            str(tmp_path / "rulesets-summary.md"),
        ]
    ) == 0
    assert rulesets_apply.main(
        [
            "auto-delete",
            "--repo",
            REPO,
            "--dry-run",
            "true",
            "--summary-file",
            str(tmp_path / "rulesets-summary.md"),
        ]
    ) == 0


def test_scan_apm_portability_verify_matches_workflow_paths(tmp_path: Path) -> None:
    path = tmp_path / "portable.md"
    path.write_text("portable prose\n", encoding="utf-8")

    assert scan_apm_portability.main(
        ["verify", "--path", str(path), "--path", str(path), "--path", str(path)]
    ) == 0


def test_scan_design_philosophy_drift_verify_matches_workflow_paths(
    tmp_path: Path,
) -> None:
    master = tmp_path / "master.md"
    doc = tmp_path / "doc.md"
    master.write_text(
        "## 1. A\n## 2. B\n",
        encoding="utf-8",
    )
    glossary_lines = "".join(
        f"- **{term}**: definition.\n"
        for term in scan_design_philosophy_drift.REQUIRED_GLOSSARY_ENTRIES
    )
    doc.write_text(
        "### 2.5 Glossary\n"
        f"{glossary_lines}"
        "## 3. Matrix\n"
        "two principles by four lanes.\n"
        "| P1 - a | x |\n"
        "| P2 - b | y |\n"
        "## 4. Next\n",
        encoding="utf-8",
    )
    assert scan_design_philosophy_drift.main(
        ["verify", "--master", str(master), "--doc", str(doc)]
    ) == 0


def test_scan_non_ascii_run_matches_workflow_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    event = {
        "pull_request": {
            "number": 7,
            "title": "fix(ci): ascii title",
            "body": "ASCII body",
            "author_association": "CONTRIBUTOR",
            "user": {"login": "octocat"},
        }
    }
    event_path = tmp_path / "event.json"
    event_path.write_text(json.dumps(event), encoding="utf-8")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_path))
    monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request_target")
    monkeypatch.setenv("REPO", REPO)
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(tmp_path / "summary.md"))

    assert scan_non_ascii.main(["run"]) == 0


def test_security_drift_report_aggregate_and_post_comment_match_workflow_args(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ruleset_out = tmp_path / "ruleset-detect.out"
    labels_summary = tmp_path / "labels-summary.md"
    uv_stale = tmp_path / "uv-stale.out"
    report = tmp_path / "security-drift-report.md"
    ruleset_out.write_text("run_date=2026-05-24\ndrift_count=0\nunknown_count=0\n", encoding="utf-8")
    labels_summary.write_text("| `type:fix` | no-op | no | no | unchanged |\n", encoding="utf-8")
    uv_stale.write_text("", encoding="utf-8")

    assert security_drift_report.main(
        [
            "aggregate",
            "--ruleset-detect-output",
            str(ruleset_out),
            "--ruleset-detect-rc",
            "0",
            "--labels-plan-rc",
            "0",
            "--labels-summary-file",
            str(labels_summary),
            "--apm-diff-rc",
            "0",
            "--uv-drift-rc",
            "0",
            "--uv-stale-rc",
            "0",
            "--uv-stale-output",
            str(uv_stale),
            "--run-url",
            "https://example.test/run",
            "--summary-file",
            str(tmp_path / "summary.md"),
            "--report-file",
            str(report),
            "--github-output",
            str(tmp_path / "output"),
        ]
    ) == 0
    assert security_drift_report.main(
        [
            "post-comment",
            "--repo",
            REPO,
            "--issue",
            "178",
            "--report-file",
            str(report),
            "--dry-run",
            "true",
        ]
    ) == 0


def test_threat_intel_scan_matches_workflow_args(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dep = threat_intel_triage.Dependency(
        name="pytest",
        version="8.0.0",
        ecosystem="PyPI",
        source="uv.lock",
    )
    monkeypatch.setattr(threat_intel_triage, "discover_dependencies", lambda repo_root: [dep])
    monkeypatch.setattr(
        threat_intel_triage,
        "fetch_external_findings",
        lambda dependencies, osv_file=None, kev_file=None: [],
    )

    assert threat_intel_triage.main(
        [
            "scan",
            "--repo-root",
            ".",
            "--labels",
            "type:fix",
            "--github-output",
            str(tmp_path / "output"),
            "--summary-file",
            str(tmp_path / "summary.md"),
        ]
    ) == 0


def test_title_policy_verify_matches_workflow_kind_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TITLE", "fix(ci): ascii title")

    assert title_policy.main(["verify", "--kind", "pull_request"]) == 0


def test_uv_pin_workflow_subcommands_match_ci_usage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[tool.uv]\nrequired-version = "==0.11.11"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(uv_pin, "fetch_latest_uv_release", lambda: "0.11.11")

    assert uv_pin.main(["read", str(tmp_path / "pyproject.toml")]) == 0
    assert uv_pin.main(["drift", "--repo-root", str(tmp_path)]) == 0
    assert uv_pin.main(["stale", "--repo-root", str(tmp_path)]) == 0


def test_verify_ruleset_sync_matches_workflow_args(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    live = _ruleset_for_id(1)
    sot_text = json.dumps(live)
    monkeypatch.setenv("GH_TOKEN_API", "token")
    monkeypatch.setattr(
        verify_ruleset_sync,
        "fetch_live_ruleset_by_name",
        lambda repo, name, token: live,
    )
    monkeypatch.setattr(
        verify_ruleset_sync,
        "fetch_base_ref_sot",
        lambda repo, base_ref, sot_path, token: sot_text,
    )

    assert verify_ruleset_sync.main(
        [
            "verify",
            "--repo",
            REPO,
            "--base-ref",
            "main",
            "--sot-path",
            ".github/rulesets/main.json",
            "--ruleset-name",
            "main-protection",
        ]
    ) == 0


def test_verify_required_check_contexts_matches_workflow_args() -> None:
    """Mirrors the `Verify required-check contexts match workflow job names`
    step in `.github/workflows/verify-ruleset-sync.yml`."""
    assert verify_required_check_contexts.main(
        [
            "verify",
            "--sot-path",
            ".github/rulesets/main.json",
            "--workflows-dir",
            ".github/workflows",
        ]
    ) == 0


@pytest.mark.parametrize(
    ("label", "call"),
    [
        (
            "branch-cleanup invalid min age",
            lambda tmp: branch_cleanup.main(
                [
                    "survey",
                    "--repo",
                    REPO,
                    "--dry-run",
                    "true",
                    "--min-age-days",
                    "sixty",
                    "--default-branch",
                    "main",
                    "--out",
                    str(tmp / "out.md"),
                ]
            ),
        ),
        (
            "labels invalid boolean",
            lambda tmp: labels_apply.main(
                [
                    "plan",
                    "--repo",
                    REPO,
                    "--sot",
                    str(tmp / "missing.json"),
                    "--prune",
                    "maybe",
                    "--dry-run",
                    "true",
                    "--summary-file",
                    str(tmp / "summary.md"),
                ]
            ),
        ),
        (
            "security report invalid dry-run",
            lambda tmp: security_drift_report.main(
                [
                    "post-comment",
                    "--repo",
                    REPO,
                    "--issue",
                    "178",
                    "--report-file",
                    str(tmp / "missing.md"),
                    "--dry-run",
                    "maybe",
                ]
            ),
        ),
    ],
)
def test_workflow_cli_operator_errors_fail_loudly(
    label: str, call: Any, tmp_path: Path
) -> None:
    _ = label
    assert call(tmp_path) == 1


def test_verify_ruleset_sync_decodes_base_ref_fixture_like_github_api() -> None:
    raw = b'{"rules":[]}'
    payload = {
        "encoding": "base64",
        "content": base64.b64encode(raw).decode("ascii"),
    }

    assert verify_ruleset_sync.decode_base64_content(payload) == raw.decode("utf-8")


def _write_ruleset_sot(tmp_path: Path) -> Path:
    sot_dir = tmp_path / "rulesets"
    sot_dir.mkdir()
    for filename, ruleset in {
        "main.json": _ruleset_for_id(1),
        "all-branches.json": _ruleset_for_id(2),
        "dependabot.json": _ruleset_for_id(3),
    }.items():
        (sot_dir / filename).write_text(json.dumps(ruleset), encoding="utf-8")
    return sot_dir


def _ruleset_for_id(ruleset_id: int) -> dict[str, Any]:
    names = {
        1: "main-protection",
        2: "all-branches-no-force-push",
        3: "dependabot-protection",
    }
    return {
        "id": ruleset_id,
        "name": names[ruleset_id],
        "target": "branch",
        "enforcement": "active",
        "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}},
        "bypass_actors": [],
        "rules": [
            {
                "type": "required_status_checks",
                "parameters": {
                    "required_status_checks": [{"context": "script tests"}]
                },
            }
        ],
    }
