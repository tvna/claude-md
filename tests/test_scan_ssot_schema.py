"""Tests for ``scripts/scan_ssot_schema.py``.

Covers the happy path (the real ``.gitapex/ssot.json`` validates), schema-shape
enforcement (types, ``additionalProperties``, ``minItems``, enums, non-object
array items), each referential-integrity failure class, the ordered-rules
invariant, schema-guard failures, and the ``main`` CLI contract (exit 0/1/64).

The synthetic-registry tests inject ``is_tracked``, ``live_labels``, and
``consumer_labels`` so no real ``git`` or filesystem state is required; the
real schema on disk supplies the shape vocabulary.

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
    """A minimal registry that validates against the real schema and fixtures."""
    return {
        "meta": {
            "schema_version": 1,
            "tracking_issue": 2246,
            "status": "adopted-design",
            "phase": "phase-0",
        },
        "policy_sources": [
            {
                "id": "label-policy",
                "path": ".github/label-policy.toml",
                "format": "toml",
                "authority": "label taxonomy design and live catalog",
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
                "policy_refs": ["label-policy"],
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


class TestLiveLabelNamesFromPolicy:
    def test_matches_synthetic_fixture(self, tmp_path: Path) -> None:
        policy_path = tmp_path / "label-policy.toml"
        policy_path.write_text(
            "\n".join(
                [
                    "[[labels]]",
                    'name = "type:fix"',
                    'status = "keep"',
                    'description = "Defect or broken workflow."',
                    'color = "d73a4a"',
                ]
            ),
            encoding="utf-8",
        )

        names = gate.live_label_names_from_policy(policy_path)

        assert names == frozenset({"type:fix"})


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
        policy = tomllib.loads((_REPO_ROOT / ".github/label-policy.toml").read_text())
        live = gate.live_label_names_from_policy(_REPO_ROOT / ".github/label-policy.toml")
        consumer = gate.consumer_label_universe(live, policy)
        assert gate.verify_registry(registry, _SCHEMA, lambda _p: True, live, consumer) == []


# ---------------------------------------------------------------------------
# Schema-shape enforcement (the full-schema gate the review asked for)
# ---------------------------------------------------------------------------


class TestSchemaEnforcement:
    def test_extra_top_level_property(self) -> None:
        reg = _valid_registry()
        reg["UNEXPECTED"] = "x"
        assert any("unexpected property 'UNEXPECTED'" in e for e in _verify(reg))

    def test_extra_property_in_gate(self) -> None:
        reg = _valid_registry()
        reg["gates"][0]["surprise"] = 1
        assert any("unexpected property 'surprise'" in e for e in _verify(reg))

    def test_non_object_array_item(self) -> None:
        reg = _valid_registry()
        reg["gates"].append("stray")
        assert any("expected type" in e and "gates[2]" in e for e in _verify(reg))

    def test_wrong_scalar_type_for_tracking_issue(self) -> None:
        reg = _valid_registry()
        reg["gates"][0]["tracking_issue"] = "not-int"
        assert any("tracking_issue" in e and "expected type" in e for e in _verify(reg))

    def test_null_where_string_required(self) -> None:
        reg = _valid_registry()
        reg["meta"]["status"] = None
        assert any("status" in e and "null" in e for e in _verify(reg))

    def test_empty_planes_violates_min_items(self) -> None:
        reg = _valid_registry()
        reg["gates"][0]["planes"] = []
        assert any("at least 1 item" in e for e in _verify(reg))

    def test_unknown_plane_enum(self) -> None:
        reg = _valid_registry()
        reg["gates"][0]["planes"] = ["bogus-plane"]
        assert any("'bogus-plane'" in e and "is not one of" in e for e in _verify(reg))

    def test_unknown_body_read_enum(self) -> None:
        reg = _valid_registry()
        reg["label_routing"]["rules"][0]["body_read"] = "maybe"
        assert any("'maybe'" in e and "is not one of" in e for e in _verify(reg))

    def test_unknown_gate_kind_enum(self) -> None:
        reg = _valid_registry()
        reg["gates"][0]["kind"] = "mystery"
        assert any("'mystery'" in e and "is not one of" in e for e in _verify(reg))

    def test_missing_required_field(self) -> None:
        reg = _valid_registry()
        del reg["meta"]["phase"]
        assert any("missing required field 'phase'" in e for e in _verify(reg))


# ---------------------------------------------------------------------------
# Schema guard (a truncated / broken schema must fail loud)
# ---------------------------------------------------------------------------


class TestSchemaGuard:
    def test_empty_schema_raises(self) -> None:
        with pytest.raises(gate.SchemaError):
            gate.verify_registry(_valid_registry(), {}, lambda _p: True, _LIVE, _CONSUMER)

    def test_non_object_schema_raises(self) -> None:
        with pytest.raises(gate.SchemaError):
            gate.verify_registry(_valid_registry(), [], lambda _p: True, _LIVE, _CONSUMER)

    def test_schema_missing_defs_raises(self) -> None:
        with pytest.raises(gate.SchemaError):
            gate.verify_registry(
                _valid_registry(),
                {"properties": {}, "required": []},
                lambda _p: True,
                _LIVE,
                _CONSUMER,
            )

    def test_unresolvable_ref_raises(self) -> None:
        schema = json.loads(json.dumps(_SCHEMA))
        schema["properties"]["meta"]["properties"]["schema_version"] = {
            "$ref": "#/$defs/does-not-exist"
        }
        with pytest.raises(gate.SchemaError):
            gate.verify_registry(_valid_registry(), schema, lambda _p: True, _LIVE, _CONSUMER)


# ---------------------------------------------------------------------------
# Referential-integrity failure classes
# ---------------------------------------------------------------------------


class TestReferentialIntegrity:
    def test_unresolved_policy_ref(self) -> None:
        reg = _valid_registry()
        reg["gates"][0]["policy_refs"] = ["ghost-source"]
        assert any("policy_ref 'ghost-source'" in e for e in _verify(reg))

    def test_unresolved_cluster(self) -> None:
        reg = _valid_registry()
        reg["gates"][0]["cluster"] = "ghost-cluster"
        assert any("cluster 'ghost-cluster'" in e for e in _verify(reg))

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

    def test_untracked_policy_source_path(self) -> None:
        reg = _valid_registry()
        errors = gate.verify_registry(
            reg,
            _SCHEMA,
            is_tracked=lambda p: p != ".github/label-policy.toml",
            live_labels=_LIVE,
            consumer_labels=_CONSUMER,
        )
        assert any(".github/label-policy.toml" in e and "not a tracked file" in e for e in errors)

    def test_routing_label_not_in_live_catalog(self) -> None:
        reg = _valid_registry()
        reg["label_routing"]["rules"][0]["if_any"] = ["type:ghost"]
        assert any("does not resolve against the live catalog" in e for e in _verify(reg))

    def test_consumer_label_not_in_union(self) -> None:
        reg = _valid_registry()
        reg["label_consumers"][0]["labels"] = ["type:ghost"]
        assert any("does not resolve" in e and "type:ghost" in e for e in _verify(reg))

    def test_script_kind_missing_script(self) -> None:
        reg = _valid_registry()
        del reg["gates"][0]["script"]
        assert any("kind 'script' requires a 'script' path" in e for e in _verify(reg))

    def test_native_kind_missing_native_rule(self) -> None:
        reg = _valid_registry()
        del reg["gates"][1]["native_rule"]
        assert any("kind 'native' requires a 'native_rule'" in e for e in _verify(reg))

    def test_script_kind_with_native_rule(self) -> None:
        reg = _valid_registry()
        reg["gates"][0]["native_rule"] = "deletion"
        assert any("must not carry 'native_rule'" in e for e in _verify(reg))

    def test_native_kind_with_script(self) -> None:
        reg = _valid_registry()
        reg["gates"][1]["script"] = "scripts/x.py"
        assert any("kind 'native' must not carry 'script'" in e for e in _verify(reg))


# ---------------------------------------------------------------------------
# Ordered-rules invariant
# ---------------------------------------------------------------------------


class TestOrderedRules:
    def test_no_default_rule(self) -> None:
        reg = _valid_registry()
        reg["label_routing"]["rules"] = [reg["label_routing"]["rules"][0]]
        assert any("exactly one default rule, found 0" in e for e in _verify(reg))

    def test_two_default_rules(self) -> None:
        reg = _valid_registry()
        reg["label_routing"]["rules"].insert(
            0, {"default": True, "action": "triage-needed", "body_read": "no"}
        )
        assert any("exactly one default rule, found 2" in e for e in _verify(reg))

    def test_default_rule_not_last(self) -> None:
        reg = _valid_registry()
        rules = reg["label_routing"]["rules"]
        rules[0], rules[1] = rules[1], rules[0]
        assert any("default rule must be last" in e for e in _verify(reg))


# ---------------------------------------------------------------------------
# Loading helpers
# ---------------------------------------------------------------------------


class TestLoadingHelpers:
    def test_consumer_universe_unions_rename_and_retired(self) -> None:
        live = frozenset({"ops:retro-opened"})
        policy = {
            "labels": [{"rename_from": "harness:retro-opened"}],
            "retired_labels": [{"name": "layer:meta"}],
        }
        assert gate.consumer_label_universe(live, policy) == frozenset(
            {"ops:retro-opened", "harness:retro-opened", "layer:meta"}
        )

    def test_registry_root_not_object(self) -> None:
        errors = gate.verify_registry(
            ["not", "an", "object"], _SCHEMA, lambda _p: True, _LIVE, _CONSUMER
        )
        assert any("expected type" in e for e in errors)


# ---------------------------------------------------------------------------
# git-tracked checker
# ---------------------------------------------------------------------------


class TestTrackedChecker:
    def test_fallback_to_disk_without_git(self, tmp_path: Path) -> None:
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
        assert gate.main(["verify", "--registry", str(tmp_path / "nope.json")]) == 1

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


class TestLabelPolicySource:
    def test_policy_derived_live_labels_pass(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        registry = _valid_registry()
        registry["label_consumers"][0]["labels"] = ["type:fix"]
        registry_path = tmp_path / "ssot.json"
        registry_path.write_text(json.dumps(registry), encoding="utf-8")
        schema_path = tmp_path / "ssot.schema.json"
        schema_path.write_text((_REPO_ROOT / ".gitapex" / "ssot.schema.json").read_text(), encoding="utf-8")
        policy_path = tmp_path / "label-policy.toml"
        policy_path.write_text(
            "\n".join(
                [
                    "[[labels]]",
                    'name = "type:fix"',
                    'status = "keep"',
                    'description = "Defect or broken workflow."',
                    'color = "d73a4a"',
                ]
            ),
            encoding="utf-8",
        )

        rc = gate.main(
            [
                "verify",
                "--registry",
                str(registry_path),
                "--schema",
                str(schema_path),
                "--label-policy",
                str(policy_path),
            ]
        )

        assert rc == 0, capsys.readouterr().err

    def test_malformed_policy_reports_error_not_traceback(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A semantically invalid policy-derived catalog (here: an
        unrecognized status) must exit 1 with an ::error:: line, the same
        malformed-input contract every other input file already gets --
        not an uncaught ValueError traceback."""
        registry_path = tmp_path / "ssot.json"
        registry_path.write_text(json.dumps(_valid_registry()), encoding="utf-8")
        schema_path = tmp_path / "ssot.schema.json"
        schema_path.write_text((_REPO_ROOT / ".gitapex" / "ssot.schema.json").read_text(), encoding="utf-8")
        policy_path = tmp_path / "label-policy.toml"
        policy_path.write_text(
            "\n".join(
                [
                    "[[labels]]",
                    'name = "type:fix"',
                    'status = "Keep"',
                    'description = "Typo-cased status."',
                    'color = "d73a4a"',
                ]
            ),
            encoding="utf-8",
        )

        rc = gate.main(
            [
                "verify",
                "--registry",
                str(registry_path),
                "--schema",
                str(schema_path),
                "--label-policy",
                str(policy_path),
            ]
        )

        assert rc == 1
        assert "::error::" in capsys.readouterr().err
