#!/usr/bin/env python3
"""Shared draft-2020-12 JSON Schema subset validator.

Extracted from ``scan_ssot_schema.py`` (#2252) so ``scan_gitapex_schema.py``
(#2342) can validate a different registry/schema pair without duplicating the
engine. Supports ``type``, ``enum``, ``required``, ``properties``,
``additionalProperties`` (as ``true``/``false`` or as a schema object, the
extension #2342 needed to validate the two ``*.enforcement.toml`` registries,
whose root tables have fully dynamic keys), ``items``, ``minItems``, and
``$ref`` into ``$defs``.

This module has no CLI of its own; it is a private (``_``-prefixed) helper
imported by gate scripts, mirroring the repo's existing ``_*.py`` shared-helper
convention (e.g. ``_ssot.py``, ``_retry.sh``).

Contract:
- Inputs: none (pure functions only).
- Outputs: :func:`validate_shape` returns a list of violation strings; empty
  means the instance conforms to the schema.
- Failure policy: :class:`SchemaError` is raised only by callers that choose
  to assert their own schema-shape preconditions before calling
  :func:`validate_shape`; this module itself never raises.

Tested indirectly by ``tests/test_scan_ssot_schema.py`` and
``tests/test_scan_gitapex_schema.py``. Refs #2252, #2342.
"""

from __future__ import annotations

from collections.abc import Callable


class SchemaError(Exception):
    """Raised by callers when a schema itself is missing a structure they read."""


_TYPE_CHECKS: dict[str, Callable[[object], bool]] = {
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "string": lambda v: isinstance(v, str),
    # bool is a subclass of int; an integer field must reject True/False.
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, int | float) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "null": lambda v: v is None,
}


def _as_list(value: object) -> list[object]:
    return value if isinstance(value, list) else []


def _resolve_ref(root: dict[str, object], ref: str) -> dict[str, object]:
    node: object = root
    for part in ref.lstrip("#/").split("/"):
        if not isinstance(node, dict) or part not in node:
            raise SchemaError(f"schema $ref {ref!r} does not resolve")
        node = node[part]
    if not isinstance(node, dict):
        raise SchemaError(f"schema $ref {ref!r} does not resolve to an object")
    return node


def _type_name(value: object) -> str:
    return "null" if value is None else type(value).__name__


def _validate_instance(
    instance: object,
    schema: dict[str, object],
    root: dict[str, object],
    path: str,
    errors: list[str],
) -> None:
    """Validate *instance* against the *schema* subset, appending violations."""
    ref = schema.get("$ref")
    if isinstance(ref, str):
        schema = _resolve_ref(root, ref)

    declared_type = schema.get("type")
    if declared_type is not None:
        types = declared_type if isinstance(declared_type, list) else [declared_type]
        if not any(_TYPE_CHECKS.get(str(t), lambda _v: True)(instance) for t in types):
            errors.append(f"{path}: expected type {declared_type}, got {_type_name(instance)}")
            return

    enum = schema.get("enum")
    if isinstance(enum, list) and instance not in enum:
        errors.append(f"{path}: {instance!r} is not one of {enum}")

    if isinstance(instance, dict):
        properties = schema.get("properties")
        properties = properties if isinstance(properties, dict) else {}
        for key in _as_list(schema.get("required")):
            if key not in instance:
                errors.append(f"{path}: missing required field {key!r}")
        additional = schema.get("additionalProperties")
        if additional is False:
            for key in instance:
                if key not in properties:
                    errors.append(f"{path}: unexpected property {key!r}")
        elif isinstance(additional, dict):
            # Dynamic-key map: every key not explicitly named in `properties`
            # is validated against this shared value schema instead of being
            # hardcoded, so a new key (e.g. a new defect class or M-id) needs
            # no schema edit; only the referential-integrity gate that
            # already owns that key set (e.g. scan_pr_body_quality_drift.py).
            for key, value in instance.items():
                if key not in properties:
                    _validate_instance(value, additional, root, f"{path}.{key}", errors)
        for key, subschema in properties.items():
            if key in instance and isinstance(subschema, dict):
                _validate_instance(instance[key], subschema, root, f"{path}.{key}", errors)
    elif isinstance(instance, list):
        min_items = schema.get("minItems")
        if isinstance(min_items, int) and len(instance) < min_items:
            errors.append(f"{path}: expected at least {min_items} item(s), got {len(instance)}")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for idx, item in enumerate(instance):
                _validate_instance(item, item_schema, root, f"{path}[{idx}]", errors)


def validate_shape(instance: object, schema: dict[str, object], *, root_path: str = "root") -> list[str]:
    """Return schema-conformance violations for *instance* against *schema*."""
    errors: list[str] = []
    _validate_instance(instance, schema, schema, root_path, errors)
    return errors
