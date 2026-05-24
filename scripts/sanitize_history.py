#!/usr/bin/env python3
"""Apply translations.json to live issues/PRs/comments under #102 Layer 1.

Operator-run companion to ``scripts/backup_non_ascii.py`` (P1) and
``scripts/translations.json`` (P3). For each mapping item:

1. GET the live body/title.
2. If ``sha256(live) == sha256(mapping.original)``, PATCH to
   ``mapping.translated``.
3. If ``sha256(live) == sha256(mapping.translated)``, skip (already
   applied, idempotent).
4. Otherwise emit ``::error::Drift detected ...`` and abort -- the live
   body diverged from both the mapping's source and target, so
   overwriting it would silently destroy work.

``--exclude-pr`` lets the operator skip items targeting specific PR
numbers; the umbrella's three rollout PRs (#102 P1/P3/P5) pass their
own numbers here so a self-mutation cannot rewrite the operator's
in-flight review thread.

The docs originally specified a bash + jq + ``gh api`` script. This is
Python instead so it can reuse :func:`_github_api.apply_call`'s retry
and surrogate-safe decode rather than re-implement them, and so the
drift/idempotency logic is unit-tested instead of inspected by eye.

Refs #102.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

from _github_api import apply_call

API_ROOT = "https://api.github.com"


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_translations(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_backup(path: str | Path) -> dict[str, Any]:
    raw = Path(path).read_bytes()
    if path and str(path).endswith(".gz"):
        raw = gzip.decompress(raw)
    return json.loads(raw.decode("utf-8"))


def index_backup(backup: dict[str, Any]) -> dict[tuple[str, int, int | None, str], str]:
    """Return ``{(type, id, comment_id, field): original_value}``.

    ``field`` is ``"title"`` or ``"body"``; comment kinds only carry
    ``"body"`` so their ``"title"`` entries are intentionally absent.
    """
    out: dict[tuple[str, int, int | None, str], str] = {}
    for item in backup.get("items") or []:
        kind = item.get("type")
        id_ = item.get("id")
        comment_id = item.get("comment_id")
        if id_ is None or kind is None:
            continue
        body = item.get("body") or ""
        out[(kind, id_, comment_id, "body")] = body
        title = item.get("title") or ""
        if title:
            out[(kind, id_, comment_id, "title")] = title
    return out


def item_endpoint(repo: str, item: dict[str, Any]) -> str:
    """Return the API URL for the GET/PATCH of *item*'s field-bearing object."""
    kind = item["type"]
    if kind == "issue":
        return f"{API_ROOT}/repos/{repo}/issues/{item['number']}"
    if kind == "pr":
        return f"{API_ROOT}/repos/{repo}/pulls/{item['number']}"
    if kind == "issue_comment":
        if item.get("comment_id") is None:
            raise ValueError(
                f"issue_comment item id={item.get('id')} missing comment_id"
            )
        return f"{API_ROOT}/repos/{repo}/issues/comments/{item['comment_id']}"
    if kind == "pr_review_comment":
        if item.get("comment_id") is None:
            raise ValueError(
                f"pr_review_comment item id={item.get('id')} missing comment_id"
            )
        return f"{API_ROOT}/repos/{repo}/pulls/comments/{item['comment_id']}"
    raise ValueError(f"unsupported item type: {kind!r}")


def is_excluded(item: dict[str, Any], excluded_prs: set[int]) -> bool:
    """True if *item* targets a PR number in *excluded_prs*."""
    if not excluded_prs:
        return False
    if item["type"] not in {"pr", "pr_review_comment"}:
        return False
    number = item.get("number")
    return number in excluded_prs


def classify_drift(*, live: str, original: str, translated: str) -> str:
    """Return ``"patch"`` / ``"skip"`` / ``"drift"``.

    - ``patch``: live matches the mapping's ``original`` -> safe to apply.
    - ``skip``:  live already matches ``translated`` -> idempotent noop.
    - ``drift``: live matches neither -> abort.
    """
    live_h = sha256_hex(live)
    if live_h == sha256_hex(original):
        return "patch"
    if live_h == sha256_hex(translated):
        return "skip"
    return "drift"


