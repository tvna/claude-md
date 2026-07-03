"""Tests for ``scripts/scan_ssot_schema.py``.

Covers the happy path (the real ``.gitapex/ssot.json`` validates), each
referential-integrity failure class over a synthetic minimal registry, the
ordered-rules invariant, and the ``main`` CLI contract (exit 0 / 1 / 64).

The synthetic-registry tests inject ``is_tracked``, ``live_labels``, and
``consumer_labels`` so no real ``git`` or filesystem state is required; the
real schema on disk supplies the enum and required-field vocabulary.

Refs #2252, #2246.
"""

from __future__ import annotations

import json
import tomllib
from pathlib import Path
from typing import Any

import pytest
import scan_ssot_schema as gate

pytestmark = pytest.mark.shard_preflight

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SCHEMA = json.loads((_REPO_ROOT / ".gitapex/ssot.schema.json").read_text())


def _valid_registry() -> dict[str, Any]:
    """A minimal registry that validates with the fixtures below."""
    return {
        "meta": {
            "schema_version": 1,
            "tracking_issue": 2246,
            "status": "adopted-design",
            "phase": "phase-0",
        },
        "policy_sources": [
            {
                "id": "labels-live",
                "path": ".github/labels.json",
                "format": "json",
                "authority": "live label catalog",
            }
        ],
        "gates": [
            {
                "id": "g-script",
                "kind": "script",
                "script": "scripts/scan_ssot_schema.py",
                "rule": "r",
                "planes": ["pretooluse"],
                "trigger": "t",
                "policy_refs": ["labels-live"],
                "cluster": "c1",
                "tracking_issue": None,
            },
            {
                "id": "g-native",
                "kind": "native",
                "native_rule": "non_fast_forward",
                "rule": "r",
                "planes": ["server"],
                "trigger": "push",
                "policy_refs": [],
                "cluster": None,
                "tracking_issue": None,
            },
        ],
        "clusters": [
            {"id": "c1", "rule": "r", "expected_planes": ["pretooluse", "server"]}
        ],
        "label_routing": {
            "source_note": "s",
            "rules": [
                {"if_any": ["type:fix"], "action": "auto-fix-candidate", "body_read": "yes"},
                {"default": True, "action": "triage-needed", "body_read": "title-only"},
            ],
        },
        "label_consumers": [
            {"path": "scripts/scan_ssot_schema.py", "labels": ["ops:dependencies"], "note": "n"}
        ],
    }


_LIVE = frozenset({"type:fix"})
_CONSUMER = frozenset({"ops:dependencies"})


def _verify(registry: dict[str, Any]) -> list[str]:
    return gate.verify_registry(
        registry,
        _SCHEMA,
        is_tracked=lambda _p: True,
        live_labels=_LIVE,
        consumer_labels=_CONSUMER,
    )


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestHappyPath:
    def test_synthetic_registry_is_valid(self) -> None:
        assert _verify(_valid_registry()) == []

    def test_real_registry_validates_via_main(self) -> None:
        assert gate.main(["verify"]) == 0

    def test_real_registry_verify_registry_clean(self) -> None:
        registry = json.loads((_REPO_ROOT / ".gitapex/ssot.json").read_text())
        labels = json.loads((_REPO_ROOT / ".github/labels.json").read_text())
        policy = tomllib.loads((_REPO_ROOT / ".github/label-policy.toml").read_text())
        live = gate.live_label_names(labels)
        consumer = gate.consumer_label_universe(live, policy)
        errors = gate.verify_registry(
            registry, _SCHEMA, lambda _p: True, live, consumer
        )
        assert errors == []


# ---------------------------------------------------------------------------
# Schema-vocabulary loading
# ---------------------------------------------------------------------------


class TestSchemaVocab:
    def test_extracts_expected_planes(self) -> None:
        vocab = gate.extract_schema_vocab(_SCHEMA)
        assert "pretooluse" in vocab.planes
        assert "server" in vocab.planes

    def test_missing_node_raises(self) -> None:
        with pytest.raises(gate.SchemaError):
            gate.extract_schema_vocab({"properties": {}})


# ---------------------------------------------------------------------------
# Referential-integrity failure classes
# ---------------------------------------------------------------------------


