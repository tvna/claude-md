"""Tests for ``scripts/ci_budget_issue.py`` (issue #1156).

The ``scripts/`` directory is added to ``sys.path`` via the ``pythonpath``
key under ``[tool.pytest.ini_options]`` in ``pyproject.toml``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import ci_budget_issue
import pytest

pytestmark = pytest.mark.shard_ci_ops


class _FakeApply:
    """Record apply_call invocations and return scripted (code, body) pairs."""

    def __init__(self, responses: list[tuple[int, str]]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def __call__(
        self, *, method: str, url: str, payload: Any, token: str
    ) -> tuple[int, str]:
        self.calls.append(
            {"method": method, "url": url, "payload": payload, "token": token}
        )
        return self._responses.pop(0)


_BREACHES = [{"job": "lint-scripts-pytest", "p50": 410.0}]


def _write_breach_file(
    tmp_path: Path, *, budget: float = 300.0, breaches: list[dict[str, Any]] | None = None
) -> Path:
    path = tmp_path / "budget.json"
    payload = {
        "budget_seconds": budget,
        "breaches": _BREACHES if breaches is None else breaches,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# parse_dry_run
# ---------------------------------------------------------------------------


class TestParseDryRun:
    @pytest.mark.parametrize("raw", ["true", "TRUE", "1", "yes"])
    def test_truthy(self, raw: str) -> None:
        assert ci_budget_issue.parse_dry_run(raw) is True

    @pytest.mark.parametrize("raw", ["false", "0", "no", ""])
    def test_falsy(self, raw: str) -> None:
        assert ci_budget_issue.parse_dry_run(raw) is False

    def test_invalid_raises(self) -> None:
        with pytest.raises(ValueError):
            ci_budget_issue.parse_dry_run("maybe")


# ---------------------------------------------------------------------------
# load_breaches
# ---------------------------------------------------------------------------


class TestLoadBreaches:
    def test_valid_payload(self, tmp_path: Path) -> None:
        path = _write_breach_file(tmp_path)
        budget, breaches = ci_budget_issue.load_breaches(path)
        assert budget == 300.0
        assert breaches == _BREACHES

    def test_empty_breaches(self, tmp_path: Path) -> None:
        path = _write_breach_file(tmp_path, breaches=[])
        budget, breaches = ci_budget_issue.load_breaches(path)
        assert budget == 300.0
        assert breaches == []

    def test_non_object_root_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "b.json"
        path.write_text(json.dumps([1, 2]), encoding="utf-8")
        with pytest.raises(ValueError):
            ci_budget_issue.load_breaches(path)

    def test_missing_budget_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "b.json"
        path.write_text(json.dumps({"breaches": []}), encoding="utf-8")
        with pytest.raises(ValueError):
            ci_budget_issue.load_breaches(path)

    def test_breaches_not_list_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "b.json"
        path.write_text(
            json.dumps({"budget_seconds": 300.0, "breaches": {}}), encoding="utf-8"
        )
        with pytest.raises(ValueError):
            ci_budget_issue.load_breaches(path)

    def test_malformed_entry_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "b.json"
        path.write_text(
            json.dumps({"budget_seconds": 300.0, "breaches": [{"job": "x"}]}),
            encoding="utf-8",
        )
        with pytest.raises(ValueError):
            ci_budget_issue.load_breaches(path)


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


class TestRendering:
    def test_issue_body_has_marker_and_facts(self) -> None:
        body = ci_budget_issue.render_issue_body(
            300.0, _BREACHES, run_url="https://example/run/1"
        )
        assert ci_budget_issue.ISSUE_MARKER in body
        assert f"Refs #{ci_budget_issue.PARENT_ISSUE}" in body
        assert "300.0" in body
        assert "lint-scripts-pytest" in body
        assert "410.0" in body
        assert "https://example/run/1" in body

    def test_issue_body_is_ascii(self) -> None:
        ci_budget_issue.render_issue_body(
            300.0, _BREACHES, run_url="https://example/run/1"
        ).encode("ascii")

    def test_update_comment_is_ascii_and_lists_jobs(self) -> None:
        comment = ci_budget_issue.render_update_comment(
            300.0, _BREACHES, run_url="https://example/run/2"
        )
        comment.encode("ascii")
        assert "lint-scripts-pytest" in comment
        assert "https://example/run/2" in comment


# ---------------------------------------------------------------------------
# find_existing_issue
# ---------------------------------------------------------------------------


class TestFindExistingIssue:
    def test_matches_marker_in_body(self) -> None:
        items = {
            "items": [{"number": 42, "body": ci_budget_issue.ISSUE_MARKER + "\n..."}]
        }
        apply = _FakeApply([(200, json.dumps(items))])
        assert (
            ci_budget_issue.find_existing_issue("o/r", "tok", apply_call=apply) == 42
        )
        assert apply.calls[0]["url"].startswith(
            "https://api.github.com/search/issues?q="
        )

    def test_ignores_lookalike_without_marker(self) -> None:
        items = {"items": [{"number": 9, "body": "no marker here"}]}
        apply = _FakeApply([(200, json.dumps(items))])
        assert (
            ci_budget_issue.find_existing_issue("o/r", "tok", apply_call=apply) is None
        )

    def test_empty_items_returns_none(self) -> None:
        apply = _FakeApply([(200, json.dumps({"items": []}))])
        assert (
            ci_budget_issue.find_existing_issue("o/r", "tok", apply_call=apply) is None
        )

    def test_non_2xx_raises(self) -> None:
        apply = _FakeApply([(403, "forbidden")])
        with pytest.raises(RuntimeError):
            ci_budget_issue.find_existing_issue("o/r", "tok", apply_call=apply)


# ---------------------------------------------------------------------------
# open_or_update_issue
# ---------------------------------------------------------------------------


class TestOpenOrUpdateIssue:
    def test_creates_when_absent(self) -> None:
        apply = _FakeApply(
            [(200, json.dumps({"items": []})), (201, json.dumps({"number": 100}))]
        )
        result = ci_budget_issue.open_or_update_issue(
            repo="o/r",
            token="tok",
            budget_seconds=300.0,
            breaches=_BREACHES,
            run_url="https://example/run",
            apply_call=apply,
        )
        assert result == "created"
        create = apply.calls[1]
        assert create["method"] == "POST"
        assert create["url"] == "https://api.github.com/repos/o/r/issues"
        assert create["payload"]["title"] == ci_budget_issue.ISSUE_TITLE
        assert create["payload"]["labels"] == list(ci_budget_issue.ISSUE_LABELS)

    def test_comments_when_present(self) -> None:
        items = {"items": [{"number": 55, "body": ci_budget_issue.ISSUE_MARKER}]}
        apply = _FakeApply([(200, json.dumps(items)), (201, "{}")])
        result = ci_budget_issue.open_or_update_issue(
            repo="o/r",
            token="tok",
            budget_seconds=300.0,
            breaches=_BREACHES,
            run_url="https://example/run",
            apply_call=apply,
        )
        assert result == "commented"
        comment = apply.calls[1]
        assert comment["url"] == (
            "https://api.github.com/repos/o/r/issues/55/comments"
        )

    def test_create_failure_raises(self) -> None:
        apply = _FakeApply([(200, json.dumps({"items": []})), (500, "boom")])
        with pytest.raises(RuntimeError):
            ci_budget_issue.open_or_update_issue(
                repo="o/r",
                token="tok",
                budget_seconds=300.0,
                breaches=_BREACHES,
                run_url="https://example/run",
                apply_call=apply,
            )


# ---------------------------------------------------------------------------
# CLI (run subcommand)
# ---------------------------------------------------------------------------


class TestRunCli:
    def test_no_breach_is_noop(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        path = _write_breach_file(tmp_path, breaches=[])
        called: list[bool] = []
        monkeypatch.setattr(
            ci_budget_issue,
            "open_or_update_issue",
            lambda **_: called.append(True),
        )
        rc = ci_budget_issue.main(["run", "--breach-file", str(path), "--repo", "o/r"])
        assert rc == 0
        assert called == []

    def test_dry_run_does_not_touch_github(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        path = _write_breach_file(tmp_path)
        called: list[bool] = []
        monkeypatch.setattr(
            ci_budget_issue,
            "open_or_update_issue",
            lambda **_: called.append(True),
        )
        rc = ci_budget_issue.main(
            ["run", "--breach-file", str(path), "--repo", "o/r", "--dry-run", "true"]
        )
        assert rc == 0
        assert called == []

    def test_missing_token_fails(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        path = _write_breach_file(tmp_path)
        monkeypatch.delenv("GH_TOKEN", raising=False)
        rc = ci_budget_issue.main(
            ["run", "--breach-file", str(path), "--repo", "o/r"]
        )
        assert rc == 1

    def test_real_run_opens_issue(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        path = _write_breach_file(tmp_path)
        monkeypatch.setenv("GH_TOKEN", "tok")
        captured: dict[str, Any] = {}

        def fake_open(**kwargs: Any) -> str:
            captured.update(kwargs)
            return "created"

        monkeypatch.setattr(ci_budget_issue, "open_or_update_issue", fake_open)
        rc = ci_budget_issue.main(
            [
                "run",
                "--breach-file",
                str(path),
                "--repo",
                "o/r",
                "--run-url",
                "https://example/run",
            ]
        )
        assert rc == 0
        assert captured["repo"] == "o/r"
        assert captured["breaches"] == _BREACHES
        assert captured["budget_seconds"] == 300.0

    def test_malformed_breach_file_returns_1(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        path = tmp_path / "b.json"
        path.write_text(json.dumps({"breaches": []}), encoding="utf-8")
        monkeypatch.setenv("GH_TOKEN", "tok")
        rc = ci_budget_issue.main(
            ["run", "--breach-file", str(path), "--repo", "o/r"]
        )
        assert rc == 1
