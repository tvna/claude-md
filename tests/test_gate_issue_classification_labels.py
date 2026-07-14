"""Tests for ``scripts/gate_issue_classification_labels.py``.

Verifies that:
- An ``mcp__github__issue_write`` ``create`` lacking a ``layer:*`` or ``type:*``
  label (validated against the labels SoT) is denied, naming the missing axis.
- A create carrying both axes passes through.
- Non-create methods, off-target tools, and a labels value that is absent or the
  wrong type behave correctly.
- A missing / malformed labels SoT fails open (no decision).
- The stdin/stdout boundary works end-to-end.
"""

from __future__ import annotations

import io
import json
from collections.abc import Iterator
from pathlib import Path

import _ssot
import gate_issue_classification_labels as gate
import pytest

pytestmark = pytest.mark.shard_preflight


@pytest.fixture(autouse=True)
def _reset_ssot_cache() -> Iterator[None]:
    # gate.axis_prefixes() reads the module-global _ssot registry cache. Reset it
    # around every test so a future test that monkeypatches _ssot._REGISTRY_PATH
    # cannot leak a stale cached registry into another test in this module (this
    # file must not depend on test_ssot.py's fixture running first).
    _ssot._reset_for_tests()
    yield
    _ssot._reset_for_tests()


_SOT = [
    {"name": "layer:p1-goal-plan", "color": "1d76db", "description": "x"},
    {"name": "layer:p4-safety-boundary", "color": "fbca04", "description": "x"},
    {"name": "layer:meta", "color": "c5def5", "description": "x"},
    {"name": "type:feat", "color": "a2eeef", "description": "x"},
    {"name": "type:fix", "color": "d73a4a", "description": "x"},
    {"name": "severity:security", "color": "b60205", "description": "x"},
    {"name": "threat:intel-needed", "color": "000000", "description": "x"},
]


@pytest.fixture
def labels_path(tmp_path: Path) -> Path:
    path = tmp_path / "labels.json"
    path.write_text(json.dumps(_SOT), encoding="utf-8")
    return path


def _create_input(labels: object) -> dict[str, object]:
    return {"method": "create", "owner": "o", "repo": "r", "title": "t", "labels": labels}


class TestAxisPrefixes:
    def test_pins_layer_and_type_prefixes_from_policy(self) -> None:
        # PIN-TEST: the gate's required axes are cardinality-driven from the live
        # label-policy families via _ssot.required_issue_axes(). Today that must
        # derive exactly the layer:/type: prefixes, in that order (so the deny
        # message stays deterministic). A family/cardinality change that would
        # silently add or drop a required axis fails here.
        assert gate.axis_prefixes() == (("layer", "layer:"), ("type", "type:"))


class TestLoadAxisLabels:
    def test_groups_names_by_axis_prefix(self, labels_path: Path) -> None:
        axes = gate.load_axis_labels(labels_path)
        assert axes["layer"] == frozenset(
            {"layer:p1-goal-plan", "layer:p4-safety-boundary", "layer:meta"}
        )
        assert axes["type"] == frozenset({"type:feat", "type:fix"})

    def test_rejects_non_array(self, tmp_path: Path) -> None:
        path = tmp_path / "labels.json"
        path.write_text(json.dumps({"name": "layer:meta"}), encoding="utf-8")
        with pytest.raises(ValueError, match="JSON array"):
            gate.load_axis_labels(path)

    def test_every_required_axis_has_live_labels(self) -> None:
        # DRIFT GUARD (#3): the gate assumes each required axis's labels use the
        # "<axis>:" prefix. If a future label-policy family were made create-
        # mandatory but its labels used another naming convention (or had no
        # labels defined in labels.json yet), load_axis_labels would return an
        # empty valid set, missing_axes would silently skip it, and that axis
        # would go unenforced. Assert every derived required axis resolves to at
        # least one live label so such drift fails deterministically here.
        axes = gate.load_axis_labels(gate._DEFAULT_LABELS_PATH)
        for axis, _prefix in gate.axis_prefixes():
            assert axes.get(axis), f"required axis {axis!r} has no valid labels in the live SoT"


