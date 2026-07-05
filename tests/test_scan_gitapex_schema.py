"""Tests for ``scripts/scan_gitapex_schema.py``.

Covers the happy path (the real ``.gitapex/*.toml`` files validate against
their sibling schemas), a missing-sibling-schema violation, an unparseable
TOML/schema file, a non-object schema root (``SchemaError``), a genuine shape
violation, and the ``main`` CLI contract (exit 0/1/64).

Refs #2342, #2252.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import scan_gitapex_schema as gate

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
