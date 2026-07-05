"""Tests for ``scripts/_json_schema_subset.py``.

The shared draft-2020-12 subset engine (extracted from ``scan_ssot_schema.py``
in #2342 so ``scan_gitapex_schema.py`` can reuse it). Covers each supported
keyword (``type``, ``enum``, ``required``, ``properties``,
``additionalProperties`` (``true``/``false``/schema-object), ``items``,
``minItems``, and ``$ref``), plus the ``additionalProperties``-as-schema
extension #2342 added for the two dynamic-key ``*.enforcement.toml``
registries.

Refs #2252, #2342.
"""

from __future__ import annotations

import pytest
from _json_schema_subset import SchemaError, validate_shape

pytestmark = pytest.mark.shard_preflight


class TestTypeChecks:
    def test_matching_type_passes(self) -> None:
        assert validate_shape("hello", {"type": "string"}) == []

    def test_mismatched_type_fails(self) -> None:
        errors = validate_shape(1, {"type": "string"})
        assert any("expected type" in e for e in errors)

    def test_bool_is_not_integer(self) -> None:
        errors = validate_shape(True, {"type": "integer"})
        assert any("expected type" in e for e in errors)

    def test_bool_is_not_number(self) -> None:
        errors = validate_shape(False, {"type": "number"})
        assert any("expected type" in e for e in errors)

    def test_type_list_accepts_any_member(self) -> None:
        assert validate_shape(None, {"type": ["string", "null"]}) == []

    def test_null_type(self) -> None:
        assert validate_shape(None, {"type": "null"}) == []


class TestEnum:
    def test_value_in_enum_passes(self) -> None:
        assert validate_shape("a", {"enum": ["a", "b"]}) == []

    def test_value_outside_enum_fails(self) -> None:
        errors = validate_shape("c", {"enum": ["a", "b"]})
        assert any("is not one of" in e for e in errors)


class TestObjectShape:
    def test_missing_required_field(self) -> None:
        errors = validate_shape({}, {"type": "object", "required": ["a"]})
        assert any("missing required field 'a'" in e for e in errors)

    def test_additional_properties_false_rejects_extra_key(self) -> None:
        schema: dict[str, object] = {
            "type": "object",
            "properties": {"a": {"type": "string"}},
            "additionalProperties": False,
        }
        errors = validate_shape({"a": "x", "b": 1}, schema)
        assert any("unexpected property 'b'" in e for e in errors)

    def test_additional_properties_unset_allows_extra_key(self) -> None:
        schema: dict[str, object] = {"type": "object", "properties": {"a": {"type": "string"}}}
        assert validate_shape({"a": "x", "b": 1}, schema) == []

    def test_nested_property_validated(self) -> None:
        schema: dict[str, object] = {
            "type": "object",
            "properties": {"a": {"type": "integer"}},
        }
        errors = validate_shape({"a": "not an int"}, schema)
        assert any("a: expected type" in e for e in errors)

    def test_additional_properties_as_schema_validates_dynamic_keys(self) -> None:
        # The extension #2342 added for pr-body-quality.enforcement.toml /
        # workflow-script-quality.enforcement.toml, whose root tables have
        # fully dynamic keys (defect ids / M-ids) mapping to a fixed shape.
        schema: dict[str, object] = {
            "type": "object",
            "additionalProperties": {
                "type": "object",
                "required": ["status"],
                "properties": {"status": {"type": "string"}},
            },
        }
        instance: dict[str, object] = {
            "placeholder-residue": {"status": "doc-only"},
            "M1": {"status": 1},
        }
        errors = validate_shape(instance, schema)
        assert not any("placeholder-residue" in e for e in errors)
        assert any("M1.status" in e for e in errors)

    def test_additional_properties_as_schema_skips_declared_properties(self) -> None:
        # A key explicitly named in `properties` is validated by its own
        # subschema, not the dynamic-key `additionalProperties` schema.
        schema: dict[str, object] = {
            "type": "object",
            "properties": {"meta": {"type": "object"}},
            "additionalProperties": {"type": "string"},
        }
        assert validate_shape({"meta": {}, "extra": "ok"}, schema) == []


class TestArrayShape:
    def test_min_items_violation(self) -> None:
        errors = validate_shape([], {"type": "array", "minItems": 1})
        assert any("expected at least 1 item" in e for e in errors)

    def test_items_validated(self) -> None:
        errors = validate_shape([1, "two"], {"type": "array", "items": {"type": "integer"}})
        assert any("[1]: expected type" in e for e in errors)


class TestRef:
    def test_ref_resolves(self) -> None:
        schema: dict[str, object] = {
            "$defs": {"name": {"type": "string"}},
            "$ref": "#/$defs/name",
        }
        assert validate_shape("ok", schema) == []

    def test_unresolvable_ref_raises(self) -> None:
        with pytest.raises(SchemaError):
            validate_shape("x", {"$ref": "#/$defs/missing"})

    def test_ref_to_non_object_raises(self) -> None:
        with pytest.raises(SchemaError):
            validate_shape("x", {"$defs": {"name": "not-a-dict"}, "$ref": "#/$defs/name"})


class TestRootPath:
    def test_custom_root_path_used_in_messages(self) -> None:
        errors = validate_shape(1, {"type": "string"}, root_path="my-file.toml")
        assert errors == ["my-file.toml: expected type string, got int"]
