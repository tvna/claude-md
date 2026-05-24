"""Unit tests for scripts/verify_required_check_contexts.py."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import verify_required_check_contexts as mod


class TestLoadSotContexts:
    def test_extracts_contexts(self, tmp_path: Path) -> None:
        sot = tmp_path / "main.json"
        sot.write_text(
            json.dumps(
                {
                    "rules": [
                        {
                            "type": "required_status_checks",
                            "parameters": {
                                "required_status_checks": [
                                    {"context": "alpha / gate"},
                                    {"context": "beta / gate"},
                                ]
                            },
                        }
                    ]
                }
            )
        )
        assert mod.load_sot_contexts(sot) == ["alpha / gate", "beta / gate"]

    def test_returns_empty_when_no_required_status_checks_rule(
        self, tmp_path: Path
    ) -> None:
        sot = tmp_path / "main.json"
        sot.write_text(json.dumps({"rules": [{"type": "non_fast_forward"}]}))
        assert mod.load_sot_contexts(sot) == []

    def test_returns_empty_when_no_rules(self, tmp_path: Path) -> None:
        sot = tmp_path / "main.json"
        sot.write_text(json.dumps({}))
        assert mod.load_sot_contexts(sot) == []

    def test_filters_entries_with_empty_context(self, tmp_path: Path) -> None:
        sot = tmp_path / "main.json"
        sot.write_text(
            json.dumps(
                {
                    "rules": [
                        {
                            "type": "required_status_checks",
                            "parameters": {
                                "required_status_checks": [
                                    {"context": "kept"},
                                    {"context": ""},
                                    {},
                                ]
                            },
                        }
                    ]
                }
            )
        )
        assert mod.load_sot_contexts(sot) == ["kept"]


class TestParseWorkflow:
    def test_extracts_workflow_name_and_explicit_job_names(self) -> None:
        text = (
            "name: My workflow\n"
            "\n"
            "on:\n"
            "  pull_request:\n"
            "\n"
            "jobs:\n"
            "  gate:\n"
            '    name: "My workflow / gate"\n'
            "    runs-on: ubuntu-latest\n"
            "    steps:\n"
            "      - name: Step one\n"
            "        run: echo hi\n"
        )
        parsed = mod.parse_workflow(text)
        assert parsed["name"] == "My workflow"
        assert parsed["jobs"]["gate"]["name"] == "My workflow / gate"

    def test_defaults_to_no_name_when_job_has_none(self) -> None:
        text = (
            "name: Other\n"
            "jobs:\n"
            "  gate:\n"
            "    runs-on: ubuntu-latest\n"
            "    steps:\n"
            "      - name: Step\n"
            "        run: echo x\n"
        )
        parsed = mod.parse_workflow(text)
        assert parsed["jobs"]["gate"] == {}

    def test_ignores_step_names_indented_six_spaces(self) -> None:
        text = (
            "name: Z\n"
            "jobs:\n"
            "  gate:\n"
            "    runs-on: ubuntu-latest\n"
            "    steps:\n"
            "      - name: Should-not-leak\n"
        )
        parsed = mod.parse_workflow(text)
        assert "name" not in parsed["jobs"]["gate"]

    def test_handles_unquoted_scalar(self) -> None:
        text = (
            "name: Plain\n"
            "jobs:\n"
            "  gate:\n"
            "    name: Plain / gate\n"
        )
        parsed = mod.parse_workflow(text)
        assert parsed["jobs"]["gate"]["name"] == "Plain / gate"

    def test_handles_single_quoted_scalar(self) -> None:
        text = (
            "name: Q\n"
            "jobs:\n"
            "  gate:\n"
            "    name: 'Q / gate'\n"
        )
        parsed = mod.parse_workflow(text)
        assert parsed["jobs"]["gate"]["name"] == "Q / gate"

    def test_survives_column_one_python_heredoc_inside_run_block(self) -> None:
        """Reproduces threat-intel-triage.yml shape that breaks PyYAML.

        The fallback line-based parser must extract `name:` and job
        names successfully even when later lines in the file include
        column-1 content that a strict YAML parser would reject.
        """
        text = (
            "name: Heredoc\n"
            "jobs:\n"
            "  gate:\n"
            '    name: "Heredoc / gate"\n'
            "    runs-on: ubuntu-latest\n"
            "    steps:\n"
            "      - name: Run python\n"
            "        run: |\n"
            "          python3 - <<'PY'\n"
            "import json\n"
            "import sys\n"
            "print(json.dumps({}))\n"
            "PY\n"
        )
        parsed = mod.parse_workflow(text)
        assert parsed["name"] == "Heredoc"
        assert parsed["jobs"]["gate"]["name"] == "Heredoc / gate"


class TestProducedCheckNames:
    def test_maps_explicit_name_to_origin(self, tmp_path: Path) -> None:
        wf = tmp_path / "verify-x.yml"
        wf.write_text(
            "name: Verify x\n"
            "jobs:\n"
            "  gate:\n"
            '    name: "Verify x / gate"\n'
        )
        produced = mod.produced_check_names(tmp_path)
        assert produced["Verify x / gate"] == ("verify-x.yml", "gate")

    def test_falls_back_to_job_id_when_no_explicit_name(self, tmp_path: Path) -> None:
        wf = tmp_path / "verify-y.yml"
        wf.write_text(
            "name: Verify y\n"
            "jobs:\n"
            "  gate:\n"
            "    runs-on: ubuntu-latest\n"
        )
        produced = mod.produced_check_names(tmp_path)
        assert produced["gate"] == ("verify-y.yml", "gate")

    def test_first_workflow_wins_on_collision(self, tmp_path: Path) -> None:
        for fname in ["first.yml", "second.yml"]:
            (tmp_path / fname).write_text(
                "name: dup\n"
                "jobs:\n"
                "  gate:\n"
                "    runs-on: ubuntu-latest\n"
            )
        produced = mod.produced_check_names(tmp_path)
        assert produced["gate"][0] == "first.yml"


class TestFindMissing:
    def test_returns_only_missing_contexts(self) -> None:
        sot = ["A / gate", "B / gate", "C / gate"]
        produced = {"A / gate": ("a.yml", "gate"), "C / gate": ("c.yml", "gate")}
        assert mod.find_missing(sot, produced) == ["B / gate"]

    def test_returns_empty_when_all_match(self) -> None:
        sot = ["A / gate"]
        produced = {"A / gate": ("a.yml", "gate")}
        assert mod.find_missing(sot, produced) == []

    def test_returns_all_when_none_match(self) -> None:
        assert mod.find_missing(["X", "Y"], {}) == ["X", "Y"]


class TestCmdVerify:
    def _write_sot(self, tmp_path: Path, contexts: list[str]) -> Path:
        sot = tmp_path / "main.json"
        sot.write_text(
            json.dumps(
                {
                    "rules": [
                        {
                            "type": "required_status_checks",
                            "parameters": {
                                "required_status_checks": [
                                    {"context": c} for c in contexts
                                ]
                            },
                        }
                    ]
                }
            )
        )
        return sot

    def _write_workflows(self, tmp_path: Path, mapping: dict[str, str]) -> Path:
        wf_dir = tmp_path / "workflows"
        wf_dir.mkdir()
        for fname, context in mapping.items():
            (wf_dir / fname).write_text(
                f"name: {context.split(' / ')[0]}\n"
                "jobs:\n"
                "  gate:\n"
                f'    name: "{context}"\n'
            )
        return wf_dir

    def test_exit_zero_when_all_contexts_produced(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        sot = self._write_sot(tmp_path, ["A / gate", "B / gate"])
        wf_dir = self._write_workflows(
            tmp_path, {"verify-a.yml": "A / gate", "verify-b.yml": "B / gate"}
        )
        code = mod.main(
            ["verify", "--sot-path", str(sot), "--workflows-dir", str(wf_dir)]
        )
        assert code == 0
        out = capsys.readouterr().out
        assert "OK: every required_status_check" in out

    def test_exit_zero_when_no_contexts_declared(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        sot = tmp_path / "main.json"
        sot.write_text(json.dumps({}))
        wf_dir = tmp_path / "workflows"
        wf_dir.mkdir()
        code = mod.main(
            ["verify", "--sot-path", str(sot), "--workflows-dir", str(wf_dir)]
        )
        assert code == 0
        assert "declares no required_status_checks" in capsys.readouterr().out

    def test_exit_one_when_a_context_is_missing(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        sot = self._write_sot(tmp_path, ["A / gate", "B / gate"])
        wf_dir = self._write_workflows(tmp_path, {"verify-a.yml": "A / gate"})
        code = mod.main(
            ["verify", "--sot-path", str(sot), "--workflows-dir", str(wf_dir)]
        )
        assert code == 1
        err = capsys.readouterr().err
        assert "missing: 'B / gate'" in err
        assert "issue #287" in err

    def test_exit_one_when_workflow_job_lacks_explicit_name(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """The PR #271/#274 silent break scenario: SoT says
        'Verify ruleset sync / gate' but workflow job has no explicit
        name, so check_run.name defaults to 'gate' and never matches.
        """
        sot = self._write_sot(tmp_path, ["Verify ruleset sync / gate"])
        wf_dir = tmp_path / "workflows"
        wf_dir.mkdir()
        (wf_dir / "verify-ruleset-sync.yml").write_text(
            "name: Verify ruleset sync\n"
            "jobs:\n"
            "  gate:\n"
            "    runs-on: ubuntu-latest\n"
        )
        code = mod.main(
            ["verify", "--sot-path", str(sot), "--workflows-dir", str(wf_dir)]
        )
        assert code == 1
        err = capsys.readouterr().err
        assert "Verify ruleset sync / gate" in err


class TestStripScalar:
    def test_strips_double_quotes(self) -> None:
        assert mod._strip_scalar(' "hello world" ') == "hello world"

    def test_strips_single_quotes(self) -> None:
        assert mod._strip_scalar(" 'a / b' ") == "a / b"

    def test_passes_through_unquoted(self) -> None:
        assert mod._strip_scalar("  plain  ") == "plain"

    def test_handles_empty(self) -> None:
        assert mod._strip_scalar("   ") == ""
