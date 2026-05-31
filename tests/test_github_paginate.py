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
