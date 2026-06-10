"""Tests for scripts/scan_test_presence_drift.py (#1088).

These cover the three static checks the gate performs -- M2 test-module
presence with a shrink-only allowlist, the O6 GitHub-API boundary registry
drift check, and the M3 CLI-contract registration check -- plus the
end-to-end ``verify`` CLI over synthetic ``scripts/``/``tests/`` trees, and
a self-check that the real repository tree passes the gate.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import scan_test_presence_drift as gate
import yaml

pytestmark = pytest.mark.shard_default

REPO_ROOT = Path(__file__).resolve().parent.parent


def _local_hook_entries() -> dict[str, str]:
    """Return {hook id: entry} for the repo-local pre-commit hooks."""
    config = yaml.safe_load((REPO_ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8"))
    entries: dict[str, str] = {}
    for repo in config["repos"]:
        if repo.get("repo") == "local":
            for hook in repo["hooks"]:
                entries[hook["id"]] = hook["entry"]
    return entries


# --- M2 test-module presence -------------------------------------------------


class TestTestModuleCandidates:
    def test_public_script_expects_test_prefix(self) -> None:
        assert gate.test_module_candidates("issue_link") == ("test_issue_link.py",)

    def test_private_helper_accepts_both_underscore_forms(self) -> None:
        # ``_ci_watch`` -> ``test__ci_watch`` (literal) and ``_git`` ->
        # ``test_git`` (dropped leading underscore) both occur in the tree.
        assert gate.test_module_candidates("_git") == ("test__git.py", "test_git.py")


class TestHasTestModule:
    def test_detects_literal_form(self, tmp_path: Path) -> None:
        (tmp_path / "test_foo.py").write_text("", encoding="utf-8")
        assert gate.has_test_module("foo", tmp_path) is True

    def test_detects_dropped_underscore_form(self, tmp_path: Path) -> None:
        (tmp_path / "test_git.py").write_text("", encoding="utf-8")
        assert gate.has_test_module("_git", tmp_path) is True

    def test_missing_returns_false(self, tmp_path: Path) -> None:
        assert gate.has_test_module("foo", tmp_path) is False


class TestFindMissingTests:
    def test_flags_script_without_test_or_allowlist(self, tmp_path: Path) -> None:
        missing, stale = gate.find_missing_tests(["foo"], tmp_path, {})
        assert missing == ["foo"]
        assert stale == []

    def test_allowlisted_script_is_not_missing(self, tmp_path: Path) -> None:
        missing, stale = gate.find_missing_tests(["_foo"], tmp_path, {"_foo": "reason"})
        assert missing == []
        assert stale == []

    def test_stale_allowlist_when_test_now_exists(self, tmp_path: Path) -> None:
        (tmp_path / "test_foo.py").write_text("", encoding="utf-8")
        missing, stale = gate.find_missing_tests(["_foo"], tmp_path, {"_foo": "reason"})
        assert missing == []
        assert stale == ["_foo"]

    def test_stale_allowlist_when_script_removed(self, tmp_path: Path) -> None:
        missing, stale = gate.find_missing_tests([], tmp_path, {"_gone": "reason"})
        assert stale == ["_gone"]


# --- O6 GitHub-API boundary registry ----------------------------------------


class TestModuleImports:
    def test_collects_import_and_from_import(self, tmp_path: Path) -> None:
        path = tmp_path / "m.py"
        path.write_text("import os\nfrom _github_api import gh_api\n", encoding="utf-8")
        assert {"os", "_github_api"} <= gate.module_imports(path)

    def test_unparseable_returns_empty(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.py"
        path.write_text("def (:\n", encoding="utf-8")
        assert gate.module_imports(path) == set()


class TestDetectGithubApiScripts:
    def test_detects_boundary_importer_skips_private(self, tmp_path: Path) -> None:
        (tmp_path / "pub.py").write_text("from _github_api import gh_api\n", encoding="utf-8")
        (tmp_path / "_priv.py").write_text("import _github_api\n", encoding="utf-8")
        (tmp_path / "plain.py").write_text("import os\n", encoding="utf-8")
        assert gate.detect_github_api_scripts(tmp_path) == {"pub"}


class TestFindGithubApiDrift:
    def test_undeclared_and_stale(self) -> None:
        undeclared, stale = gate.find_github_api_drift({"a", "b"}, frozenset({"b", "c"}))
        assert undeclared == ["a"]
        assert stale == ["c"]

    def test_clean(self) -> None:
        undeclared, stale = gate.find_github_api_drift({"b"}, frozenset({"b"}))
        assert undeclared == []
        assert stale == []


# --- M3 CLI-contract registration -------------------------------------------


class TestParseContractRegistryScripts:
    def test_parses_tuple_keys(self, tmp_path: Path) -> None:
        path = tmp_path / "t.py"
        path.write_text(
            "CONTRACT_REGISTRY = {\n"
            '    ("foo.py", "verify"): "test_foo",\n'
            '    ("bar.py", None): "test_bar",\n'
            "}\n",
            encoding="utf-8",
        )
        assert gate.parse_contract_registry_scripts(path) == {"foo", "bar"}

    def test_parses_annotated_assignment(self, tmp_path: Path) -> None:
        path = tmp_path / "t.py"
        path.write_text(
            'CONTRACT_REGISTRY: dict = {("foo.py", "run"): "test_foo"}\n',
            encoding="utf-8",
        )
        assert gate.parse_contract_registry_scripts(path) == {"foo"}

    def test_missing_file_returns_empty(self, tmp_path: Path) -> None:
        assert gate.parse_contract_registry_scripts(tmp_path / "nope.py") == set()


class TestFindMissingCliContracts:
    def test_flags_unregistered_workflow_script(self) -> None:
        assert gate.find_missing_cli_contracts({"foo", "bar"}, {"foo"}) == ["bar"]

    def test_clean(self) -> None:
        assert gate.find_missing_cli_contracts({"foo"}, {"foo", "extra"}) == []


class TestCollectWorkflowScripts:
    def test_matches_invocations_excludes_comment_mentions(self, tmp_path: Path) -> None:
        scripts_dir = tmp_path / "scripts"
        workflows_dir = tmp_path / "wf"
        scripts_dir.mkdir()
        workflows_dir.mkdir()
        (scripts_dir / "foo.py").write_text("", encoding="utf-8")
        (scripts_dir / "runner.py").write_text("", encoding="utf-8")
        (workflows_dir / "a.yml").write_text(
            "steps:\n"
            "  - run: python3 scripts/foo.py verify\n"
            "  # see scripts/runner.py for the local runner\n",
            encoding="utf-8",
        )
        assert gate.collect_workflow_scripts(workflows_dir, scripts_dir) == {"foo"}

    def test_uv_run_python_form(self, tmp_path: Path) -> None:
        scripts_dir = tmp_path / "scripts"
        workflows_dir = tmp_path / "wf"
        scripts_dir.mkdir()
        workflows_dir.mkdir()
        (scripts_dir / "foo.py").write_text("", encoding="utf-8")
        (workflows_dir / "a.yml").write_text(
            "  - run: uv run python scripts/foo.py verify\n", encoding="utf-8"
        )
        assert gate.collect_workflow_scripts(workflows_dir, scripts_dir) == {"foo"}


# --- verify CLI end-to-end ---------------------------------------------------


def _build_clean_tree(tmp_path: Path) -> tuple[Path, Path, Path]:
    scripts_dir = tmp_path / "scripts"
    tests_dir = tmp_path / "tests"
    workflows_dir = tmp_path / "wf"
    for directory in (scripts_dir, tests_dir, workflows_dir):
        directory.mkdir()
    (scripts_dir / "foo.py").write_text("import os\n", encoding="utf-8")
    (tests_dir / "test_foo.py").write_text("import foo\n", encoding="utf-8")
    (tests_dir / gate.CONTRACT_TEST_MODULE).write_text(
        'CONTRACT_REGISTRY = {("foo.py", "verify"): "test_foo"}\n', encoding="utf-8"
    )
    (workflows_dir / "a.yml").write_text(
        "  - run: python3 scripts/foo.py verify\n", encoding="utf-8"
    )
    return scripts_dir, tests_dir, workflows_dir


def _verify(scripts_dir: Path, tests_dir: Path, workflows_dir: Path) -> int:
    return gate.main(
        [
            "verify",
            "--scripts-dir",
            str(scripts_dir),
            "--tests-dir",
            str(tests_dir),
            "--workflows-dir",
            str(workflows_dir),
        ]
    )


@pytest.fixture
def empty_registries(monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the gate's registries at an empty set for synthetic-tree runs.

    ``cmd_verify`` consults the module-level :data:`ALLOW_NO_TEST_MODULE` and
    :data:`GITHUB_API_SCRIPTS`, which describe the *real* repository tree.
    Synthetic trees have neither, so the CLI tests reset both to empty.
    """
    monkeypatch.setattr(gate, "ALLOW_NO_TEST_MODULE", {})
    monkeypatch.setattr(gate, "GITHUB_API_SCRIPTS", frozenset())