class TestReferentialIntegrity:
    def test_unresolved_policy_ref(self) -> None:
        reg = _valid_registry()
        reg["gates"][0]["policy_refs"] = ["ghost-source"]
        errors = _verify(reg)
        assert any("policy_ref 'ghost-source'" in e for e in errors)

    def test_unresolved_cluster(self) -> None:
        reg = _valid_registry()
        reg["gates"][0]["cluster"] = "ghost-cluster"
        errors = _verify(reg)
        assert any("cluster 'ghost-cluster'" in e for e in errors)

    def test_untracked_script_path(self) -> None:
        reg = _valid_registry()
        errors = gate.verify_registry(
            reg,
            _SCHEMA,
            is_tracked=lambda p: p != "scripts/scan_ssot_schema.py",
            live_labels=_LIVE,
            consumer_labels=_CONSUMER,
        )
        assert any("is not a tracked file" in e for e in errors)

    def test_routing_label_not_in_live_catalog(self) -> None:
        reg = _valid_registry()
        reg["label_routing"]["rules"][0]["if_any"] = ["type:ghost"]
        errors = _verify(reg)
        assert any("does not resolve against the live catalog" in e for e in errors)

    def test_consumer_label_not_in_union(self) -> None:
        reg = _valid_registry()
        reg["label_consumers"][0]["labels"] = ["type:ghost"]
        errors = _verify(reg)
        assert any("does not resolve" in e and "type:ghost" in e for e in errors)

    def test_script_kind_missing_script(self) -> None:
        reg = _valid_registry()
        del reg["gates"][0]["script"]
        errors = _verify(reg)
        assert any("kind 'script' requires a 'script' path" in e for e in errors)

    def test_native_kind_missing_native_rule(self) -> None:
        reg = _valid_registry()
        del reg["gates"][1]["native_rule"]
        errors = _verify(reg)
        assert any("kind 'native' requires a 'native_rule'" in e for e in errors)

    def test_script_kind_with_native_rule(self) -> None:
        reg = _valid_registry()
        reg["gates"][0]["native_rule"] = "deletion"
        errors = _verify(reg)
        assert any("must not carry 'native_rule'" in e for e in errors)

    def test_unknown_plane(self) -> None:
        reg = _valid_registry()
        reg["gates"][0]["planes"] = ["bogus-plane"]
        errors = _verify(reg)
        assert any("unknown plane 'bogus-plane'" in e for e in errors)

    def test_unknown_cluster_expected_plane(self) -> None:
        reg = _valid_registry()
        reg["clusters"][0]["expected_planes"] = ["bogus-plane"]
        errors = _verify(reg)
        assert any("unknown expected plane 'bogus-plane'" in e for e in errors)

    def test_unknown_body_read(self) -> None:
        reg = _valid_registry()
        reg["label_routing"]["rules"][0]["body_read"] = "maybe"
        errors = _verify(reg)
        assert any("unknown body_read 'maybe'" in e for e in errors)

    def test_missing_required_field(self) -> None:
        reg = _valid_registry()
        del reg["meta"]["phase"]
        errors = _verify(reg)
        assert any("missing required field 'phase'" in e for e in errors)


# ---------------------------------------------------------------------------
# Ordered-rules invariant
# ---------------------------------------------------------------------------


class TestOrderedRules:
    def test_no_default_rule(self) -> None:
        reg = _valid_registry()
        reg["label_routing"]["rules"] = [reg["label_routing"]["rules"][0]]
        errors = _verify(reg)
        assert any("exactly one default rule, found 0" in e for e in errors)

    def test_two_default_rules(self) -> None:
        reg = _valid_registry()
        reg["label_routing"]["rules"].insert(
            0, {"default": True, "action": "triage-needed", "body_read": "no"}
        )
        errors = _verify(reg)
        assert any("exactly one default rule, found 2" in e for e in errors)

    def test_default_rule_not_last(self) -> None:
        reg = _valid_registry()
        rules = reg["label_routing"]["rules"]
        rules[0], rules[1] = rules[1], rules[0]
        errors = _verify(reg)
        assert any("default rule must be last" in e for e in errors)


# ---------------------------------------------------------------------------
# CLI contract
# ---------------------------------------------------------------------------


class TestMainCli:
    def test_verify_exits_zero(self) -> None:
        assert gate.main(["verify"]) == 0

    def test_unknown_subcommand_exits_64(self) -> None:
        assert gate.main(["bogus"]) == 64

    def test_no_subcommand_exits_64(self) -> None:
        assert gate.main([]) == 64

    def test_missing_registry_exits_one(self, tmp_path: Path) -> None:
        missing = tmp_path / "nope.json"
        assert gate.main(["verify", "--registry", str(missing)]) == 1

    def test_unparseable_registry_exits_one(self, tmp_path: Path) -> None:
        bad = tmp_path / "r.json"
        bad.write_text("{ not json")
        assert gate.main(["verify", "--registry", str(bad)]) == 1

    def test_malformed_schema_exits_one(self, tmp_path: Path) -> None:
        empty_schema = tmp_path / "s.json"
        empty_schema.write_text("{}")
        assert gate.main(["verify", "--schema", str(empty_schema)]) == 1

    def test_registry_with_violation_exits_one(self, tmp_path: Path) -> None:
        reg = _valid_registry()
        reg["gates"][0]["policy_refs"] = ["ghost-source"]
        path = tmp_path / "r.json"
        path.write_text(json.dumps(reg))
        assert gate.main(["verify", "--registry", str(path)]) == 1