class TestLoadAxisLabelsFromPolicy:
    def test_matches_load_axis_labels_on_real_repo_files(self) -> None:
        """Integration proof for #2442 Phase B batch 2: the TOML-derived axis
        buckets must match the labels.json-derived buckets for the real repo
        files. Not wired into decide()'s production path; test-only proof."""
        repo_root = Path(__file__).resolve().parent.parent
        policy_path = repo_root / ".github" / "label-policy.toml"
        labels_path = repo_root / ".github" / "labels.json"

        from_json = gate.load_axis_labels(labels_path)
        from_policy = gate.load_axis_labels_from_policy(policy_path, labels_path)

        assert from_policy == from_json

    def test_groups_names_by_axis_prefix(self, tmp_path: Path) -> None:
        policy_path = tmp_path / "label-policy.toml"
        policy_path.write_text(
            "\n".join(
                [
                    "[[labels]]",
                    'name = "layer:p1-goal-plan"',
                    'status = "keep"',
                    'description = "x"',
                    'color = "1d76db"',
                    "",
                    "[[labels]]",
                    'name = "type:fix"',
                    'status = "keep"',
                    'description = "x"',
                    'color = "d73a4a"',
                ]
            ),
            encoding="utf-8",
        )
        labels_json_path = tmp_path / "labels.json"
        labels_json_path.write_text(
            json.dumps([{"name": "type:retrospective", "color": "c5def5", "description": "Auto-opened."}]),
            encoding="utf-8",
        )

        axes = gate.load_axis_labels_from_policy(policy_path, labels_json_path)

        assert axes["layer"] == frozenset({"layer:p1-goal-plan"})
        # The injected retrospective label (see load_sot_from_policy) groups
        # into the "type" axis purely by its name prefix, same as the
        # labels.json-backed load_axis_labels would.
        assert axes["type"] == frozenset({"type:fix", "type:retrospective"})


class TestMissingAxes:
    def test_both_axes_present_is_empty(self, labels_path: Path) -> None:
        axes = gate.load_axis_labels(labels_path)
        assert gate.missing_axes(["layer:p4-safety-boundary", "type:fix"], axes) == []

    def test_no_labels_reports_both(self, labels_path: Path) -> None:
        axes = gate.load_axis_labels(labels_path)
        assert gate.missing_axes([], axes) == ["layer", "type"]

    def test_only_layer_reports_type(self, labels_path: Path) -> None:
        axes = gate.load_axis_labels(labels_path)
        assert gate.missing_axes(["layer:meta"], axes) == ["type"]

    def test_only_type_reports_layer(self, labels_path: Path) -> None:
        axes = gate.load_axis_labels(labels_path)
        assert gate.missing_axes(["type:feat"], axes) == ["layer"]

    def test_unregistered_axis_label_does_not_satisfy(self, labels_path: Path) -> None:
        axes = gate.load_axis_labels(labels_path)
        assert gate.missing_axes(["layer:bogus", "type:fix"], axes) == ["layer"]

    def test_unrelated_labels_ignored(self, labels_path: Path) -> None:
        axes = gate.load_axis_labels(labels_path)
        assert gate.missing_axes(["threat:intel-needed", "severity:security"], axes) == [
            "layer",
            "type",
        ]

    def test_empty_axis_is_skipped(self) -> None:
        axes = {"layer": frozenset(), "type": frozenset({"type:fix"})}
        assert gate.missing_axes([], axes) == ["type"]


