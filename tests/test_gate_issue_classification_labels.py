"""Tests for ``scripts/gate_issue_classification_labels.py``.

Verifies that:
- An ``mcp__github__issue_write`` ``create`` lacking a ``layer:*`` or ``type:*``
  label (validated against the label-policy.toml catalog) is denied, naming the
  missing axis.
- A create carrying both axes passes through.
- Non-create methods, off-target tools, and a labels value that is absent or the
  wrong type behave correctly.
- A missing / malformed policy SoT fails open (no decision).
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
    ("layer:p1-goal-plan", "1d76db"),
    ("layer:p4-safety-boundary", "fbca04"),
    ("layer:meta", "c5def5"),
    ("type:feat", "a2eeef"),
    ("type:fix", "d73a4a"),
    ("severity:security", "b60205"),
]


def _policy_toml(entries: list[tuple[str, str]]) -> str:
    blocks = []
    for name, color in entries:
        blocks.append(
            "\n".join(
                [
                    "[[labels]]",
                    f'name = "{name}"',
                    'status = "keep"',
                    'description = "x"',
                    f'color = "{color}"',
                ]
            )
        )
    return "\n\n".join(blocks)


@pytest.fixture
def policy_path(tmp_path: Path) -> Path:
    path = tmp_path / "label-policy.toml"
    path.write_text(_policy_toml(_SOT), encoding="utf-8")
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


class TestLoadAxisLabelsFromPolicy:
    def test_groups_names_by_axis_prefix(self, policy_path: Path) -> None:
        axes = gate.load_axis_labels_from_policy(policy_path)
        assert axes["layer"] == frozenset(
            {"layer:p1-goal-plan", "layer:p4-safety-boundary", "layer:meta"}
        )
        assert axes["type"] == frozenset({"type:feat", "type:fix"})

    def test_rejects_unknown_status(self, tmp_path: Path) -> None:
        path = tmp_path / "label-policy.toml"
        path.write_text(
            "\n".join(
                [
                    "[[labels]]",
                    'name = "layer:meta"',
                    'status = "bogus"',
                    'description = "x"',
                    'color = "c5def5"',
                ]
            ),
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="unrecognized"):
            gate.load_axis_labels_from_policy(path)

    def test_every_required_axis_has_live_labels(self) -> None:
        # DRIFT GUARD (#3): the gate assumes each required axis's labels use the
        # "<axis>:" prefix. If a future label-policy family were made create-
        # mandatory but its labels used another naming convention (or had no
        # labels defined in the policy yet), load_axis_labels_from_policy would
        # return an empty valid set, missing_axes would silently skip it, and that
        # axis would go unenforced. Assert every derived required axis resolves to
        # at least one live label so such drift fails deterministically here.
        axes = gate.load_axis_labels_from_policy(gate._DEFAULT_POLICY_PATH)
        for axis, _prefix in gate.axis_prefixes():
            assert axes.get(axis), f"required axis {axis!r} has no valid labels in the policy SoT"


class TestMissingAxes:
    def test_both_axes_present_is_empty(self, policy_path: Path) -> None:
        axes = gate.load_axis_labels_from_policy(policy_path)
        assert gate.missing_axes(["layer:p4-safety-boundary", "type:fix"], axes) == []

    def test_no_labels_reports_both(self, policy_path: Path) -> None:
        axes = gate.load_axis_labels_from_policy(policy_path)
        assert gate.missing_axes([], axes) == ["layer", "type"]

    def test_only_layer_reports_type(self, policy_path: Path) -> None:
        axes = gate.load_axis_labels_from_policy(policy_path)
        assert gate.missing_axes(["layer:meta"], axes) == ["type"]

    def test_only_type_reports_layer(self, policy_path: Path) -> None:
        axes = gate.load_axis_labels_from_policy(policy_path)
        assert gate.missing_axes(["type:feat"], axes) == ["layer"]

    def test_unregistered_axis_label_does_not_satisfy(self, policy_path: Path) -> None:
        axes = gate.load_axis_labels_from_policy(policy_path)
        assert gate.missing_axes(["layer:bogus", "type:fix"], axes) == ["layer"]

    def test_unrelated_labels_ignored(self, policy_path: Path) -> None:
        axes = gate.load_axis_labels_from_policy(policy_path)
        assert gate.missing_axes(["severity:security"], axes) == [
            "layer",
            "type",
        ]

    def test_empty_axis_is_skipped(self) -> None:
        axes = {"layer": frozenset(), "type": frozenset({"type:fix"})}
        assert gate.missing_axes([], axes) == ["type"]


class TestDecide:
    def test_under_labeled_create_is_denied(self, policy_path: Path) -> None:
        decision = gate.decide(
            "mcp__github__issue_write", _create_input(["type:fix"]), policy_path=policy_path
        )
        assert decision is not None
        out = decision["hookSpecificOutput"]
        assert out["permissionDecision"] == "deny"
        assert "layer:*" in out["permissionDecisionReason"]
        assert "#1246" in out["permissionDecisionReason"]

    def test_fully_labeled_create_passes(self, policy_path: Path) -> None:
        decision = gate.decide(
            "mcp__github__issue_write",
            _create_input(["layer:p4-safety-boundary", "type:fix"]),
            policy_path=policy_path,
        )
        assert decision is None

    def test_missing_labels_key_is_denied(self, policy_path: Path) -> None:
        tool_input = {"method": "create", "owner": "o", "repo": "r"}
        decision = gate.decide(
            "mcp__github__issue_write", tool_input, policy_path=policy_path
        )
        assert decision is not None

    def test_labels_wrong_type_treated_as_empty(self, policy_path: Path) -> None:
        decision = gate.decide(
            "mcp__github__issue_write", _create_input("type:fix"), policy_path=policy_path
        )
        assert decision is not None

    def test_update_method_passes(self, policy_path: Path) -> None:
        tool_input = {"method": "update", "owner": "o", "repo": "r", "labels": []}
        assert (
            gate.decide("mcp__github__issue_write", tool_input, policy_path=policy_path)
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
    def test_off_target_tools_pass(self, tool_name: str, policy_path: Path) -> None:
        assert gate.decide(tool_name, _create_input([]), policy_path=policy_path) is None

    def test_missing_sot_fails_open(self, tmp_path: Path) -> None:
        decision = gate.decide(
            "mcp__github__issue_write",
            _create_input([]),
            policy_path=tmp_path / "absent.toml",
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