def parse_exclude_prs(raw: str | None) -> set[int]:
    if not raw:
        return set()
    out: set[int] = set()
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        out.add(int(chunk))
    return out


# ---------------------------------------------------------------------------
# Network-touching helpers (opener/sleeper injected for tests)
# ---------------------------------------------------------------------------


def fetch_live_field(
    *,
    url: str,
    field: str,
    token: str,
    opener: Callable[[urllib.request.Request], Any] = urllib.request.urlopen,
    sleeper: Callable[[float], None] | None = None,
) -> str:
    """GET *url* via :func:`apply_call`; return the requested field as a string.

    *field* is ``"title"`` or ``"body"`` -- the two columns this script
    rewrites. Coerces missing/null to empty string so drift comparison is
    over deterministic strings.
    """
    kwargs: dict[str, Any] = {
        "method": "GET",
        "url": url,
        "payload": None,
        "token": token,
        "opener": opener,
    }
    if sleeper is not None:
        kwargs["sleeper"] = sleeper
    code, body = apply_call(**kwargs)
    if not (200 <= code < 300):
        raise RuntimeError(f"GET {url} returned HTTP {code}: {body!r}")
    parsed = json.loads(body)
    return parsed.get(field) or ""


def patch_field(
    *,
    url: str,
    field: str,
    new_value: str,
    token: str,
    opener: Callable[[urllib.request.Request], Any] = urllib.request.urlopen,
    sleeper: Callable[[float], None] | None = None,
) -> None:
    kwargs: dict[str, Any] = {
        "method": "PATCH",
        "url": url,
        "payload": {field: new_value},
        "token": token,
        "opener": opener,
    }
    if sleeper is not None:
        kwargs["sleeper"] = sleeper
    code, body = apply_call(**kwargs)
    if not (200 <= code < 300):
        raise RuntimeError(f"PATCH {url} returned HTTP {code}: {body!r}")


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def iter_actionable(
    translations: dict[str, Any],
    excluded_prs: set[int],
) -> list[dict[str, Any]]:
    items = translations.get("items") or []
    return [it for it in items if not is_excluded(it, excluded_prs)]


def run_apply(
    *,
    translations: dict[str, Any],
    repo: str,
    token: str,
    dry_run: bool,
    batch_size: int,
    excluded_prs: set[int],
    opener: Callable[[urllib.request.Request], Any] = urllib.request.urlopen,
    sleeper: Callable[[float], None] | None = None,
) -> dict[str, int]:
    """Apply the mapping. Returns ``{patched, skipped, excluded}`` counts.

    Aborts loudly on the first drift detection so the operator can
    investigate before any further mutation lands.
    """
    counts = {"patched": 0, "skipped": 0, "excluded": 0, "examined": 0}
    items = translations.get("items") or []
    actionable: list[dict[str, Any]] = []
    for item in items:
        if is_excluded(item, excluded_prs):
            counts["excluded"] += 1
            continue
        actionable.append(item)

    for index, item in enumerate(actionable):
        if batch_size and index and index % batch_size == 0:
            print(f"--- batch boundary at {index}/{len(actionable)} ---")
        counts["examined"] += 1
        url = item_endpoint(repo, item)
        field = item["field"]
        live = fetch_live_field(
            url=url, field=field, token=token, opener=opener, sleeper=sleeper
        )
        verdict = classify_drift(
            live=live,
            original=item["original"],
            translated=item["translated"],
        )
        if verdict == "drift":
            msg = (
                f"::error::Drift detected on {item['type']}#{item.get('number')}"
                f"({field}); live SHA does not match mapping.original nor "
                "mapping.translated. Aborting."
            )
            print(msg, file=sys.stderr)
            raise SystemExit(1)
        if verdict == "skip":
            counts["skipped"] += 1
            print(f"skip {item['type']}#{item.get('number')}({field}) -- already applied")
            continue
        # verdict == "patch"
        if dry_run:
            print(f"plan PATCH {url} field={field}")
        else:
            patch_field(
                url=url,
                field=field,
                new_value=item["translated"],
                token=token,
                opener=opener,
                sleeper=sleeper,
            )
            print(f"patched {item['type']}#{item.get('number')}({field})")
        counts["patched"] += 1
    return counts