class TestDecide:
    def test_under_labeled_create_is_denied(self, labels_path: Path) -> None:
        decision = gate.decide(
            "mcp__github__issue_write", _create_input(["type:fix"]), labels_path=labels_path
        )
        assert decision is not None
        out = decision["hookSpecificOutput"]
        assert out["permissionDecision"] == "deny"
        assert "layer:*" in out["permissionDecisionReason"]
        assert "#1246" in out["permissionDecisionReason"]

    def test_fully_labeled_create_passes(self, labels_path: Path) -> None:
        decision = gate.decide(
            "mcp__github__issue_write",
            _create_input(["layer:p4-safety-boundary", "type:fix"]),
            labels_path=labels_path,
        )
        assert decision is None

    def test_missing_labels_key_is_denied(self, labels_path: Path) -> None:
        tool_input = {"method": "create", "owner": "o", "repo": "r"}
        decision = gate.decide(
            "mcp__github__issue_write", tool_input, labels_path=labels_path
        )
        assert decision is not None

    def test_labels_wrong_type_treated_as_empty(self, labels_path: Path) -> None:
        decision = gate.decide(
            "mcp__github__issue_write", _create_input("type:fix"), labels_path=labels_path
        )
        assert decision is not None

    def test_update_method_passes(self, labels_path: Path) -> None:
        tool_input = {"method": "update", "owner": "o", "repo": "r", "labels": []}
        assert (
            gate.decide("mcp__github__issue_write", tool_input, labels_path=labels_path)
            is None
        )

    @pytest.mark.parametrize(
        "tool_name",
        [
            "mcp__github__create_pull_request",
            "mcp__github__add_issue_comment",
            "Bash",
        ],
    )
    def test_off_target_tools_pass(self, tool_name: str, labels_path: Path) -> None:
        assert gate.decide(tool_name, _create_input([]), labels_path=labels_path) is None

    def test_missing_sot_fails_open(self, tmp_path: Path) -> None:
        decision = gate.decide(
            "mcp__github__issue_write",
            _create_input([]),
            labels_path=tmp_path / "absent.json",
        )
        assert decision is None


class TestMain:
    def _run(self, payload: object, monkeypatch: pytest.MonkeyPatch) -> str:
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()
        monkeypatch.setattr("sys.stdout", stdout_buf)
        monkeypatch.setattr("sys.stderr", stderr_buf)
        rc = gate.main()
        assert rc == 0
        return stdout_buf.getvalue()

    def test_under_labeled_create_produces_deny(self, monkeypatch: pytest.MonkeyPatch) -> None:
        stdout = self._run(
            {"tool_name": "mcp__github__issue_write", "tool_input": _create_input([])},
            monkeypatch,
        )
        decision = json.loads(stdout)
        assert decision["hookSpecificOutput"]["permissionDecision"] == "deny"

    def test_fully_labeled_create_produces_no_output(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        stdout = self._run(
            {
                "tool_name": "mcp__github__issue_write",
                "tool_input": _create_input(["layer:p4-safety-boundary", "type:fix"]),
            },
            monkeypatch,
        )
        assert stdout == ""

    def test_empty_stdin_is_handled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("sys.stdin", io.StringIO(""))
        stdout_buf = io.StringIO()
        monkeypatch.setattr("sys.stdout", stdout_buf)
        monkeypatch.setattr("sys.stderr", io.StringIO())
        assert gate.main() == 0
        assert stdout_buf.getvalue() == ""

    def test_malformed_json_fails_open(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("sys.stdin", io.StringIO("{bad json"))
        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()
        monkeypatch.setattr("sys.stdout", stdout_buf)
        monkeypatch.setattr("sys.stderr", stderr_buf)
        assert gate.main() == 0
        assert stdout_buf.getvalue() == ""
        assert "malformed" in stderr_buf.getvalue()


def test_main_block_exits_via_runpy(monkeypatch: pytest.MonkeyPatch) -> None:
    import runpy

    monkeypatch.setattr("sys.stdin", type("Input", (), {"read": lambda self: ""})())
    with pytest.raises(SystemExit) as exc_info:
        runpy.run_module("gate_issue_classification_labels", run_name="__main__")
    assert exc_info.value.code == 0
