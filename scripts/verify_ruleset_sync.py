#!/usr/bin/env python3
"""PR-time gate: live `required_status_checks` must contain every context the base-ref SoT declares.

The workflow `.github/workflows/verify-ruleset-sync.yml` calls this module on
every pull request. It catches the lag window where `.github/rulesets/main.json`
(SoT) lists a required status check context that has not yet been pushed to the
live ruleset via the `Apply rulesets` workflow.

Scope (per #120): only the `required_status_checks` lag in the lagging-behind
direction. Full SoT-vs-live drift is owned by `scripts/ruleset_drift.py`
(`.github/workflows/ruleset-drift.yml`, #30 / #116).

Design notes:

- Reads the SoT from the PR base ref via `GET /repos/{repo}/contents/...?ref=`
  rather than the PR head, so a PR that introduces a new context does not
  self-fail (see #120 Q2 / Q4).
- Uses the same `RULESETS_PAT` secret as `ruleset-drift.yml`, bound as
  `GH_TOKEN_API` in the workflow env.
- Pure functions on top; HTTP boundary at the bottom, injectable for tests.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any, Callable

from _github_api import API_VERSION


API_ROOT = "https://api.github.com"
DEFAULT_DOCS_URL = (
    "https://github.com/tvna/claude-md/blob/main/docs/rulesets.md"
    "#pr-time-required-checks-sync-gate"
)


# ---------------------------------------------------------------------------
# Pure functions
# ---------------------------------------------------------------------------

def extract_required_contexts(ruleset: dict[str, Any]) -> set[str]:
    """Return the set of `context` values declared by the ruleset.

    Looks for the first rule whose ``type == "required_status_checks"`` and
    reads its ``parameters.required_status_checks[].context`` list. Returns an
    empty set when no such rule exists, when the rule has no `parameters`, or
    when the parameter list is empty.
    """
    for rule in ruleset.get("rules", []) or []:
        if rule.get("type") != "required_status_checks":
            continue
        params = rule.get("parameters") or {}
        checks = params.get("required_status_checks") or []
        return {check["context"] for check in checks if isinstance(check, dict) and "context" in check}
    return set()


def compute_missing(sot_contexts: set[str], live_contexts: set[str]) -> set[str]:
    """Return contexts declared in SoT but not yet applied to live.

    Only the lagging-behind direction (`sot - live`). The opposite direction
    (live has contexts not in SoT) is full ruleset drift and is owned by
    `ruleset-drift.yml`; this gate intentionally ignores it.
    """
    return sot_contexts - live_contexts


def decode_base64_content(api_response: dict[str, Any]) -> str:
    """Decode the ``content`` field of a contents-API response.

    GitHub's contents API returns the file body as base64 with newlines every
    60 chars. ``base64.b64decode`` tolerates the newlines.
    """
    encoding = api_response.get("encoding")
    if encoding != "base64":
        raise ValueError(f"unexpected encoding {encoding!r}; expected 'base64'")
    raw = api_response.get("content")
    if not isinstance(raw, str):
        raise ValueError("contents API response has no 'content' string")
    return base64.b64decode(raw).decode("utf-8")


def format_error_lines(missing: set[str], docs_url: str) -> list[str]:
    """Return `::error::` annotation lines for each missing context, sorted."""
    lines = [
        f"::error::Required status check context declared in base-ref SoT but missing from live ruleset: {context}"
        for context in sorted(missing)
    ]
    lines.append(
        "::error::Resolve by dispatching the 'Apply rulesets' workflow "
        f"(ruleset=main, dry_run=false). See {docs_url}."
    )
    return lines


# ---------------------------------------------------------------------------
# HTTP boundary (injectable for tests)
# ---------------------------------------------------------------------------

def _api_request(url: str, token: str) -> urllib.request.Request:
    request = urllib.request.Request(url)
    request.add_header("Authorization", f"Bearer {token}")
    request.add_header("Accept", "application/vnd.github+json")
    request.add_header("X-GitHub-Api-Version", API_VERSION)
    return request


def fetch_live_ruleset_by_name(
    repo: str,
    name: str,
    token: str,
    *,
    opener: Callable[[urllib.request.Request], Any] = urllib.request.urlopen,
) -> dict[str, Any]:
    """Look up the live ruleset by `name` and return its full body.

    Lists rulesets first (id-less), matches by name, then GETs the id-specific
    endpoint to include the `rules` array (the list endpoint omits it).
    Raises ``RuntimeError`` for no-match or multi-match (caller fails loud).
    """
    list_req = _api_request(f"{API_ROOT}/repos/{repo}/rulesets", token)
    with opener(list_req) as response:
        listing = json.loads(response.read().decode("utf-8"))
    matches = [r for r in listing if r.get("name") == name]
    if len(matches) > 1:
        raise RuntimeError(
            f"Multiple live rulesets named {name!r} ({len(matches)}). "
            "Refusing to guess; resolve manually via the GitHub UI."
        )
    if not matches:
        raise RuntimeError(
            f"No live ruleset named {name!r} exists. The SoT declares one — "
            "dispatch the 'Apply rulesets' workflow first."
        )
    ruleset_id = matches[0]["id"]
    detail_req = _api_request(f"{API_ROOT}/repos/{repo}/rulesets/{ruleset_id}", token)
    with opener(detail_req) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_base_ref_sot(
    repo: str,
    base_ref: str,
    sot_path: str,
    token: str,
    *,
    opener: Callable[[urllib.request.Request], Any] = urllib.request.urlopen,
) -> str:
    """Fetch the SoT JSON file from `base_ref` via the contents API.

    Avoids checking out base_ref locally. Returns the decoded UTF-8 text.
    """
    url = f"{API_ROOT}/repos/{repo}/contents/{sot_path}?ref={base_ref}"
    request = _api_request(url, token)
    with opener(request) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return decode_base64_content(payload)


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def verify(
    *,
    repo: str,
    base_ref: str,
    sot_path: str,
    ruleset_name: str,
    token: str,
    docs_url: str,
    out_stream,
    err_stream,
    live_fetcher: Callable[[str, str, str], dict[str, Any]] | None = None,
    sot_fetcher: Callable[[str, str, str, str], str] | None = None,
) -> int:
    """Return process exit code: 0 when symmetric, 1 when missing or on error."""
    live_fn = live_fetcher or (lambda r, n, t: fetch_live_ruleset_by_name(r, n, t))
    sot_fn = sot_fetcher or (lambda r, b, p, t: fetch_base_ref_sot(r, b, p, t))

    try:
        live = live_fn(repo, ruleset_name, token)
    except (RuntimeError, urllib.error.HTTPError, urllib.error.URLError) as exc:
        print(f"::error::Failed to fetch live ruleset: {exc}", file=err_stream)
        return 1

    try:
        sot_text = sot_fn(repo, base_ref, sot_path, token)
        sot = json.loads(sot_text)
    except (ValueError, urllib.error.HTTPError, urllib.error.URLError) as exc:
        print(
            f"::error::Failed to fetch base-ref SoT {sot_path!r} at {base_ref!r}: {exc}",
            file=err_stream,
        )
        return 1

    sot_contexts = extract_required_contexts(sot)
    live_contexts = extract_required_contexts(live)
    missing = compute_missing(sot_contexts, live_contexts)

    if not missing:
        print(
            f"OK: live ruleset {ruleset_name!r} contains all "
            f"{len(sot_contexts)} required_status_checks contexts declared "
            f"by base-ref {sot_path!r} (ref={base_ref}).",
            file=out_stream,
        )
        return 0

    for line in format_error_lines(missing, docs_url):
        print(line, file=err_stream)
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Verify that the live main-protection ruleset's required_status_checks "
            "contains every context the base-ref SoT declares."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_verify = subparsers.add_parser("verify", help="Run the PR-time sync check.")
    p_verify.add_argument("--repo", required=True, help="owner/name")
    p_verify.add_argument("--base-ref", required=True, help="PR base branch name")
    p_verify.add_argument(
        "--sot-path",
        default=".github/rulesets/main.json",
        help="Path within the repo to the SoT JSON file.",
    )
    p_verify.add_argument(
        "--ruleset-name",
        default="main-protection",
        help="Live ruleset name to look up.",
    )
    p_verify.add_argument(
        "--docs-url",
        default=DEFAULT_DOCS_URL,
        help="Runbook URL emitted in the resolution hint.",
    )

    args = parser.parse_args(argv)

    if args.command == "verify":
        token = os.environ.get("GH_TOKEN_API", "")
        if not token:
            print(
                "::error::GH_TOKEN_API env var (RULESETS_PAT) is not set. "
                "See docs/rulesets.md \"Required secret\".",
                file=sys.stderr,
            )
            return 1
        return verify(
            repo=args.repo,
            base_ref=args.base_ref,
            sot_path=args.sot_path,
            ruleset_name=args.ruleset_name,
            token=token,
            docs_url=args.docs_url,
            out_stream=sys.stdout,
            err_stream=sys.stderr,
        )

    return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