def run_plan(
    *,
    translations: dict[str, Any],
    excluded_prs: set[int],
) -> list[dict[str, Any]]:
    """Return the apply plan as a list of intent dicts (no API calls)."""
    plan: list[dict[str, Any]] = []
    for item in iter_actionable(translations, excluded_prs):
        plan.append({
            "type": item["type"],
            "number": item.get("number"),
            "field": item["field"],
            "original_sha256": sha256_hex(item["original"]),
            "translated_sha256": sha256_hex(item["translated"]),
        })
    return plan


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def cmd_plan(args: argparse.Namespace) -> int:
    translations = load_translations(args.input)
    excluded = parse_exclude_prs(args.exclude_pr)
    plan = run_plan(translations=translations, excluded_prs=excluded)
    print(json.dumps({"count": len(plan), "items": plan}, indent=2))
    return 0


def cmd_apply(args: argparse.Namespace) -> int:
    repo = os.environ.get("REPO")
    if not repo:
        print("::error::REPO env var is required", file=sys.stderr)
        return 2
    token = os.environ.get("GH_TOKEN")
    if not token:
        print("::error::GH_TOKEN env var is required", file=sys.stderr)
        return 2

    translations = load_translations(args.input)
    excluded = parse_exclude_prs(args.exclude_pr)
    counts = run_apply(
        translations=translations,
        repo=repo,
        token=token,
        dry_run=args.dry_run,
        batch_size=args.batch_size,
        excluded_prs=excluded,
    )
    print(json.dumps(counts, indent=2))
    return 0


def cmd_restore(args: argparse.Namespace) -> int:
    """Reverse a previous apply by pushing the backup's originals back."""
    repo = os.environ.get("REPO")
    if not repo:
        print("::error::REPO env var is required", file=sys.stderr)
        return 2
    token = os.environ.get("GH_TOKEN")
    if not token:
        print("::error::GH_TOKEN env var is required", file=sys.stderr)
        return 2

    backup = load_backup(args.backup)
    index = index_backup(backup)
    patched = 0
    for (kind, id_, comment_id, field), original in index.items():
        item = {
            "type": kind,
            "id": id_,
            "comment_id": comment_id,
            # Restore uses the same endpoint shape; number must come from backup.
            "number": _number_for_restore(backup, kind, id_),
        }
        try:
            url = item_endpoint(repo, item)
        except ValueError:
            continue
        if args.dry_run:
            print(f"plan PATCH {url} field={field}")
        else:
            patch_field(
                url=url,
                field=field,
                new_value=original,
                token=token,
            )
            print(f"restored {kind}#{item['number']}({field})")
        patched += 1
    print(json.dumps({"restored": patched}, indent=2))
    return 0


def _number_for_restore(backup: dict[str, Any], kind: str, id_: int) -> int | None:
    for item in backup.get("items") or []:
        if item.get("type") == kind and item.get("id") == id_:
            return item.get("number")
    return None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sanitize_history",
        description="Apply translations.json to live issues/PRs/comments (#102).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_plan = sub.add_parser("plan", help="Print the apply plan without contacting the API.")
    p_plan.add_argument("--in", dest="input", required=True)
    p_plan.add_argument("--exclude-pr", default="", help="Comma-separated PR numbers to skip.")

    p_apply = sub.add_parser("apply", help="GET each live field, drift-check, PATCH safe items.")
    p_apply.add_argument("--in", dest="input", required=True)
    p_apply.add_argument("--batch-size", type=int, default=10)
    p_apply.add_argument("--dry-run", action="store_true")
    p_apply.add_argument("--exclude-pr", default="")

    p_restore = sub.add_parser("restore", help="Push the backup's originals back over current state.")
    p_restore.add_argument("--backup", required=True)
    p_restore.add_argument("--dry-run", action="store_true")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "plan":
        return cmd_plan(args)
    if args.command == "apply":
        return cmd_apply(args)
    if args.command == "restore":
        return cmd_restore(args)
    parser.error(f"unknown command: {args.command!r}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
