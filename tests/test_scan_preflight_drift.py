"""Tests for ``scripts/scan_preflight_drift.py``.

The drift gate is the deterministic backstop for the verification-set
parity guarantee: pull_request: workflows and ``preflight_all.STEPS``
must cover the same script set (modulo the allowlist). Refs #493.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
import scan_preflight_drift as spd

pytestmark = pytest.mark.shard_default
# ---------------------------------------------------------------------------
# workflow_targets_pull_request
# ---------------------------------------------------------------------------


class TestWorkflowTargetsPullRequest:
    def test_mapping_form(self) -> None:
        yaml = textwrap.dedent(
            """\
            on:
              pull_request:
                types: [opened, edited]
            jobs: {}
            """
        )
        assert spd.workflow_targets_pull_request(yaml) is True

    def test_list_form(self) -> None:
        yaml = "on: [pull_request, push]\njobs: {}\n"
        assert spd.workflow_targets_pull_request(yaml) is True

    def test_pull_request_target_excluded(self) -> None:
        yaml = textwrap.dedent(
            """\
            on:
              pull_request_target:
                types: [opened]
            jobs: {}
            """
        )
        assert spd.workflow_targets_pull_request(yaml) is False

    def test_schedule_only_excluded(self) -> None:
        yaml = 'on:\n  schedule:\n    - cron: "0 0 * * 0"\n'
        assert spd.workflow_targets_pull_request(yaml) is False

    def test_issues_only_excluded(self) -> None:
        yaml = "on:\n  issues:\n    types: [opened]\n"
        assert spd.workflow_targets_pull_request(yaml) is False

    def test_mixed_triggers_keeps_pull_request(self) -> None:
        yaml = textwrap.dedent(
            """\
            on:
              issues:
                types: [opened]
              pull_request:
                types: [opened]
            """
        )
        assert spd.workflow_targets_pull_request(yaml) is True


# ---------------------------------------------------------------------------
# extract_script_refs
# ---------------------------------------------------------------------------


class TestExtractScriptRefs:
    def test_basic(self) -> None:
        text = "run: python3 scripts/foo.py verify\n"
        assert spd.extract_script_refs(text) == {"foo"}

    def test_multiple(self) -> None:
        text = "scripts/foo.py\nscripts/bar.py\nscripts/foo.py\n"
        assert spd.extract_script_refs(text) == {"foo", "bar"}

    def test_ignores_private_helpers(self) -> None:
        # Helpers prefixed with '_' are imports, not CLI gates.
        text = "scripts/_github_api.py\nscripts/foo.py\n"
        assert spd.extract_script_refs(text) == {"foo"}

    def test_underscored_name_allowed(self) -> None:
        text = "scripts/preflight_all.py --list\n"
        assert spd.extract_script_refs(text) == {"preflight_all"}


# ---------------------------------------------------------------------------
# collect_workflow_refs
# ---------------------------------------------------------------------------


class TestCollectWorkflowRefs:
    def test_collects_only_pull_request_workflows(self, tmp_path: Path) -> None:
        workflows = tmp_path / "workflows"
        workflows.mkdir()
        (workflows / "pr.yml").write_text(
            textwrap.dedent(
                """\
                on:
                  pull_request:
                jobs:
                  gate:
                    runs-on: ubuntu-latest
                    steps:
                      - run: python3 scripts/foo.py verify
                """
            ),
            encoding="utf-8",
        )
        (workflows / "schedule.yml").write_text(
            textwrap.dedent(
                """\
                on:
                  schedule:
                    - cron: "0 0 * * 0"
                jobs:
                  gate:
                    runs-on: ubuntu-latest
                    steps:
                      - run: python3 scripts/bar.py verify
                """
            ),
            encoding="utf-8",
        )
        refs = spd.collect_workflow_refs(workflows)
        assert refs == [spd.WorkflowReference(workflow="pr.yml", script="foo")]


# ---------------------------------------------------------------------------
# diff
# ---------------------------------------------------------------------------


class TestDiff:
    def test_no_drift(self) -> None:
        refs = [spd.WorkflowReference(workflow="pr.yml", script="foo")]
        missing, extra = spd.diff(refs, declared={"foo"}, allowlist={})
        assert missing == []
        assert extra == set()

    def test_ci_extra_is_missing_in_preflight(self) -> None:
        refs = [
            spd.WorkflowReference(workflow="pr.yml", script="foo"),
            spd.WorkflowReference(workflow="pr.yml", script="bar"),
        ]
        missing, extra = spd.diff(refs, declared={"foo"}, allowlist={})
        assert missing == [spd.WorkflowReference(workflow="pr.yml", script="bar")]
        assert extra == set()

    def test_allowlist_silences_missing(self) -> None:
        refs = [spd.WorkflowReference(workflow="pr.yml", script="title_policy")]
        missing, extra = spd.diff(
            refs,
            declared=set(),
            allowlist={"title_policy": "webhook input only"},
        )
        assert missing == []
        assert extra == set()

    def test_preflight_extra_is_warning(self) -> None:
        refs = [spd.WorkflowReference(workflow="pr.yml", script="foo")]
        missing, extra = spd.diff(refs, declared={"foo", "future"}, allowlist={})
        assert missing == []
        assert extra == {"future"}


# ---------------------------------------------------------------------------
# Real repo invariants
# ---------------------------------------------------------------------------


class TestRealRepoInvariants:
    """Run the drift gate against the real repository state.

    Acts as the canonical assertion that landing this PR does not
    immediately fail the new CI step it adds.
    """

    def test_real_repo_has_no_drift(self) -> None:
        repo_root = Path(__file__).resolve().parent.parent
        exit_code = spd.main(
            [
                "verify",
                "--workflows-dir",
                str(repo_root / ".github" / "workflows"),
                "--preflight",
                str(repo_root / "scripts" / "preflight_all.py"),
            ]
        )
        assert exit_code == 0


# ---------------------------------------------------------------------------
# CLI integration
# ---------------------------------------------------------------------------


class TestCli:
    def test_verify_reports_drift_via_exit_code(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        workflows = tmp_path / "workflows"
        workflows.mkdir()
        (workflows / "pr.yml").write_text(
            textwrap.dedent(
                """\
                on:
                  pull_request:
                jobs:
                  gate:
                    runs-on: ubuntu-latest
                    steps:
                      - run: python3 scripts/new_gate.py verify
                """
            ),
            encoding="utf-8",
        )

        fake_preflight = tmp_path / "preflight_all.py"
        fake_preflight.write_text(
            textwrap.dedent(
                """\
                import json, sys
                print(json.dumps([]))
                """
            ),
            encoding="utf-8",
        )

        exit_code = spd.main(
            [
                "verify",
                "--workflows-dir",
                str(workflows),
                "--preflight",
                str(fake_preflight),
            ]
        )
        captured = capsys.readouterr()
        assert exit_code == 1
        assert "new_gate" in captured.err
