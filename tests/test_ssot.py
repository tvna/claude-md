"""Tests for ``scripts/_ssot.py``.

Exercises the reader against the real ``.gitapex/ssot.json`` (validated
separately by ``tests/test_scan_ssot_schema.py``), so these tests catch a
reader/registry contract break without duplicating shape validation.

Refs #2266, #2246, #1041.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import _ssot
import pytest

pytestmark = pytest.mark.shard_preflight


@pytest.fixture(autouse=True)
def _reset_ssot_cache() -> Iterator[None]:
    _ssot._reset_for_tests()
    yield
    _ssot._reset_for_tests()


def _write_registry(tmp_path: Path, data: object) -> Path:
    path = tmp_path / "ssot.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


class TestConsumerLabels:
    def test_returns_registered_labels_for_branch_cleanup(self) -> None:
        assert _ssot.consumer_labels("scripts/branch_cleanup.py") == (
            "layer:meta",
            "type:docs",
        )

    def test_raises_key_error_for_unknown_path(self) -> None:
        with pytest.raises(KeyError, match="no label_consumers entry"):
            _ssot.consumer_labels("scripts/does_not_exist.py")

    def test_raises_type_error_for_non_list_labels(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        registry = _write_registry(
            tmp_path,
            {"label_consumers": [{"path": "scripts/x.py", "labels": "not-a-list"}]},
        )
        monkeypatch.setattr(_ssot, "_REGISTRY_PATH", registry)
        with pytest.raises(TypeError, match="non-list labels"):
            _ssot.consumer_labels("scripts/x.py")


class TestRoutingRules:
    def test_returns_ordered_rules_ending_in_default(self) -> None:
        rules = _ssot.routing_rules()
        assert len(rules) > 0
        assert rules[-1].get("default") is True
        assert all(rule.get("default") is not True for rule in rules[:-1])

    def test_raises_type_error_for_missing_label_routing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        registry = _write_registry(tmp_path, {})
        monkeypatch.setattr(_ssot, "_REGISTRY_PATH", registry)
        with pytest.raises(TypeError, match="label_routing is missing"):
            _ssot.routing_rules()

    def test_raises_type_error_for_non_list_rules(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        registry = _write_registry(tmp_path, {"label_routing": {"rules": "nope"}})
        monkeypatch.setattr(_ssot, "_REGISTRY_PATH", registry)
        with pytest.raises(TypeError, match="label_routing.rules is missing"):
            _ssot.routing_rules()


class TestPolicySourcePath:
    def test_resolves_label_policy_to_repo_relative_path(self) -> None:
        path = _ssot.policy_source_path("label-policy")
        assert path == _ssot._REPO_ROOT / ".github" / "label-policy.toml"
        assert path.is_file()

    def test_raises_key_error_for_unknown_id(self) -> None:
        with pytest.raises(KeyError, match="no policy_sources entry"):
            _ssot.policy_source_path("does-not-exist")

    def test_raises_type_error_for_non_string_path(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        registry = _write_registry(tmp_path, {"policy_sources": [{"id": "x", "path": 123}]})
        monkeypatch.setattr(_ssot, "_REGISTRY_PATH", registry)
        with pytest.raises(TypeError, match="non-string path"):
            _ssot.policy_source_path("x")


class TestRequiredIssueAxes:
    def test_pins_layer_and_type_in_policy_order(self) -> None:
        # PIN-TEST: the required axes are cardinality-driven from the live
        # .github/label-policy.toml families. Today that must be exactly
        # {layer, type}. A future family/cardinality change that would silently
        # add or drop a required axis fails here deterministically.
        axes = _ssot.required_issue_axes()
        assert axes == ("layer", "type")
        assert set(axes) == {"layer", "type"}

    def _registry_pointing_at(self, tmp_path: Path, toml_text: str) -> Path:
        policy = tmp_path / "label-policy.toml"
        policy.write_text(toml_text, encoding="utf-8")
        # An absolute path in policy_sources resolves independently of _REPO_ROOT
        # (Path("/root") / "/abs" == Path("/abs")), so the reader reads this file.
        return _write_registry(
            tmp_path,
            {"policy_sources": [{"id": "label-policy", "path": str(policy)}]},
        )

    def test_selects_mandatory_cardinalities_only(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        toml_text = (
            '[[families]]\nname = "layer"\ncardinality = "one_or_more"\n'
            '[[families]]\nname = "type"\ncardinality = "exactly_one_for_normal_issues"\n'
            '[[families]]\nname = "state"\ncardinality = "zero_or_one"\n'
            '[[families]]\nname = "area"\ncardinality = "one_or_more_for_active_implementation"\n'
        )
        monkeypatch.setattr(_ssot, "_REGISTRY_PATH", self._registry_pointing_at(tmp_path, toml_text))
        assert _ssot.required_issue_axes() == ("layer", "type")

    def test_raises_runtime_error_when_no_mandatory_family(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        toml_text = '[[families]]\nname = "state"\ncardinality = "zero_or_one"\n'
        monkeypatch.setattr(_ssot, "_REGISTRY_PATH", self._registry_pointing_at(tmp_path, toml_text))
        with pytest.raises(RuntimeError, match="no mandatory-at-create family"):
            _ssot.required_issue_axes()

    def test_raises_type_error_for_missing_families(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(_ssot, "_REGISTRY_PATH", self._registry_pointing_at(tmp_path, 'title = "x"\n'))
        with pytest.raises(TypeError, match="non-list"):
            _ssot.required_issue_axes()

    def test_raises_type_error_for_non_string_cardinality(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        toml_text = '[[families]]\nname = "layer"\ncardinality = 1\n'
        monkeypatch.setattr(_ssot, "_REGISTRY_PATH", self._registry_pointing_at(tmp_path, toml_text))
        with pytest.raises(TypeError, match="non-string name/cardinality"):
            _ssot.required_issue_axes()

    def test_raises_runtime_error_for_invalid_toml(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(_ssot, "_REGISTRY_PATH", self._registry_pointing_at(tmp_path, "not = valid = toml"))
        with pytest.raises(RuntimeError, match="not valid TOML"):
            _ssot.required_issue_axes()

    def test_raises_key_error_for_missing_pointer(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        registry = _write_registry(tmp_path, {"policy_sources": []})
        monkeypatch.setattr(_ssot, "_REGISTRY_PATH", registry)
        with pytest.raises(KeyError, match="no policy_sources entry"):
            _ssot.required_issue_axes()


class TestResetForTests:
    def test_reset_makes_a_monkeypatched_path_take_effect(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _ssot.consumer_labels("scripts/branch_cleanup.py")  # populate the cache

        registry = _write_registry(
            tmp_path,
            {"label_consumers": [{"path": "scripts/x.py", "labels": ["area:example"]}]},
        )
        monkeypatch.setattr(_ssot, "_REGISTRY_PATH", registry)
        _ssot._reset_for_tests()

        assert _ssot.consumer_labels("scripts/x.py") == ("area:example",)
