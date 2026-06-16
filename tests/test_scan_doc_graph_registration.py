"""Tests for ``scripts/scan_doc_graph_registration.py``.

Covers :func:`classify_path`, :func:`parse_waivers`, :func:`run_gate`, and
:func:`main`. All tests are hermetic: ``get_added_files`` is patched via
``monkeypatch`` or ``unittest.mock``; no real ``git diff`` subprocess is called.

Refs #1793.
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest
import scan_doc_graph_registration as gate

pytestmark = pytest.mark.shard_ci_ops

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_GRAPH_TOML = textwrap.dedent(
    """\
    [meta]
    schema_version = 1

    [[nodes]]
    id = "existing_standard"
    path = "docs/standards/existing.md"
    type = "standard"

    [[nodes]]
    id = "existing_prd"
    path = "docs/prd/existing.md"
    type = "prd"

    [[nodes]]
    id = "existing_runbook"
    path = "docs/runbooks/existing.md"
    type = "runbook"

    [[nodes]]
    id = "existing_script"
    path = "scripts/existing.py"
    type = "harness_script"

    [[nodes]]
    id = "existing_workflow"
    path = ".github/workflows/existing.yml"
    type = "harness_workflow"
    """
)


def _write_graph(tmp_path: Path, content: str = _GRAPH_TOML) -> Path:
    p = tmp_path / "doc-dependencies.toml"
    p.write_text(content)
    return p


def _body_file(tmp_path: Path, body: str = "") -> Path:
    p = tmp_path / "pr-body.txt"
    p.write_text(body)
    return p


# ---------------------------------------------------------------------------
# classify_path
# ---------------------------------------------------------------------------


class TestClassifyPath:
    def test_docs_standards_blocking(self) -> None:
        assert gate.classify_path("docs/standards/foo.md") == "blocking"

    def test_docs_standards_nested_blocking(self) -> None:
        assert gate.classify_path("docs/standards/sub/foo.md") == "blocking"

    def test_docs_prd_blocking(self) -> None:
        assert gate.classify_path("docs/prd/foo.md") == "blocking"

    def test_docs_prd_nested_blocking(self) -> None:
        assert gate.classify_path("docs/prd/sub/foo.md") == "blocking"

    def test_docs_runbooks_advisory(self) -> None:
        assert gate.classify_path("docs/runbooks/foo.md") == "advisory"

    def test_docs_runbooks_nested_advisory(self) -> None:
        assert gate.classify_path("docs/runbooks/sub/foo.md") == "advisory"

    def test_scripts_py_advisory(self) -> None:
        assert gate.classify_path("scripts/foo.py") == "advisory"

    def test_scripts_py_subdir_unmanaged(self) -> None:
        assert gate.classify_path("scripts/subdir/foo.py") is None

    def test_scripts_non_py_unmanaged(self) -> None:
        assert gate.classify_path("scripts/foo.sh") is None

    def test_workflows_yml_advisory(self) -> None:
        assert gate.classify_path(".github/workflows/foo.yml") == "advisory"

    def test_workflows_yaml_unmanaged(self) -> None:
        assert gate.classify_path(".github/workflows/foo.yaml") is None

    def test_workflows_subdir_unmanaged(self) -> None:
        assert gate.classify_path(".github/workflows/sub/foo.yml") is None

    def test_tests_unmanaged(self) -> None:
        assert gate.classify_path("tests/test_foo.py") is None

    def test_docs_other_unmanaged(self) -> None:
        assert gate.classify_path("docs/INDEX.md") is None

    def test_root_file_unmanaged(self) -> None:
        assert gate.classify_path("CLAUDE.md") is None


# ---------------------------------------------------------------------------
# parse_waivers
# ---------------------------------------------------------------------------


class TestParseWaivers:
    def test_empty_body(self) -> None:
        assert gate.parse_waivers("") == frozenset()

    def test_single_waiver(self) -> None:
        body = "doc-graph-registration-waiver: docs/runbooks/foo.md -- standalone\n"
        assert gate.parse_waivers(body) == frozenset(["docs/runbooks/foo.md"])

    def test_multiple_waivers(self) -> None:
        body = (
            "doc-graph-registration-waiver: docs/standards/a.md -- r1\n"
            "doc-graph-registration-waiver: docs/runbooks/b.md -- r2\n"
        )
        assert gate.parse_waivers(body) == frozenset(
            ["docs/standards/a.md", "docs/runbooks/b.md"]
        )

    def test_case_insensitive_marker(self) -> None:
        body = "DOC-GRAPH-REGISTRATION-WAIVER: docs/standards/foo.md -- reason"
        assert gate.parse_waivers(body) == frozenset(["docs/standards/foo.md"])

    def test_leading_whitespace_ignored(self) -> None:
        body = "  doc-graph-registration-waiver: docs/prd/foo.md -- reason"
        assert gate.parse_waivers(body) == frozenset(["docs/prd/foo.md"])

    def test_waiver_without_reason(self) -> None:
        body = "doc-graph-registration-waiver: docs/runbooks/foo.md"
        assert gate.parse_waivers(body) == frozenset(["docs/runbooks/foo.md"])

    def test_irrelevant_text_ignored(self) -> None:
        body = "Some PR description.\nNo waivers here.\n"
        assert gate.parse_waivers(body) == frozenset()

    def test_doc_graph_waiver_not_matched(self) -> None:
        # The old gate_doc_graph_pr.py marker must not be confused with ours.
        body = "doc-graph-waiver: prd_a -- reason\n"
        assert gate.parse_waivers(body) == frozenset()


# ---------------------------------------------------------------------------
# run_gate (pure unit tests, no subprocess)
# ---------------------------------------------------------------------------


class TestRunGate:
    def test_empty_added_files_passes(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert gate.run_gate(frozenset(), [], frozenset()) is True
        out = capsys.readouterr().err
        assert "no new governed files" in out

    def test_blocking_registered_passes(self) -> None:
        known = frozenset(["docs/standards/foo.md"])
        assert gate.run_gate(known, ["docs/standards/foo.md"], frozenset()) is True

    def test_blocking_waiver_passes(self, capsys: pytest.CaptureFixture[str]) -> None:
        waivers = frozenset(["docs/standards/foo.md"])
        assert gate.run_gate(frozenset(), ["docs/standards/foo.md"], waivers) is True
        out = capsys.readouterr().err
        assert "waived" in out

    def test_blocking_unregistered_no_waiver_fails(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        result = gate.run_gate(
            frozenset(), ["docs/standards/foo.md"], frozenset()
        )
        assert result is False
        err = capsys.readouterr().err
        assert "::error file=docs/standards/foo.md::" in err

    def test_blocking_wrong_waiver_still_fails(self) -> None:
        waivers = frozenset(["docs/standards/other.md"])
        assert (
            gate.run_gate(frozenset(), ["docs/standards/foo.md"], waivers) is False
        )

    def test_advisory_unregistered_passes_with_warning(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        result = gate.run_gate(
            frozenset(), ["docs/runbooks/foo.md"], frozenset()
        )
        assert result is True
        err = capsys.readouterr().err
        assert "::warning::" in err

    def test_advisory_script_unregistered_passes_with_warning(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        result = gate.run_gate(frozenset(), ["scripts/foo.py"], frozenset())
        assert result is True
        err = capsys.readouterr().err
        assert "::warning::" in err

    def test_advisory_workflow_unregistered_passes_with_warning(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        result = gate.run_gate(
            frozenset(), [".github/workflows/foo.yml"], frozenset()
        )
        assert result is True
        err = capsys.readouterr().err
        assert "::warning::" in err

    def test_unmanaged_path_ignored(self) -> None:
        assert gate.run_gate(frozenset(), ["tests/test_foo.py"], frozenset()) is True

    def test_mixed_blocking_and_advisory(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        added = ["docs/standards/foo.md", "docs/runbooks/bar.md"]
        result = gate.run_gate(frozenset(), added, frozenset())
        assert result is False
        err = capsys.readouterr().err
        assert "::error file=docs/standards/foo.md::" in err
        assert "::warning::" in err

    def test_ok_message_when_all_registered(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        known = frozenset(["docs/standards/foo.md"])
        gate.run_gate(known, ["docs/standards/foo.md"], frozenset())
        out = capsys.readouterr().err
        assert "OK:" in out


# ---------------------------------------------------------------------------
# registered_paths
# ---------------------------------------------------------------------------


class TestRegisteredPaths:
    def test_returns_node_paths(self, tmp_path: Path) -> None:
        from doc_graph import load_graph

        graph_path = _write_graph(tmp_path)
        graph = load_graph(graph_path)
        paths = gate.registered_paths(graph)
        assert "docs/standards/existing.md" in paths
        assert "docs/prd/existing.md" in paths
        assert "docs/runbooks/existing.md" in paths

    def test_empty_graph(self) -> None:
        from doc_graph import DocGraph

        assert gate.registered_paths(DocGraph()) == frozenset()


# ---------------------------------------------------------------------------
# main() integration (subprocess patched)
# ---------------------------------------------------------------------------


class TestMain:
    def _run_main(
        self,
        tmp_path: Path,
        added: list[str],
        body: str = "",
        graph_toml: str = _GRAPH_TOML,
        extra_argv: list[str] | None = None,
    ) -> int:
        graph_path = _write_graph(tmp_path, graph_toml)
        body_path = _body_file(tmp_path, body)
        argv = [
            "verify",
            "--graph", str(graph_path),
            "--body-file", str(body_path),
            "--base-ref", "origin/main",
        ]
        if extra_argv:
            argv += extra_argv
        with patch(
            "scan_doc_graph_registration.get_added_files", return_value=added
        ):
            return gate.main(argv)

    # ------------------------------------------------------------------
    # Subcommand routing
    # ------------------------------------------------------------------

    def test_unknown_subcommand_exits_64(self) -> None:
        assert gate.main(["unknown"]) == 64

    def test_no_subcommand_exits_64(self) -> None:
        assert gate.main([]) == 64

    # ------------------------------------------------------------------
    # Blocking path cases
    # ------------------------------------------------------------------

    def test_blocking_registered_exits_0(self, tmp_path: Path) -> None:
        assert (
            self._run_main(tmp_path, ["docs/standards/existing.md"]) == 0
        )

    def test_blocking_unregistered_no_waiver_exits_1(
        self, tmp_path: Path
    ) -> None:
        assert self._run_main(tmp_path, ["docs/standards/new.md"]) == 1

    def test_blocking_waiver_exits_0(self, tmp_path: Path) -> None:
        body = "doc-graph-registration-waiver: docs/standards/new.md -- reason\n"
        assert self._run_main(tmp_path, ["docs/standards/new.md"], body=body) == 0

    def test_prd_unregistered_exits_1(self, tmp_path: Path) -> None:
        assert self._run_main(tmp_path, ["docs/prd/new.md"]) == 1

    def test_prd_registered_exits_0(self, tmp_path: Path) -> None:
        assert self._run_main(tmp_path, ["docs/prd/existing.md"]) == 0

    # ------------------------------------------------------------------
    # Advisory path cases
    # ------------------------------------------------------------------

    def test_advisory_runbook_unregistered_exits_0(
        self, tmp_path: Path
    ) -> None:
        assert self._run_main(tmp_path, ["docs/runbooks/new.md"]) == 0

    def test_advisory_script_unregistered_exits_0(
        self, tmp_path: Path
    ) -> None:
        assert self._run_main(tmp_path, ["scripts/new.py"]) == 0

    def test_advisory_workflow_unregistered_exits_0(
        self, tmp_path: Path
    ) -> None:
        assert self._run_main(
            tmp_path, [".github/workflows/new.yml"]
        ) == 0

    # ------------------------------------------------------------------
    # Unmanaged paths
    # ------------------------------------------------------------------

    def test_unmanaged_path_exits_0(self, tmp_path: Path) -> None:
        assert self._run_main(tmp_path, ["tests/test_foo.py"]) == 0

    def test_no_added_files_exits_0(self, tmp_path: Path) -> None:
        assert self._run_main(tmp_path, []) == 0

    # ------------------------------------------------------------------
    # git diff failure (fail-open)
    # ------------------------------------------------------------------

    def test_git_diff_failure_exits_0(self, tmp_path: Path) -> None:
        graph_path = _write_graph(tmp_path)
        body_path = _body_file(tmp_path)
        with patch(
            "scan_doc_graph_registration.get_added_files", return_value=None
        ):
            result = gate.main(
                [
                    "verify",
                    "--graph", str(graph_path),
                    "--body-file", str(body_path),
                    "--base-ref", "origin/main",
                ]
            )
        assert result == 0

    # ------------------------------------------------------------------
    # Graph file missing (fail-open)
    # ------------------------------------------------------------------

    def test_missing_graph_exits_0(self, tmp_path: Path) -> None:
        with patch(
            "scan_doc_graph_registration.get_added_files",
            return_value=["docs/standards/foo.md"],
        ):
            result = gate.main(
                [
                    "verify",
                    "--graph", str(tmp_path / "nonexistent.toml"),
                    "--base-ref", "origin/main",
                ]
            )
        assert result == 0

    # ------------------------------------------------------------------
    # Invalid graph (fail-loud)
    # ------------------------------------------------------------------

    def test_invalid_graph_exits_1(self, tmp_path: Path) -> None:
        bad_toml = (
            "[[nodes]]\nid = \"x\"\npath = \"x.md\"\ntype = \"bogus_type\"\n"
        )
        assert (
            self._run_main(tmp_path, ["docs/standards/x.md"], graph_toml=bad_toml)
            == 1
        )

    # ------------------------------------------------------------------
    # PR_BODY env var fallback
    # ------------------------------------------------------------------

    def test_env_pr_body_used_when_no_body_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(
            "PR_BODY",
            "doc-graph-registration-waiver: docs/standards/new.md -- env waiver\n",
        )
        graph_path = _write_graph(tmp_path)
        with patch(
            "scan_doc_graph_registration.get_added_files",
            return_value=["docs/standards/new.md"],
        ):
            result = gate.main(
                [
                    "verify",
                    "--graph", str(graph_path),
                    "--base-ref", "origin/main",
                ]
            )
        assert result == 0

    def test_body_file_takes_precedence_over_env(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(
            "PR_BODY",
            "doc-graph-registration-waiver: docs/standards/new.md -- from env\n",
        )
        graph_path = _write_graph(tmp_path)
        body_path = _body_file(tmp_path, "")  # no waiver in file
        with patch(
            "scan_doc_graph_registration.get_added_files",
            return_value=["docs/standards/new.md"],
        ):
            result = gate.main(
                [
                    "verify",
                    "--graph", str(graph_path),
                    "--body-file", str(body_path),
                    "--base-ref", "origin/main",
                ]
            )
        # body-file has no waiver; env is ignored; gate fails
        assert result == 1
