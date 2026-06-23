from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from typing import Any

API_VERSION = "2022-11-28"

# GitHub serves release-asset uploads from a separate host (binary body,
# not JSON), so the asset uploader below targets this fixed endpoint while
# every other call stays on https://api.github.com. Keeping both on this
# module preserves the single-HTTP-boundary invariant (must-have M7).
_UPLOADS_ROOT = "https://uploads.github.com"

# Bound every GitHub API call so a stalled connection cannot hang the
# workflow job until the runner-level timeout fires (CWE-400 / CWE-770).
# Matches the 30s used at the threat-intel HTTP boundary.
_HTTP_TIMEOUT_SECONDS = 30


def _default_opener(request: urllib.request.Request) -> Any:
    """Open *request* against the fixed https GitHub API with a timeout.

    Baking the timeout into the default opener keeps the injected test
    openers single-argument while ensuring production calls never block
    without bound.
    """
    # S310 justification: the request URL is always the fixed
    # https://api.github.com endpoint built by the callers in this module.
    return urllib.request.urlopen(request, timeout=_HTTP_TIMEOUT_SECONDS)  # noqa: S310 -- fixed https://api.github.com endpoint


def apply_call(
    *,
    method: str,
    url: str,
    payload: dict[str, Any] | None,
    token: str,
    opener: Callable[[urllib.request.Request], Any] = _default_opener,
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
        request = urllib.request.Request(url, data=data, method=method)  # noqa: S310 -- fixed https://api.github.com endpoint
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


def upload_release_asset(
    *,
    repo: str,
    release_id: int,
    name: str,
    content: bytes,
    content_type: str,
    token: str,
    opener: Callable[[urllib.request.Request], Any] = _default_opener,
    sleeper: Callable[[float], None] | None = None,
) -> tuple[int, str]:
    """Upload a binary asset to a GitHub release. Returns (http_status, body).

    POSTs raw bytes to the uploads.github.com asset endpoint for *release_id*.
    Transient responses (network failure or HTTP 5xx) are retried up to 3
    attempts with backoff, mirroring :func:`apply_call`. A 4xx is returned to
    the caller as-is so it fails loud rather than retrying pointlessly.
    """
    # Resolve the sleeper at call time so tests can neutralise the backoff (#985).
    sleeper = sleeper if sleeper is not None else time.sleep
    url = f"{_UPLOADS_ROOT}/repos/{repo}/releases/{release_id}/assets?name={urllib.parse.quote(name)}"
    last_code = 0
    last_body = ""

    for attempt in range(1, 4):
        # S310 justification: the URL is built from the fixed
        # https://uploads.github.com endpoint plus repo/path segments from
        # trusted env vars; opener is injectable for tests but defaults to the
        # bounded urlopen on the fixed host.
        request = urllib.request.Request(url, data=content, method="POST")  # noqa: S310 -- fixed https://uploads.github.com endpoint
        request.add_header("Authorization", f"Bearer {token}")
        request.add_header("Accept", "application/vnd.github+json")
        request.add_header("X-GitHub-Api-Version", API_VERSION)
        request.add_header("Content-Type", content_type)

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
        print(f"Attempt {attempt}: HTTP {_format_code(last_code)} for POST {url}")
        if last_code != 0 and last_code < 500:
            break
        if attempt < 3:
            sleeper(attempt * 5)

    return last_code, last_body


# GitHub's GraphQL endpoint, like the REST one, returns transient HTTP 5xx and
# network failures; it ALSO returns a generic "Something went wrong while
# executing your query ... Please include <id> when reporting this issue" entry
# in the response ``errors`` array; its internal-error / timeout signature --
# usually with HTTP 200. A manual decision-tree run reproduced this on
# createCommitOnBranch even for a single small batch (Refs #1580), and the same
# generic error also appears when a mutation races a just-recreated branch ref.
# apply_call already retries the 5xx/network class; graphql_call must mirror that
# and additionally catch this GraphQL-only signature so one transient blip does
# not fail the whole generated-docs publish. A retried createCommitOnBranch is
# safe because expectedHeadOid rejects a stale oid rather than duplicating a
# commit that actually landed.
_GRAPHQL_TRANSIENT_ERROR_MARKER = "something went wrong while executing your query"


def _graphql_is_transient(code: int, body: dict[str, Any]) -> bool:
    """Return True when a GraphQL response should be retried.

    Transient: a network failure (``code == 0``), an HTTP 5xx, or a body whose
    ``errors`` array carries GitHub's generic "Something went wrong while
    executing your query" entry (its internal-error/timeout signature, usually
    delivered with HTTP 200). A permanent client error; a validation failure or
    a malformed query; is not transient and is returned to the caller as-is so
    it fails loud rather than retrying pointlessly.
    """
    if code == 0 or code >= 500:
        return True
    errors = body.get("errors")
    if isinstance(errors, list):
        for err in errors:
            message = err.get("message", "") if isinstance(err, dict) else ""
            if isinstance(message, str) and _GRAPHQL_TRANSIENT_ERROR_MARKER in message.lower():
                return True
    return False


def graphql_call(
    *,
    query: str,
    variables: dict[str, Any],
    token: str,
    opener: Callable[[urllib.request.Request], Any] = _default_opener,
    sleeper: Callable[[float], None] | None = None,
) -> tuple[int, dict[str, Any]]:
    """Execute a GitHub GraphQL query/mutation. Returns (http_status, response_dict).

    Transient responses (HTTP 5xx, network failure, or GitHub's generic
    "Something went wrong" error signature) are retried up to 3 attempts with
    backoff, mirroring :func:`apply_call`. A network-level failure that never
    clears still degrades to ``(0, {})`` rather than raising (CWE-703).
    """
    # Resolve the sleeper at call time (not as a captured default) so tests can
    # neutralise the real retry backoff by injecting a no-op sleeper (#985).
    sleeper = sleeper if sleeper is not None else time.sleep
    payload = json.dumps({"query": query, "variables": variables}, separators=(",", ":"))
    last_code = 0
    last_body: dict[str, Any] = {}

    for attempt in range(1, 4):
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
        except urllib.error.URLError:
            # Network-level failure (DNS, connection reset, timeout). Mirror
            # apply_call's curl-level 000 so a transient outage degrades to an
            # empty result instead of an unhandled traceback (CWE-703).
            code = 0
            body_str = ""
        try:
            parsed = json.loads(body_str) if body_str else {}
        except json.JSONDecodeError:
            parsed = {}
        last_code = code
        last_body = parsed if isinstance(parsed, dict) else {}

        if not _graphql_is_transient(last_code, last_body):
            break
        print(f"Attempt {attempt}: transient GraphQL response HTTP {_format_code(last_code)} for POST /graphql")
        if attempt < 3:
            sleeper(attempt * 5)

    return last_code, last_body


def _format_code(code: int) -> str:
    return "000" if code == 0 else str(code)
