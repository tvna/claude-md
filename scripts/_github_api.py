from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

API_VERSION = "2022-11-28"


def apply_call(
    *,
    method: str,
    url: str,
    payload: dict[str, Any] | None,
    token: str,
    opener: Callable[[urllib.request.Request], Any] = urllib.request.urlopen,
    sleeper: Callable[[float], None] | None = None,
) -> tuple[int, str]:
    # Resolve the sleeper at call time (not as a captured default) so tests can
    # neutralise the real 5xx-retry backoff by patching ``time.sleep`` (#985).
    sleeper = sleeper if sleeper is not None else time.sleep
    last_code = 0
    last_body = ""

    for attempt in range(1, 4):
        data = None
        if payload is not None:
            data = json.dumps(payload, separators=(",", ":")).encode("utf-8")

        # S310 justification: callers construct `url` from `API_ROOT` (https://api.github.com)
        # + repo/path segments built from trusted env vars; opener is injectable for tests
        # but defaults to urllib.request.urlopen on the fixed https endpoint.
        request = urllib.request.Request(url, data=data, method=method)  # noqa: S310 — fixed https://api.github.com endpoint
        request.add_header("Authorization", f"Bearer {token}")
        request.add_header("Accept", "application/vnd.github+json")
        request.add_header("X-GitHub-Api-Version", API_VERSION)
        if payload is not None:
            request.add_header("Content-Type", "application/json")

        try:
            with opener(request) as response:
                last_code = int(response.status)
                last_body = response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as error:
            last_code = int(error.code)
            last_body = error.read().decode("utf-8", errors="replace")
        except urllib.error.URLError as error:
            last_code = 0
            last_body = str(error.reason)

        if 200 <= last_code < 300:
            break
        print(f"Attempt {attempt}: HTTP {_format_code(last_code)} for {method} {url}")
        if last_code != 0 and last_code < 500:
            break
        if attempt < 3:
            sleeper(attempt * 5)

    return last_code, last_body


def graphql_call(
    *,
    query: str,
    variables: dict[str, Any],
    token: str,
    opener: Callable[[urllib.request.Request], Any] = urllib.request.urlopen,
) -> tuple[int, dict[str, Any]]:
    """Execute a GitHub GraphQL query/mutation. Returns (http_status, response_dict)."""
    payload = json.dumps({"query": query, "variables": variables}, separators=(",", ":"))
    request = urllib.request.Request(
        "https://api.github.com/graphql",
        data=payload.encode("utf-8"),
        method="POST",
    )
    request.add_header("Authorization", f"Bearer {token}")
    request.add_header("Accept", "application/vnd.github+json")
    request.add_header("X-GitHub-Api-Version", API_VERSION)
    request.add_header("Content-Type", "application/json")
    try:
        with opener(request) as response:
            code = int(response.status)
            body_str = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as error:
        code = int(error.code)
        body_str = error.read().decode("utf-8", errors="replace")
    try:
        body = json.loads(body_str)
    except (json.JSONDecodeError, UnboundLocalError):
        body = {}
    return code, body if isinstance(body, dict) else {}


def _format_code(code: int) -> str:
    return "000" if code == 0 else str(code)
