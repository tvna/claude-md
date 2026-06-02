from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from _github_api import apply_call, graphql_call

pytestmark = pytest.mark.shard_ci_ops

class Response:
    def __init__(self, status: int, body: str = "") -> None:
        self.status = status
        self.body = body.encode()

    def __enter__(self) -> Response:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self.body

    def close(self) -> None:
        return None


def http_error(code: int, body: str = "") -> urllib.error.HTTPError:
    return urllib.error.HTTPError("https://example.test", code, "err", {}, Response(code, body))


def test_apply_call_happy_2xx_single_attempt() -> None:
    requests: list[urllib.request.Request] = []
    sleeps: list[float] = []

    def opener(request: urllib.request.Request) -> Response:
        requests.append(request)
        return Response(201, '{"ok":true}')

    code, body = apply_call(
        method="POST",
        url="https://example.test/labels",
        payload={"name": "bug"},
        token="token",
        opener=opener,
        sleeper=sleeps.append,
    )

    assert code == 201
    assert body == '{"ok":true}'
    assert sleeps == []
    assert requests[0].method == "POST"
    assert json.loads(requests[0].data.decode()) == {"name": "bug"}
    assert requests[0].headers["Authorization"] == "Bearer token"


def test_apply_call_retries_5xx_then_succeeds() -> None:
    responses = [http_error(503, "one"), http_error(502, "two"), Response(200, "ok")]
    sleeps: list[float] = []

    def opener(request: urllib.request.Request) -> Response:
        response = responses.pop(0)
        if isinstance(response, urllib.error.HTTPError):
            raise response
        return response

    code, body = apply_call(
        method="PATCH",
        url="https://example.test/labels/x",
        payload={"color": "ffffff"},
        token="token",
        opener=opener,
        sleeper=sleeps.append,
    )

    assert code == 200
    assert body == "ok"
    assert sleeps == [5, 10]


def test_apply_call_breaks_on_4xx() -> None:
    calls = 0
    sleeps: list[float] = []

    def opener(request: urllib.request.Request) -> Response:
        nonlocal calls
        calls += 1
        raise http_error(422, "bad")

    code, body = apply_call(
        method="PATCH",
        url="https://example.test/labels/x",
        payload={"color": "ffffff"},
        token="token",
        opener=opener,
        sleeper=sleeps.append,
    )

    assert code == 422
    assert body == "bad"
    assert calls == 1
    assert sleeps == []


def test_apply_call_curl_level_000_retries_three_times() -> None:
    sleeps: list[float] = []

    def opener(request: urllib.request.Request) -> Response:
        raise urllib.error.URLError("socket down")

    code, body = apply_call(
        method="DELETE",
        url="https://example.test/labels/x",
        payload=None,
        token="token",
        opener=opener,
        sleeper=sleeps.append,
    )

    assert code == 0
    assert body == "socket down"
    assert sleeps == [5, 10]


def test_apply_call_payload_none_has_no_body_or_content_type() -> None:
    requests: list[urllib.request.Request] = []

    def opener(request: urllib.request.Request) -> Response:
        requests.append(request)
        return Response(204, "")

    code, _ = apply_call(
        method="DELETE",
        url="https://example.test/labels/x",
        payload=None,
        token="token",
        opener=opener,
    )

    assert code == 204
    assert requests[0].data is None
    assert "Content-type" not in requests[0].headers


@pytest.mark.parametrize("code", [401, 403, 404, 429])
def test_apply_call_breaks_on_named_4xx_codes(code: int) -> None:
    calls = 0
    sleeps: list[float] = []

    def opener(request: urllib.request.Request) -> Response:
        nonlocal calls
        calls += 1
        raise http_error(code, f"body-{code}")

    result_code, result_body = apply_call(
        method="GET",
        url="https://example.test/x",
        payload=None,
        token="token",
        opener=opener,
        sleeper=sleeps.append,
    )

    assert result_code == code
    assert result_body == f"body-{code}"
    assert calls == 1
    assert sleeps == []


def test_apply_call_print_does_not_leak_bearer_token(capsys: pytest.CaptureFixture[str]) -> None:
    # Exercise every print branch in apply_call: 5xx-then-success and URLError.
    # A single absence assertion guards the format string against any future
    # refactor that adds the token to the same printed line.
    items: list[Response | BaseException] = [
        http_error(500, "server"),
        urllib.error.URLError("net"),
        Response(200, "ok"),
    ]

    def opener(request: urllib.request.Request) -> Response:
        item = items.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item

    apply_call(
        method="GET",
        url="https://example.test/x",
        payload=None,
        token="sentinel-DEADBEEF",
        opener=opener,
        sleeper=lambda _s: None,
    )

    captured = capsys.readouterr()
    assert "sentinel-DEADBEEF" not in captured.out
    assert "sentinel-DEADBEEF" not in captured.err


