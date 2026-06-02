from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import github_paginate as gp

pytestmark = pytest.mark.shard_ci_ops


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, status: int, body: bytes, link: str = "") -> None:
        self.status = status
        self._body = body
        self.headers: dict[str, str] = {}
        if link:
            self.headers["Link"] = link

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        pass


def _make_opener(*responses: _FakeResponse) -> Any:
    responses_list = list(responses)
    idx = [0]

    def opener(request: Any) -> _FakeResponse:
        response = responses_list[idx[0]]
        idx[0] += 1
        return response

    return opener


# ---------------------------------------------------------------------------
# _paginate_get()
# ---------------------------------------------------------------------------


class TestPaginateGet:
    def test_returns_all_items_single_page(self) -> None:
        body = json.dumps([{"id": 1}, {"id": 2}]).encode("utf-8")
        opener = _make_opener(_FakeResponse(200, body))
        result = gp._paginate_get(url="https://api.github.com/repos/o/r/issues", token="tok", opener=opener)
        assert result == [{"id": 1}, {"id": 2}]

    def test_follows_link_header_to_next_page(self) -> None:
        page1_body = json.dumps([{"id": 1}]).encode("utf-8")
        page2_body = json.dumps([{"id": 2}]).encode("utf-8")
        link = '<https://api.github.com/repos/o/r/issues?page=2>; rel="next"'
        opener = _make_opener(
            _FakeResponse(200, page1_body, link=link),
            _FakeResponse(200, page2_body),
        )
        result = gp._paginate_get(url="https://api.github.com/repos/o/r/issues", token="tok", opener=opener)
        assert result == [{"id": 1}, {"id": 2}]

    def test_http_error_raises_runtime_error(self) -> None:
        body = json.dumps({"message": "Not Found"}).encode("utf-8")
        opener = _make_opener(_FakeResponse(404, body))
        with pytest.raises(RuntimeError, match="404"):
            gp._paginate_get(url="https://api.github.com/repos/o/r/issues", token="tok", opener=opener)

    def test_non_list_response_raises(self) -> None:
        body = json.dumps({"unexpected": "dict"}).encode("utf-8")
        opener = _make_opener(_FakeResponse(200, body))
        with pytest.raises(RuntimeError):
            gp._paginate_get(url="https://api.github.com/repos/o/r/issues", token="tok", opener=opener)

    def test_malformed_json_raises(self) -> None:
        opener = _make_opener(_FakeResponse(200, b"not-json"))
        with pytest.raises(RuntimeError):
            gp._paginate_get(url="https://api.github.com/repos/o/r/issues", token="tok", opener=opener)


# ---------------------------------------------------------------------------
# _cmd_fetch() / fetch subcommand
# ---------------------------------------------------------------------------


