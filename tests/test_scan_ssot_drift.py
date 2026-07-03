"""Tests for ``scripts/scan_ssot_drift.py``.

Covers each manifest-extraction function on synthetic inputs, the registry
projection helpers, the comparison functions (both drift directions plus the
no-script allowlists), the real-repo happy path (an empty drift report is
this phase's acceptance bar), and the ``main`` CLI contract (exit 0/1/64).

Refs #2256, #2246.
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest
import scan_ssot_drift as gate
from preflight_steps import Step

pytestmark = pytest.mark.shard_preflight

_REPO_ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Manifest extraction
# ---------------------------------------------------------------------------


class TestPretooluseManifest:
    def test_unions_every_target_with_a_config(self) -> None:
        agent_hooks = {
            "targets": [
                {
                    "agent": "claude",
                    "config": {
                        "hooks": {
                            "PreToolUse": [
                                {"hooks": [{"command": "python3 scripts/foo.py"}]}
                            ]
                        }
                    },
                },
                {
                    "agent": "codex",
                    "config": {
                        "hooks": {
                            "PreToolUse": [
                                {"hooks": [{"command": "python3 scripts/bar.py"}]}
                            ]
                        }
                    },
                },
                {"agent": "devin", "mirror": "codex"},
            ]
        }
        assert gate.pretooluse_manifest(agent_hooks) == frozenset({"foo", "bar"})

    def test_ignores_non_pretooluse_events(self) -> None:
        agent_hooks = {
            "targets": [
                {
                    "agent": "claude",
                    "config": {
                        "hooks": {
                            "Stop": [{"hooks": [{"command": "python3 scripts/foo.py"}]}]
                        }
                    },
                }
            ]
        }
        assert gate.pretooluse_manifest(agent_hooks) == frozenset()

    def test_non_dict_input_returns_empty(self) -> None:
        assert gate.pretooluse_manifest(["not", "a", "dict"]) == frozenset()

    def test_ignores_non_string_command(self) -> None:
        agent_hooks = {
            "targets": [
                {
                    "agent": "claude",
                    "config": {"hooks": {"PreToolUse": [{"hooks": [{"command": 1}]}]}},
                }
            ]
        }
        assert gate.pretooluse_manifest(agent_hooks) == frozenset()


class TestStepsManifest:
    def test_extracts_script_and_flags_unmapped(self) -> None:
        steps = (
            Step("gate_a", ("python3", "scripts/gate_a.py", "verify")),
            Step("ruff", ("uv", "run", "ruff", "check")),
            Step("mystery", ("some-binary",)),
        )
        scripts, unmapped = gate.steps_manifest(steps)
        assert scripts == frozenset({"gate_a"})
        assert unmapped == frozenset({"mystery"})

    def test_allowlisted_no_script_step_is_not_unmapped(self) -> None:
        steps = (Step("mypy", ("uv", "run", "mypy", "scripts", "tests")),)
        _, unmapped = gate.steps_manifest(steps)
        assert unmapped == frozenset()

    def test_real_steps_module(self) -> None:
        scripts, unmapped = gate.steps_manifest()
        assert "scan_ssot_drift" in scripts
        assert unmapped == frozenset()


class TestPreCommitManifest:
    def test_extracts_script_from_entry_and_args(self) -> None:
        config = {
            "repos": [
                {
                    "hooks": [
                        {"id": "gate-a", "entry": "uv run python scripts/gate_a.py verify"},
                        {
                            "id": "gate-b",
                            "entry": "bash -c",
                            "args": ["exec scripts/gate_b.py verify"],
                        },
                    ]
                }
            ]
        }
        scripts, unmapped = gate.pre_commit_manifest(config)
        assert scripts == frozenset({"gate_a", "gate_b"})
        assert unmapped == frozenset()

    def test_no_script_hook_is_unmapped_unless_allowlisted(self) -> None:
        config = {
            "repos": [
                {
                    "hooks": [
                        {"id": "trailing-whitespace", "entry": "trailing-whitespace-fixer"},
                        {"id": "mystery-hook", "entry": "some-binary"},
                    ]
                }
            ]
        }
        scripts, unmapped = gate.pre_commit_manifest(config)
        assert scripts == frozenset()
        assert unmapped == frozenset({"mystery-hook"})

    def test_non_dict_input_returns_empty(self) -> None:
        scripts, unmapped = gate.pre_commit_manifest("not a dict")
        assert scripts == frozenset()
        assert unmapped == frozenset()


class TestCiManifest:
    def test_excludes_preflight_all_runner(self, tmp_path: Path) -> None:
        workflows = tmp_path / "workflows"
        workflows.mkdir()
        (workflows / "pr.yml").write_text(
            textwrap.dedent(
                """\
                on:
                  pull_request:
                jobs:
                  gate:
                    steps:
                      - run: python3 scripts/preflight_all.py --list
                      - run: python3 scripts/foo.py verify
                """
            ),
            encoding="utf-8",
        )
        assert gate.ci_manifest(workflows) == frozenset({"foo"})


class TestServerNativeRules:
    def test_extracts_rule_types(self) -> None:
        rulesets = {"rules": [{"type": "deletion"}, {"type": "non_fast_forward"}, "stray"]}
        assert gate.server_native_rules(rulesets) == frozenset({"deletion", "non_fast_forward"})

    def test_non_dict_input_returns_empty(self) -> None:
        assert gate.server_native_rules([]) == frozenset()


# ---------------------------------------------------------------------------
# Registry projections
# ---------------------------------------------------------------------------

_SAMPLE_REGISTRY: dict[str, object] = {
    "gates": [
        {
            "id": "g-script",
            "kind": "script",
            "script": "scripts/foo.py",
            "planes": ["pre-push", "ci"],
            "cluster": "c1",
        },
        {
            "id": "g-native",
            "kind": "native",
            "native_rule": "deletion",
            "planes": ["server"],
            "cluster": "c1",
        },
        {
            "id": "g-other",
            "kind": "script",
            "script": "scripts/bar.py",
            "planes": ["pre-commit"],
            "cluster": None,
        },
    ],
    "clusters": [
        {"id": "c1", "expected_planes": ["pre-push", "ci", "server"]},
        {"id": "c2", "expected_planes": ["pre-commit"]},
    ],
}


class TestRegistryProjections:
    def test_registry_scripts_for_plane(self) -> None:
        assert gate.registry_scripts_for_plane(_SAMPLE_REGISTRY, "pre-push") == {"foo": "g-script"}
        assert gate.registry_scripts_for_plane(_SAMPLE_REGISTRY, "pre-commit") == {"bar": "g-other"}
        assert gate.registry_scripts_for_plane(_SAMPLE_REGISTRY, "server") == {}

    def test_registry_native_rules_for_plane(self) -> None:
        assert gate.registry_native_rules_for_plane(_SAMPLE_REGISTRY, "server") == {
            "deletion": "g-native"
        }
        assert gate.registry_native_rules_for_plane(_SAMPLE_REGISTRY, "pre-push") == {}

    def test_registry_cluster_planes(self) -> None:
        planes = gate.registry_cluster_planes(_SAMPLE_REGISTRY)
        assert planes == {"c1": {"pre-push", "ci", "server"}}


# ---------------------------------------------------------------------------
# Comparison functions
# ---------------------------------------------------------------------------


class TestDiffPlane:
    def test_reports_both_directions(self) -> None:
        warnings = gate.diff_plane(
            frozenset({"a", "b"}),
            {"b": "gate-b", "c": "gate-c"},
            manifest_label="MANIFEST",
            plane="pre-push",
        )
        assert any("scripts/a.py" in w and "no registry gate" in w for w in warnings)
        assert any("gate-c" in w and "MANIFEST does not reference it" in w for w in warnings)
        assert not any("scripts/b.py" in w for w in warnings)

    def test_no_drift_is_empty(self) -> None:
        assert gate.diff_plane(frozenset({"a"}), {"a": "gate-a"}, manifest_label="M", plane="p") == []


class TestDiffNative:
    def test_reports_both_directions(self) -> None:
        warnings = gate.diff_native(frozenset({"deletion", "non_fast_forward"}), {"deletion": "g1"})
        assert any("non_fast_forward" in w and "no registry gate" in w for w in warnings)
        assert not any("'deletion'" in w and "no registry gate" in w for w in warnings)

    def test_extra_native_gate_reported(self) -> None:
        warnings = gate.diff_native(frozenset(), {"deletion": "g1"})
        assert any("g1" in w and "does not declare it" in w for w in warnings)


class TestDiffClusters:
    def test_missing_plane_reported(self) -> None:
        warnings = gate.diff_clusters(_SAMPLE_REGISTRY)
        assert any("'c2'" in w and "'pre-commit'" in w for w in warnings)
        assert not any("'c1'" in w for w in warnings)

    def test_fully_covered_cluster_is_silent(self) -> None:
        registry: dict[str, object] = {
            "gates": [
                {"id": "g1", "kind": "script", "script": "scripts/x.py", "planes": ["pre-commit"], "cluster": "c"}
            ],
            "clusters": [{"id": "c", "expected_planes": ["pre-commit"]}],
        }
        assert gate.diff_clusters(registry) == []


class TestDiffUnmapped:
    def test_reports_each_unmapped_entry(self) -> None:
        warnings = gate.diff_unmapped(frozenset({"z", "a"}), manifest_label="M")
        assert warnings == [
            "M entry 'a' has no 'scripts/<name>.py' reference and is not in the no-script allowlist.",
            "M entry 'z' has no 'scripts/<name>.py' reference and is not in the no-script allowlist.",
        ]

    def test_empty_is_silent(self) -> None:
        assert gate.diff_unmapped(frozenset(), manifest_label="M") == []


# ---------------------------------------------------------------------------
# verify_registry (synthetic, end to end over the pure functions)
# ---------------------------------------------------------------------------


class TestVerifyRegistrySynthetic:
    def _base_registry(self) -> dict[str, object]:
        return {
            "gates": [
                {
                    "id": "g-foo",
                    "kind": "script",
                    "script": "scripts/foo.py",
                    "planes": ["pretooluse", "pre-push", "pre-commit", "ci"],
                    "cluster": None,
                },
                {
                    "id": "g-deletion",
                    "kind": "native",
                    "native_rule": "deletion",
                    "planes": ["server"],
                    "cluster": None,
                },
            ],
            "clusters": [],
        }

    def _agent_hooks(self) -> dict[str, object]:
        return {
            "targets": [
                {
                    "agent": "claude",
                    "config": {
                        "hooks": {"PreToolUse": [{"hooks": [{"command": "scripts/foo.py"}]}]}
                    },
                }
            ]
        }

    def test_clean_registry_reports_nothing(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            gate, "steps_manifest", lambda: (frozenset({"foo"}), frozenset())
        )
        workflows = tmp_path / "workflows"
        workflows.mkdir()
        (workflows / "pr.yml").write_text(
            "on:\n  pull_request:\njobs:\n  g:\n    steps:\n      - run: python3 scripts/foo.py verify\n",
            encoding="utf-8",
        )
        pre_commit_config = {
            "repos": [{"hooks": [{"id": "g-foo", "entry": "python3 scripts/foo.py verify"}]}]
        }
        rulesets = {"rules": [{"type": "deletion"}]}
        warnings = gate.verify_registry(
            self._base_registry(),
            agent_hooks=self._agent_hooks(),
            pre_commit_config=pre_commit_config,
            rulesets=rulesets,
            workflows_dir=workflows,
        )
        assert warnings == []

    def test_missing_registry_gate_reported(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(gate, "steps_manifest", lambda: (frozenset(), frozenset()))
        workflows = tmp_path / "workflows"
        workflows.mkdir()
        registry: dict[str, object] = {"gates": [], "clusters": []}
        warnings = gate.verify_registry(
            registry,
            agent_hooks=self._agent_hooks(),
            pre_commit_config={"repos": []},
            rulesets={"rules": []},
            workflows_dir=workflows,
        )
        assert any("scripts/foo.py" in w and "pretooluse" in w for w in warnings)


# ---------------------------------------------------------------------------
# Real repository (happy path -- this phase's acceptance bar is a clean report)
# ---------------------------------------------------------------------------


class TestRealRepository:
    def test_verify_registry_over_real_repo_is_clean(self) -> None:
        registry = json.loads((_REPO_ROOT / ".gitapex/ssot.json").read_text())
        agent_hooks = json.loads((_REPO_ROOT / "scripts/agent_hooks_source.json").read_text())
        pre_commit_config = gate._load_yaml(_REPO_ROOT / ".pre-commit-config.yaml")
        rulesets = json.loads((_REPO_ROOT / ".github/rulesets/main.json").read_text())
        warnings = gate.verify_registry(
            registry,
            agent_hooks=agent_hooks,
            pre_commit_config=pre_commit_config,
            rulesets=rulesets,
            workflows_dir=_REPO_ROOT / ".github/workflows",
        )
        assert warnings == []

    def test_main_verify_exits_zero(self) -> None:
        assert gate.main(["verify"]) == 0


# ---------------------------------------------------------------------------
# CLI contract
# ---------------------------------------------------------------------------


class TestMainCli:
    def test_unknown_subcommand_exits_64(self) -> None:
        assert gate.main(["bogus"]) == 64

    def test_no_subcommand_exits_64(self) -> None:
        assert gate.main([]) == 64

    def test_missing_registry_exits_one(self, tmp_path: Path) -> None:
        assert gate.main(["verify", "--registry", str(tmp_path / "nope.json")]) == 1

    def test_missing_workflows_dir_exits_one(self, tmp_path: Path) -> None:
        assert (
            gate.main(["verify", "--workflows-dir", str(tmp_path / "does-not-exist")]) == 1
        )

    def test_unparseable_registry_exits_one(self, tmp_path: Path) -> None:
        bad = tmp_path / "r.json"
        bad.write_text("{ not json")
        assert gate.main(["verify", "--registry", str(bad)]) == 1

    def test_non_object_registry_exits_one(self, tmp_path: Path) -> None:
        bad = tmp_path / "r.json"
        bad.write_text("[]")
        assert gate.main(["verify", "--registry", str(bad)]) == 1

    def test_verify_prints_warning_and_exits_zero_on_drift(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        registry_path = tmp_path / "ssot.json"
        registry_path.write_text(json.dumps({"gates": [], "clusters": []}))
        monkeypatch.chdir(_REPO_ROOT)
        exit_code = gate.main(["verify", "--registry", str(registry_path)])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "::warning::" in captured.err
        assert "ADVISORY:" in captured.err
