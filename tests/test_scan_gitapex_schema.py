"""Tests for ``scripts/scan_gitapex_schema.py``.

Covers the happy path (the real ``.gitapex/*.toml`` files validate against
their sibling schemas), a missing-sibling-schema violation, an unparseable
TOML/schema file, a non-object schema root (``SchemaError``), a genuine shape
violation, and the ``main`` CLI contract (exit 0/1/64).

Refs #2342, #2252.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

import pytest
import scan_gitapex_schema as gate
from _json_schema_subset import validate_shape

pytestmark = pytest.mark.shard_preflight

_REPO_ROOT = Path(__file__).resolve().parent.parent


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


class TestDiscoverTomlFiles:
    def test_discovers_and_sorts(self, tmp_path: Path) -> None:
        _write(tmp_path / "b.toml", "")
        _write(tmp_path / "a.toml", "")
        _write(tmp_path / "not-toml.json", "{}")
        assert [p.name for p in gate.discover_toml_files(tmp_path)] == ["a.toml", "b.toml"]

    def test_empty_dir_returns_empty(self, tmp_path: Path) -> None:
        assert gate.discover_toml_files(tmp_path) == []


class TestVerifyFile:
    def test_missing_sibling_schema(self, tmp_path: Path) -> None:
        toml_path = _write(tmp_path / "name.toml", "a = 1\n")
        errors = gate.verify_file(toml_path, display="name.toml")
        assert any("no sibling schema" in e for e in errors)

    def test_unparseable_toml(self, tmp_path: Path) -> None:
        toml_path = _write(tmp_path / "name.toml", "not [ valid toml")
        _write(tmp_path / "name.schema.json", json.dumps({"type": "object"}))
        errors = gate.verify_file(toml_path, display="name.toml")
        assert any("cannot parse TOML" in e for e in errors)

    def test_unparseable_schema(self, tmp_path: Path) -> None:
        toml_path = _write(tmp_path / "name.toml", "a = 1\n")
        _write(tmp_path / "name.schema.json", "{ not json")
        errors = gate.verify_file(toml_path, display="name.toml")
        assert any("cannot parse JSON Schema" in e for e in errors)

    def test_non_object_schema_raises(self, tmp_path: Path) -> None:
        toml_path = _write(tmp_path / "name.toml", "a = 1\n")
        _write(tmp_path / "name.schema.json", json.dumps(["not", "an", "object"]))
        with pytest.raises(gate.SchemaError):
            gate.verify_file(toml_path, display="name.toml")

    def test_shape_violation(self, tmp_path: Path) -> None:
        toml_path = _write(tmp_path / "name.toml", "a = 1\n")
        schema = {"type": "object", "properties": {"a": {"type": "string"}}}
        _write(tmp_path / "name.schema.json", json.dumps(schema))
        errors = gate.verify_file(toml_path, display="name.toml")
        assert any("expected type string" in e for e in errors)

    def test_valid_file_has_no_errors(self, tmp_path: Path) -> None:
        toml_path = _write(tmp_path / "name.toml", "a = 1\n")
        schema = {"type": "object", "properties": {"a": {"type": "integer"}}}
        _write(tmp_path / "name.schema.json", json.dumps(schema))
        assert gate.verify_file(toml_path, display="name.toml") == []


class TestRealGitapexFiles:
    def test_every_gitapex_toml_has_a_sibling_schema(self) -> None:
        gitapex_dir = _REPO_ROOT / ".gitapex"
        for toml_path in gate.discover_toml_files(gitapex_dir):
            assert toml_path.with_suffix(".schema.json").is_file(), (
                f"{toml_path} has no sibling schema"
            )

    def test_real_files_validate(self) -> None:
        gitapex_dir = _REPO_ROOT / ".gitapex"
        errors: list[str] = []
        for toml_path in gate.discover_toml_files(gitapex_dir):
            errors.extend(
                gate.verify_file(toml_path, display=f".gitapex/{toml_path.name}")
            )
        assert errors == []


class TestLoopEngineeringAuditCheckSubschema:
    """Refs #2355: the ``check`` subschema must reject unknown fields.

    ``.gitapex/loop-engineering-audit.toml`` uses ``check.target`` (for
    ``kind = "path_exists"``/``"glob_exists"``) and ``check.glob``/
    ``check.pattern`` (for ``kind = "grep_in_glob"``); TestRealGitapexFiles
    above already proves the real file still validates. This class proves
    the schema is not so loose that a typo'd field name silently passes.
    """

    def _schema(self) -> dict[str, object]:
        schema_path = _REPO_ROOT / ".gitapex" / "loop-engineering-audit.schema.json"
        return json.loads(schema_path.read_text(encoding="utf-8"))

    def _minimal_item(self, check: Mapping[str, object]) -> dict[str, object]:
        return {
            "id": "x",
            "dimension": "d",
            "title": "t",
            "status": "present",
            "machine_checkable": True,
            "evidence": "e",
            "check": check,
        }

    def _instance(self, check: Mapping[str, object]) -> dict[str, object]:
        return {
            "meta": {
                "schema_version": 1,
                "source": "s",
                "audit_umbrella": "#1",
                "last_reviewed": "2026-07-05",
            },
            "items": [self._minimal_item(check)],
        }

    def test_known_check_fields_pass(self) -> None:
        schema = self._schema()
        for check in (
            {"kind": "path_exists", "target": "x"},
            {"kind": "glob_exists", "target": "x"},
            {"kind": "grep_in_glob", "glob": "x", "pattern": "y"},
        ):
            errors = validate_shape(self._instance(check), schema, root_path="root")
            assert errors == []

    def test_typo_field_is_rejected(self) -> None:
        schema = self._schema()
        errors = validate_shape(
            self._instance({"kind": "path_exists", "taget": "x"}), schema, root_path="root"
        )
        assert any("taget" in e for e in errors)


class TestCmdVerifyErrorAccumulation:
    def test_earlier_violation_survives_later_schema_error(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Refs #2355: a real shape violation in an earlier (sorted) file must
        # still be reported even when a later file's schema itself is broken
        # (raises SchemaError). Wrapping the whole loop in one try/except
        # dropped the earlier violation; wrapping per-file must not.
        _write(tmp_path / "a-bad-value.toml", "a = 1\n")
        _write(
            tmp_path / "a-bad-value.schema.json",
            json.dumps({"type": "object", "properties": {"a": {"type": "string"}}}),
        )
        _write(tmp_path / "b-broken-schema.toml", "a = 1\n")
        _write(tmp_path / "b-broken-schema.schema.json", json.dumps(["not", "an", "object"]))

        assert gate.main(["verify", "--gitapex-dir", str(tmp_path)]) == 1
        stderr = capsys.readouterr().err
        assert "expected type string" in stderr
        assert "schema root is not a JSON object" in stderr


class TestMainCli:
    def test_verify_exits_zero(self) -> None:
        assert gate.main(["verify"]) == 0

    def test_unknown_subcommand_exits_64(self) -> None:
        assert gate.main(["bogus"]) == 64

    def test_no_subcommand_exits_64(self) -> None:
        assert gate.main([]) == 64

    def test_missing_gitapex_dir_exits_one(self, tmp_path: Path) -> None:
        assert gate.main(["verify", "--gitapex-dir", str(tmp_path / "nope")]) == 1

    def test_toml_without_schema_exits_one(self, tmp_path: Path) -> None:
        _write(tmp_path / "orphan.toml", "a = 1\n")
        assert gate.main(["verify", "--gitapex-dir", str(tmp_path)]) == 1

    def test_valid_dir_exits_zero(self, tmp_path: Path) -> None:
        _write(tmp_path / "name.toml", "a = 1\n")
        _write(
            tmp_path / "name.schema.json",
            json.dumps({"type": "object", "properties": {"a": {"type": "integer"}}}),
        )
        assert gate.main(["verify", "--gitapex-dir", str(tmp_path)]) == 0