# ---------------------------------------------------------------------------
# Loading helpers and defensive branches
# ---------------------------------------------------------------------------


class TestLoadingHelpers:
    def test_live_label_names_non_list(self) -> None:
        assert gate.live_label_names({"not": "a list"}) == frozenset()

    def test_live_label_names_skips_malformed_entries(self) -> None:
        data = [{"name": "type:fix"}, {"no_name": 1}, "stray"]
        assert gate.live_label_names(data) == frozenset({"type:fix"})

    def test_consumer_universe_unions_rename_and_retired(self) -> None:
        live = frozenset({"ops:retro-opened"})
        policy = {
            "labels": [{"rename_from": "harness:retro-opened"}],
            "retired_labels": [{"name": "layer:meta"}],
        }
        universe = gate.consumer_label_universe(live, policy)
        assert universe == frozenset(
            {"ops:retro-opened", "harness:retro-opened", "layer:meta"}
        )

    def test_registry_root_not_object(self) -> None:
        assert gate.verify_registry(
            ["not", "an", "object"], _SCHEMA, lambda _p: True, _LIVE, _CONSUMER
        ) == ["registry root is not a JSON object"]

    def test_non_dict_list_elements_are_skipped(self) -> None:
        reg = _valid_registry()
        reg["policy_sources"].append("stray")
        reg["gates"].append("stray")
        reg["clusters"].append("stray")
        reg["label_consumers"].append("stray")
        reg["label_routing"]["rules"].insert(0, "stray")
        # Stray non-dict entries are skipped, not crashed on; the valid
        # entries still validate clean.
        assert _verify(reg) == []

    def test_label_routing_not_object(self) -> None:
        reg = _valid_registry()
        reg["label_routing"] = ["not", "an", "object"]
        errors = _verify(reg)
        assert any("label_routing: missing or not an object" in e for e in errors)

    def test_unknown_gate_kind(self) -> None:
        reg = _valid_registry()
        reg["gates"][0]["kind"] = "mystery"
        errors = _verify(reg)
        assert any("unknown kind 'mystery'" in e for e in errors)

    def test_native_kind_with_script(self) -> None:
        reg = _valid_registry()
        reg["gates"][1]["script"] = "scripts/x.py"
        errors = _verify(reg)
        assert any("kind 'native' must not carry 'script'" in e for e in errors)

    def test_untracked_policy_source_path(self) -> None:
        reg = _valid_registry()
        errors = gate.verify_registry(
            reg,
            _SCHEMA,
            is_tracked=lambda p: p != ".github/labels.json",
            live_labels=_LIVE,
            consumer_labels=_CONSUMER,
        )
        assert any(".github/labels.json" in e and "not a tracked file" in e for e in errors)


class TestSchemaVocabErrors:
    def test_non_object_schema_raises(self) -> None:
        with pytest.raises(gate.SchemaError):
            gate.extract_schema_vocab(["not", "an", "object"])

    def test_enum_not_a_list_raises(self) -> None:
        schema = json.loads(json.dumps(_SCHEMA))
        schema["$defs"]["plane"]["enum"] = "not-a-list"
        with pytest.raises(gate.SchemaError):
            gate.extract_schema_vocab(schema)

    def test_required_not_a_list_raises(self) -> None:
        schema = json.loads(json.dumps(_SCHEMA))
        schema["required"] = "not-a-list"
        with pytest.raises(gate.SchemaError):
            gate.extract_schema_vocab(schema)


class TestTrackedChecker:
    def test_fallback_to_disk_without_git(self, tmp_path: Path) -> None:
        # A non-repository directory: git ls-files exits non-zero, so the
        # checker falls back to an on-disk file test.
        checker = gate.build_tracked_checker(tmp_path)
        (tmp_path / "present.txt").write_text("x")
        assert checker("present.txt") is True
        assert checker("absent.txt") is False

    def test_fallback_when_git_raises(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _raise(*_args: object, **_kwargs: object) -> None:
            raise OSError("git missing")

        monkeypatch.setattr(gate.subprocess, "run", _raise)
        checker = gate.build_tracked_checker(tmp_path)
        (tmp_path / "present.txt").write_text("x")
        assert checker("present.txt") is True
        assert checker("absent.txt") is False