def test_apply_call_returns_body_verbatim_when_not_json() -> None:
    # apply_call is JSON-agnostic; callers parse. Documents that malformed
    # JSON is returned as-is rather than swallowed.
    def opener(request: urllib.request.Request) -> Response:
        return Response(200, "{not valid json")

    code, body = apply_call(
        method="GET",
        url="https://example.test/x",
        payload=None,
        token="token",
        opener=opener,
    )

    assert code == 200
    assert body == "{not valid json"


# ---------------------------------------------------------------------------
# graphql_call -- previously untested (#985 coverage top-up alongside the
# apply_call sleeper-seam change that lifts _github_api into the changed-set).
# ---------------------------------------------------------------------------


def test_graphql_call_happy_returns_parsed_dict() -> None:
    requests: list[urllib.request.Request] = []

    def opener(request: urllib.request.Request) -> Response:
        requests.append(request)
        return Response(200, '{"data":{"x":1}}')

    code, body = graphql_call(
        query="query { viewer { login } }",
        variables={"a": 1},
        token="token",
        opener=opener,
    )

    assert code == 200
    assert body == {"data": {"x": 1}}
    assert requests[0].method == "POST"
    assert requests[0].full_url == "https://api.github.com/graphql"
    assert requests[0].headers["Authorization"] == "Bearer token"
    assert json.loads(requests[0].data.decode()) == {
        "query": "query { viewer { login } }",
        "variables": {"a": 1},
    }


def test_graphql_call_http_error_returns_code_and_error_body() -> None:
    def opener(request: urllib.request.Request) -> Response:
        raise http_error(400, '{"message":"bad"}')

    code, body = graphql_call(
        query="mutation { x }",
        variables={},
        token="token",
        opener=opener,
    )

    assert code == 400
    assert body == {"message": "bad"}


def test_graphql_call_non_dict_json_yields_empty_dict() -> None:
    def opener(request: urllib.request.Request) -> Response:
        return Response(200, "[1, 2, 3]")

    code, body = graphql_call(query="q", variables={}, token="t", opener=opener)

    assert code == 200
    assert body == {}


def test_graphql_call_invalid_json_yields_empty_dict() -> None:
    def opener(request: urllib.request.Request) -> Response:
        return Response(200, "{not json")

    code, body = graphql_call(query="q", variables={}, token="t", opener=opener)

    assert code == 200
    assert body == {}


def test_graphql_call_url_error_yields_zero_and_empty_dict() -> None:
    # A network-level failure must degrade to (0, {}) rather than raising an
    # unhandled URLError traceback (CWE-703 regression guard).
    def opener(request: urllib.request.Request) -> Response:
        raise urllib.error.URLError("socket down")

    code, body = graphql_call(query="q", variables={}, token="t", opener=opener)

    assert code == 0
    assert body == {}


# ---------------------------------------------------------------------------
# _default_opener -- the production default must bound every call with a
# timeout so a stalled connection cannot hang the job (CWE-400 / CWE-770).
# ---------------------------------------------------------------------------


def test_default_opener_passes_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    import _github_api

    captured: dict[str, object] = {}

    def fake_urlopen(request: urllib.request.Request, timeout: float | None = None) -> Response:
        captured["timeout"] = timeout
        return Response(200, "ok")

    monkeypatch.setattr(_github_api.urllib.request, "urlopen", fake_urlopen)
    _github_api._default_opener(urllib.request.Request("https://api.github.com/x"))

    assert captured["timeout"] == _github_api._HTTP_TIMEOUT_SECONDS


def test_apply_call_uses_default_opener_with_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    # End-to-end: apply_call with no injected opener funnels through
    # _default_opener and therefore sets a timeout on the live urlopen.
    import _github_api

    captured: dict[str, object] = {}

    def fake_urlopen(request: urllib.request.Request, timeout: float | None = None) -> Response:
        captured["timeout"] = timeout
        return Response(200, "ok")

    monkeypatch.setattr(_github_api.urllib.request, "urlopen", fake_urlopen)
    code, body = apply_call(
        method="GET",
        url="https://api.github.com/x",
        payload=None,
        token="token",
    )

    assert code == 200
    assert body == "ok"
    assert captured["timeout"] == _github_api._HTTP_TIMEOUT_SECONDS