@pytest.mark.usefixtures("empty_registries")
class TestVerifyCli:
    def test_clean_tree_exits_zero(self, tmp_path: Path) -> None:
        scripts_dir, tests_dir, workflows_dir = _build_clean_tree(tmp_path)
        assert _verify(scripts_dir, tests_dir, workflows_dir) == 0

    def test_missing_test_module_exits_one(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        scripts_dir, tests_dir, workflows_dir = _build_clean_tree(tmp_path)
        (scripts_dir / "bar.py").write_text("import os\n", encoding="utf-8")
        assert _verify(scripts_dir, tests_dir, workflows_dir) == 1
        err = capsys.readouterr().err
        assert "scripts/bar.py has no matching test module" in err

    def test_undeclared_github_api_script_exits_one(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        scripts_dir, tests_dir, workflows_dir = _build_clean_tree(tmp_path)
        (scripts_dir / "api.py").write_text("from _github_api import gh_api\n", encoding="utf-8")
        (tests_dir / "test_api.py").write_text("import api\n", encoding="utf-8")
        assert _verify(scripts_dir, tests_dir, workflows_dir) == 1
        err = capsys.readouterr().err
        assert "not in GITHUB_API_SCRIPTS" in err

    def test_unregistered_workflow_script_exits_one(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        scripts_dir, tests_dir, workflows_dir = _build_clean_tree(tmp_path)
        (scripts_dir / "baz.py").write_text("import os\n", encoding="utf-8")
        (tests_dir / "test_baz.py").write_text("import baz\n", encoding="utf-8")
        (workflows_dir / "b.yml").write_text(
            "  - run: python3 scripts/baz.py verify\n", encoding="utf-8"
        )
        assert _verify(scripts_dir, tests_dir, workflows_dir) == 1
        err = capsys.readouterr().err
        assert "no CLI contract test" in err


# --- self-check on the real repository tree ----------------------------------


class TestRepositoryTreeIsClean:
    def test_real_tree_passes(self) -> None:
        assert gate.main(["verify"]) == 0

    def test_allowlist_entries_are_documented(self) -> None:
        assert gate.ALLOW_NO_TEST_MODULE, "allowlist must have at least one entry"
        for stem, rationale in gate.ALLOW_NO_TEST_MODULE.items():
            assert stem.startswith("_"), f"{stem} must be a private helper"
            assert len(rationale) > 20, f"{stem} needs a substantive rationale"

    def test_github_api_registry_matches_detection(self) -> None:
        detected = gate.detect_github_api_scripts(gate.SCRIPTS_DIR)
        assert detected == set(gate.GITHUB_API_SCRIPTS)


class TestPreCommitWiring:
    """Refs #1632 (PR #1625 retro, Fact 4): the scanner must fire at commit time.

    Wiring it into ``.pre-commit-config.yaml`` is the durable gate that closes
    the Fact 4 gap (a new workflow-invoked script without its M3 contract test
    previously surfaced only in CI). The scanner already runs in
    verify-agents.yml and preflight_all.py; this asserts the commit-time mirror.
    """

    def test_hook_is_registered(self) -> None:
        entries = _local_hook_entries()
        assert "scan-test-presence-drift" in entries
        assert "scripts/scan_test_presence_drift.py verify" in entries["scan-test-presence-drift"]

    def test_throwaway_workflow_script_without_contract_is_flagged(
        self, tmp_path: Path
    ) -> None:
        # Reproduce Fact 4 in miniature: a new public script invoked by a
        # workflow, with a test module (M2 ok) but no CONTRACT_REGISTRY entry,
        # must be reported as missing its M3 contract test -- the exact class the
        # #1625 first attempt missed.
        scripts = tmp_path / "scripts"
        tests = tmp_path / "tests"
        workflows = tmp_path / "workflows"
        for d in (scripts, tests, workflows):
            d.mkdir()
        (scripts / "throwaway_tool.py").write_text("print('hi')\n", encoding="utf-8")
        (tests / "test_throwaway_tool.py").write_text("", encoding="utf-8")
        (tests / "test_workflow_cli_contracts.py").write_text(
            "CONTRACT_REGISTRY = {}\n", encoding="utf-8"
        )
        (workflows / "throwaway.yml").write_text(
            "jobs:\n  x:\n    steps:\n"
            "      - run: uv run python scripts/throwaway_tool.py verify\n",
            encoding="utf-8",
        )
        workflow_scripts = gate.collect_workflow_scripts(workflows, scripts)
        registry = gate.parse_contract_registry_scripts(tests / "test_workflow_cli_contracts.py")
        missing = gate.find_missing_cli_contracts(workflow_scripts, registry)
        assert "throwaway_tool" in missing
