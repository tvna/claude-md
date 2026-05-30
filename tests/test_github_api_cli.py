"""Tests for ``scripts/github_api.py`` CLI wrapper.

Verifies that:
- GET requests pass through and return the full body.
- --fields filters top-level JSON keys (object and array).
- HTTP errors exit 1 and print to stderr.
- Missing token exits 2.
- Invalid URL exits 2.
- --payload parses and forwards JSON.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from github_api import _filter_fields, main

pytestmark = pytest.mark.shard_ci_ops


class TestFilterFields:
    def test_dict_keeps_requested_fields(self) -> None:
        data = {"number": 1, "title": "foo", "state": "open", "body": "bar"}
        result = _filter_fields(data, ["number", "title"])
        assert result == {"number": 1, "title": "foo"}

    def test_list_filters_each_item(self) -> None:
        data = [{"number": 1, "title": "a", "body": "x"}, {"number": 2, "title": "b", "body": "y"}]
        result = _filter_fields(data, ["number", "title"])
        assert result == [{"number": 1, "title": "a"}, {"number": 2, "title": "b"}]

    def test_empty_fields_returns_unchanged(self) -> None:
        data = {"a": 1, "b": 2}
        assert _filter_fields(data, []) == {"a": 1, "b": 2}

    def test_non_dict_list_items_returned_as_is(self) -> None:
        data = [1, 2, 3]
        assert _filter_fields(data, ["x"]) == [1, 2, 3]

    def test_scalar_returned_as_is(self) -> None:
        assert _filter_fields("plain", ["x"]) == "plain"


class Response:
    def __init__(self, status: int, body: str = "") -> None:
        self.status = status
        self._body = body.encode()

    def __enter__(self) -> Response:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self._body


def http_error(code: int, body: str = "") -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        "https://example.test", code, "err", {}, Response(code, body)
    )


class TestMain:
    def _run(
        self,
        argv: list[str],
        monkeypatch: pytest.MonkeyPatch,
        responses: list[Response] | None = None,
    ) -> tuple[int, str, str]:
        import io

        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()
        monkeypatch.setattr("sys.stdout", stdout_buf)
        monkeypatch.setattr("sys.stderr", stderr_buf)

        if responses is not None:
            def fake_opener(request: urllib.request.Request) -> Response:
                r = responses.pop(0)
                if isinstance(r, BaseException):
                    raise r
                return r

            import _github_api
            monkeypatch.setattr(_github_api, "urllib", urllib)

            import github_api as gapi
            monkeypatch.setattr(
                gapi,
                "apply_call",
                lambda **kwargs: (
                    responses[0].status,
                    responses.pop(0).read().decode(),
                )
                if responses
                else (200, ""),
            )

        rc = main(argv)
        return rc, stdout_buf.getvalue(), stderr_buf.getvalue()

    def test_missing_token_exits_2(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("GH_TOKEN", raising=False)
        import io
        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()
        monkeypatch.setattr("sys.stdout", stdout_buf)
        monkeypatch.setattr("sys.stderr", stderr_buf)
        rc = main(["GET", "https://api.github.com/repos/o/r/issues"])
        assert rc == 2
        assert "token" in stderr_buf.getvalue()

    def test_invalid_url_exits_2(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GH_TOKEN", "tok")
        import io
        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()
        monkeypatch.setattr("sys.stdout", stdout_buf)
        monkeypatch.setattr("sys.stderr", stderr_buf)
        rc = main(["GET", "https://example.com/not-github"])
        assert rc == 2
        assert "api.github.com" in stderr_buf.getvalue()

    def test_successful_get_returns_body(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GH_TOKEN", "tok")
        body = json.dumps([{"number": 1, "title": "foo"}])
        import io

        import github_api as gapi
        monkeypatch.setattr(gapi, "apply_call", lambda **_: (200, body))

        stdout_buf = io.StringIO()
        monkeypatch.setattr("sys.stdout", stdout_buf)
        monkeypatch.setattr("sys.stderr", io.StringIO())

        rc = main(["GET", "https://api.github.com/repos/o/r/issues"])
        assert rc == 0
        assert stdout_buf.getvalue() == body

    def test_fields_filter_applied(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GH_TOKEN", "tok")
        body = json.dumps([{"number": 1, "title": "foo", "body": "bar"}])
        import io

        import github_api as gapi
        monkeypatch.setattr(gapi, "apply_call", lambda **_: (200, body))

        stdout_buf = io.StringIO()
        monkeypatch.setattr("sys.stdout", stdout_buf)
        monkeypatch.setattr("sys.stderr", io.StringIO())

        rc = main(["GET", "https://api.github.com/repos/o/r/issues", "--fields", "number,title"])
        assert rc == 0
        result = json.loads(stdout_buf.getvalue())
        assert result == [{"number": 1, "title": "foo"}]

    def test_http_error_exits_1(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GH_TOKEN", "tok")
        import io

        import github_api as gapi
        monkeypatch.setattr(gapi, "apply_call", lambda **_: (404, "not found"))

        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()
        monkeypatch.setattr("sys.stdout", stdout_buf)
        monkeypatch.setattr("sys.stderr", stderr_buf)

        rc = main(["GET", "https://api.github.com/repos/o/r/issues/999"])
        assert rc == 1
        assert "404" in stderr_buf.getvalue()

    def test_invalid_payload_json_exits_2(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GH_TOKEN", "tok")
        import io

        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()
        monkeypatch.setattr("sys.stdout", stdout_buf)
        monkeypatch.setattr("sys.stderr", stderr_buf)

        rc = main(
            [
                "POST",
                "https://api.github.com/repos/o/r/issues",
                "--payload",
                "{not valid json",
            ]
        )
        assert rc == 2
        assert "JSON" in stderr_buf.getvalue()