class TestCmdFetch:
    def test_writes_json_output(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("GH_TOKEN", "tok")
        captured_urls: list[str] = []

        def fake_paginate(*, url: str, token: str, **kw: Any) -> list[dict[str, Any]]:
            captured_urls.append(url)
            return [{"id": 1}, {"id": 2}]

        monkeypatch.setattr(gp, "_paginate_get", fake_paginate)
        out = tmp_path / "issues.json"
        rc = gp.main(["fetch", "--path", "repos/o/r/issues?state=all", "--output", str(out)])
        assert rc == 0
        assert json.loads(out.read_text(encoding="utf-8")) == [{"id": 1}, {"id": 2}]

    def test_path_prepends_api_root(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("GH_TOKEN", "tok")
        captured_urls: list[str] = []

        def fake_paginate(*, url: str, token: str, **kw: Any) -> list[dict[str, Any]]:
            captured_urls.append(url)
            return []

        monkeypatch.setattr(gp, "_paginate_get", fake_paginate)
        out = tmp_path / "out.json"
        gp.main(["fetch", "--path", "repos/o/r/issues", "--output", str(out)])
        assert captured_urls[0].startswith("https://api.github.com/")
        assert "repos/o/r/issues" in captured_urls[0]

    def test_missing_token_returns_1(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.delenv("GH_TOKEN", raising=False)
        out = tmp_path / "out.json"
        rc = gp.main(["fetch", "--path", "repos/o/r/issues", "--output", str(out)])
        assert rc == 1
        assert "GH_TOKEN" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# _get_single()
# ---------------------------------------------------------------------------


class TestGetSingle:
    def test_returns_body_as_string(self) -> None:
        body = json.dumps({"default_branch": "main"}).encode("utf-8")
        opener = _make_opener(_FakeResponse(200, body))
        result = gp._get_single(url="https://api.github.com/repos/o/r", token="tok", opener=opener)
        assert result == json.dumps({"default_branch": "main"})

    def test_http_error_raises_runtime_error(self) -> None:
        body = json.dumps({"message": "Not Found"}).encode("utf-8")
        opener = _make_opener(_FakeResponse(404, body))
        with pytest.raises(RuntimeError, match="404"):
            gp._get_single(url="https://api.github.com/repos/o/r", token="tok", opener=opener)


# ---------------------------------------------------------------------------
# _cmd_get() / get subcommand
# ---------------------------------------------------------------------------


class TestCmdGet:
    def test_writes_output_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("GH_TOKEN", "tok")
        payload = {"default_branch": "main", "id": 1}
        monkeypatch.setattr(gp, "_get_single", lambda **kw: json.dumps(payload))
        out = tmp_path / "repo.json"
        rc = gp.main(["get", "--path", "repos/o/r", "--output", str(out)])
        assert rc == 0
        assert json.loads(out.read_text(encoding="utf-8")) == payload

    def test_prints_field_to_stdout(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setenv("GH_TOKEN", "tok")
        monkeypatch.setattr(gp, "_get_single", lambda **kw: json.dumps({"default_branch": "main"}))
        rc = gp.main(["get", "--path", "repos/o/r", "--field", "default_branch"])
        assert rc == 0
        assert capsys.readouterr().out.strip() == "main"

    def test_output_and_field_together(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setenv("GH_TOKEN", "tok")
        payload = {"default_branch": "main"}
        monkeypatch.setattr(gp, "_get_single", lambda **kw: json.dumps(payload))
        out = tmp_path / "repo.json"
        rc = gp.main(["get", "--path", "repos/o/r", "--output", str(out), "--field", "default_branch"])
        assert rc == 0
        assert json.loads(out.read_text(encoding="utf-8")) == payload
        assert capsys.readouterr().out.strip() == "main"

    def test_path_prepends_api_root(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("GH_TOKEN", "tok")
        captured_urls: list[str] = []

        def fake_get(*, url: str, token: str, **kw: Any) -> str:
            captured_urls.append(url)
            return json.dumps({"default_branch": "main"})

        monkeypatch.setattr(gp, "_get_single", fake_get)
        gp.main(["get", "--path", "repos/o/r", "--field", "default_branch"])
        assert captured_urls[0].startswith("https://api.github.com/")
        assert "repos/o/r" in captured_urls[0]

    def test_missing_token_returns_1(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.delenv("GH_TOKEN", raising=False)
        rc = gp.main(["get", "--path", "repos/o/r", "--field", "default_branch"])
        assert rc == 1
        assert "GH_TOKEN" in capsys.readouterr().err

    def test_no_output_no_field_returns_1(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setenv("GH_TOKEN", "tok")
        rc = gp.main(["get", "--path", "repos/o/r"])
        assert rc == 1
        assert capsys.readouterr().err

    def test_missing_field_returns_1(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setenv("GH_TOKEN", "tok")
        monkeypatch.setattr(gp, "_get_single", lambda **kw: json.dumps({"other": "value"}))
        rc = gp.main(["get", "--path", "repos/o/r", "--field", "nonexistent"])
        assert rc == 1
        assert "nonexistent" in capsys.readouterr().err

    def test_api_error_returns_1(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setenv("GH_TOKEN", "tok")

        def raise_error(**kw: Any) -> str:
            raise RuntimeError("HTTP 404: Not Found")

        monkeypatch.setattr(gp, "_get_single", raise_error)
        rc = gp.main(["get", "--path", "repos/o/r", "--field", "default_branch"])
        assert rc == 1
        assert "404" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# extract_run_ids()
# ---------------------------------------------------------------------------


class TestExtractRunIds:
    def test_parses_ids(self) -> None:
        text = json.dumps({"workflow_runs": [{"id": 11}, {"id": 22}]})
        assert gp.extract_run_ids(text) == [11, 22]

    def test_empty_when_no_runs_key(self) -> None:
        assert gp.extract_run_ids(json.dumps({"total_count": 0})) == []

    def test_empty_when_runs_empty(self) -> None:
        assert gp.extract_run_ids(json.dumps({"workflow_runs": []})) == []

    def test_skips_entries_without_id(self) -> None:
        text = json.dumps({"workflow_runs": [{"id": 1}, {"name": "no id"}]})
        assert gp.extract_run_ids(text) == [1]

    def test_malformed_json_raises(self) -> None:
        with pytest.raises(ValueError, match="invalid JSON"):
            gp.extract_run_ids("not-json")


# ---------------------------------------------------------------------------
# _cmd_fetch_run_jobs() / fetch-run-jobs subcommand
# ---------------------------------------------------------------------------


class TestCmdFetchRunJobs:
    def test_writes_per_run_files(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GH_TOKEN", "tok")
        runs = tmp_path / "runs.json"
        runs.write_text(json.dumps({"workflow_runs": [{"id": 11}, {"id": 22}]}), encoding="utf-8")
        captured_urls: list[str] = []

        def fake_get(*, url: str, token: str, **kw: Any) -> str:
            captured_urls.append(url)
            return json.dumps({"jobs": [{"id": url}]})

        monkeypatch.setattr(gp, "_get_single", fake_get)
        outdir = tmp_path / "jobs"
        rc = gp.main(["fetch-run-jobs", "--runs", str(runs), "--repo", "o/r", "--outdir", str(outdir)])
        assert rc == 0
        assert (outdir / "11.json").exists()
        assert (outdir / "22.json").exists()
        assert captured_urls[0] == "https://api.github.com/repos/o/r/actions/runs/11/jobs"

    def test_no_runs_writes_nothing(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GH_TOKEN", "tok")
        runs = tmp_path / "runs.json"
        runs.write_text(json.dumps({"workflow_runs": []}), encoding="utf-8")
        outdir = tmp_path / "jobs"
        rc = gp.main(["fetch-run-jobs", "--runs", str(runs), "--repo", "o/r", "--outdir", str(outdir)])
        assert rc == 0
        assert list(outdir.iterdir()) == []

    def test_missing_token_returns_1(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.delenv("GH_TOKEN", raising=False)
        rc = gp.main(["fetch-run-jobs", "--runs", str(tmp_path / "r.json"), "--repo", "o/r", "--outdir", str(tmp_path)])
        assert rc == 1
        assert "GH_TOKEN" in capsys.readouterr().err

    def test_unreadable_runs_file_returns_1(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setenv("GH_TOKEN", "tok")
        rc = gp.main(
            ["fetch-run-jobs", "--runs", str(tmp_path / "missing.json"), "--repo", "o/r", "--outdir", str(tmp_path)]
        )
        assert rc == 1
        assert capsys.readouterr().err

    def test_api_error_returns_1(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setenv("GH_TOKEN", "tok")
        runs = tmp_path / "runs.json"
        runs.write_text(json.dumps({"workflow_runs": [{"id": 11}]}), encoding="utf-8")

        def raise_error(**kw: Any) -> str:
            raise RuntimeError("HTTP 500: boom")

        monkeypatch.setattr(gp, "_get_single", raise_error)
        rc = gp.main(["fetch-run-jobs", "--runs", str(runs), "--repo", "o/r", "--outdir", str(tmp_path / "jobs")])
        assert rc == 1
        assert "500" in capsys.readouterr().err
