"""Tests for ``scripts/validate_json_syntax.py``.

The ``scripts/`` directory is added to ``sys.path`` via the ``pythonpath``
key under ``[tool.pytest.ini_options]`` in ``pyproject.toml``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import validate_json_syntax as vjs

pytestmark = pytest.mark.shard_ci_ops


class TestValidateFiles:
    def test_valid_files_return_empty(self, tmp_path: Path) -> None:
        a = tmp_path / "a.json"
        b = tmp_path / "b.json"
        a.write_text('{"ok": true}', encoding="utf-8")
        b.write_text("[1, 2, 3]", encoding="utf-8")
        assert vjs.validate_files([str(a), str(b)]) == []

    def test_invalid_json_reported(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.json"
        bad.write_text("{not valid", encoding="utf-8")
        errors = vjs.validate_files([str(bad)])
        assert len(errors) == 1
        assert errors[0][0] == str(bad)
        assert "invalid JSON" in errors[0][1]

    def test_missing_file_reported(self, tmp_path: Path) -> None:
        missing = tmp_path / "nope.json"
        errors = vjs.validate_files([str(missing)])
        assert len(errors) == 1
        assert "unreadable" in errors[0][1]

    def test_mixed_valid_and_invalid(self, tmp_path: Path) -> None:
        good = tmp_path / "good.json"
        bad = tmp_path / "bad.json"
        good.write_text("{}", encoding="utf-8")
        bad.write_text("nope", encoding="utf-8")
        errors = vjs.validate_files([str(good), str(bad)])
        assert [e[0] for e in errors] == [str(bad)]


class TestMain:
    def test_verify_exits_0_for_valid(self, tmp_path: Path) -> None:
        f = tmp_path / "x.json"
        f.write_text("[]", encoding="utf-8")
        assert vjs.main(["verify", "--file", str(f)]) == 0

    def test_verify_exits_1_and_annotates(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        f = tmp_path / "x.json"
        f.write_text("{bad", encoding="utf-8")
        rc = vjs.main(["verify", "--file", str(f)])
        assert rc == 1
        assert f"::error file={f}::" in capsys.readouterr().err

    def test_real_ruleset_files_are_valid(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        rulesets = repo_root / ".github" / "rulesets"
        files = [str(p) for p in (rulesets / "main.json", rulesets / "all-branches.json")]
        assert vjs.validate_files(files) == []
