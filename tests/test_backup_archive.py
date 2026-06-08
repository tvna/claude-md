"""Tests for ``scripts/backup_archive.py``.

The ``scripts/`` directory is added to ``sys.path`` via the ``pythonpath``
key under ``[tool.pytest.ini_options]`` in ``pyproject.toml``.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import backup_archive as ba
import pytest

pytestmark = pytest.mark.shard_ci_ops


def _seed(indir: Path) -> None:
    indir.mkdir(parents=True, exist_ok=True)
    (indir / "issues.json").write_text(json.dumps([{"n": 1}, {"n": 2}]), encoding="utf-8")
    (indir / "pull_requests.json").write_text(json.dumps([{"n": 3}]), encoding="utf-8")
    (indir / "issue_comments.json").write_text(json.dumps([]), encoding="utf-8")
    (indir / "pull_request_review_comments.json").write_text(
        json.dumps([{"body": "テスト"}]), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# build_payload
# ---------------------------------------------------------------------------


class TestBuildPayload:
    def test_includes_metadata(self, tmp_path: Path) -> None:
        _seed(tmp_path)
        payload, _ = ba.build_payload(indir=tmp_path, timestamp="20260602T0000Z", repo="tvna/claude-md")
        assert payload["captured_at"] == "20260602T0000Z"
        assert payload["repo"] == "tvna/claude-md"

    def test_loads_all_sources_with_counts(self, tmp_path: Path) -> None:
        _seed(tmp_path)
        payload, counts = ba.build_payload(indir=tmp_path, timestamp="t", repo="r/r")
        assert counts == [
            ("issues", 2),
            ("pull_requests", 1),
            ("issue_comments", 0),
            ("pull_request_review_comments", 1),
        ]
        assert payload["issues"] == [{"n": 1}, {"n": 2}]

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        # Only seed one of the four files.
        (tmp_path / "issues.json").write_text("[]", encoding="utf-8")
        with pytest.raises(ValueError, match="missing capture file"):
            ba.build_payload(indir=tmp_path, timestamp="t", repo="r/r")

    def test_invalid_json_raises(self, tmp_path: Path) -> None:
        _seed(tmp_path)
        (tmp_path / "issues.json").write_text("{not json", encoding="utf-8")
        with pytest.raises(ValueError, match="invalid JSON"):
            ba.build_payload(indir=tmp_path, timestamp="t", repo="r/r")

    def test_non_list_json_raises(self, tmp_path: Path) -> None:
        _seed(tmp_path)
        (tmp_path / "issues.json").write_text(json.dumps({"not": "a list"}), encoding="utf-8")
        with pytest.raises(ValueError, match="expected a JSON list"):
            ba.build_payload(indir=tmp_path, timestamp="t", repo="r/r")


# ---------------------------------------------------------------------------
# write_gzip
# ---------------------------------------------------------------------------


class TestWriteGzip:
    def test_roundtrip_is_ascii_only(self, tmp_path: Path) -> None:
        payload = {"repo": "r/r", "items": [{"body": "テスト"}]}
        archive = tmp_path / "out.json.gz"
        ba.write_gzip(payload, archive)
        with gzip.open(archive, "rt", encoding="utf-8") as fh:
            text = fh.read()
        assert text.isascii()
        assert "\\u30c6" in text
        assert json.loads(text) == payload


# ---------------------------------------------------------------------------
# _cmd_build / main
# ---------------------------------------------------------------------------


class TestCmdBuild:
    def test_prints_counts_and_archive(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        _seed(tmp_path)
        archive = tmp_path / "originals.json.gz"
        rc = ba.main(
            [
                "build",
                "--indir",
                str(tmp_path),
                "--timestamp",
                "20260602T0000Z",
                "--repo",
                "tvna/claude-md",
                "--archive",
                str(archive),
            ]
        )
        assert rc == 0
        out = capsys.readouterr().out
        assert "issues: 2 items" in out
        assert f"Archive: {archive}" in out
        with gzip.open(archive, "rt", encoding="utf-8") as fh:
            payload = json.load(fh)
        assert payload["captured_at"] == "20260602T0000Z"
        assert set(payload) == {
            "captured_at",
            "repo",
            "issues",
            "pull_requests",
            "issue_comments",
            "pull_request_review_comments",
        }

    def test_returns_1_on_missing_capture(self, tmp_path: Path) -> None:
        (tmp_path / "issues.json").write_text("[]", encoding="utf-8")
        rc = ba.main(
            [
                "build",
                "--indir",
                str(tmp_path),
                "--timestamp",
                "t",
                "--repo",
                "r/r",
                "--archive",
                str(tmp_path / "out.json.gz"),
            ]
        )
        assert rc == 1
