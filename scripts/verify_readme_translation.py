#!/usr/bin/env python3
"""Deterministic gate: README.md edits land alongside translations.

Issue #476: README.md, README.ja.md and README.zh.md drifted apart five
PRs in a row (no workflow asserts the trio moves together). This script
makes the parity contract deterministic.

Contract:

* Read the changed-file list as ``git diff --name-only {base}..HEAD``.
* If ``README.md`` is in that set, ``README.ja.md`` and ``README.zh.md``
  must also be in it; unless the PR body carries the literal opt-out
  marker ``<!-- readme-translation-ack -->`` (case-insensitive, optional
  surrounding whitespace inside the comment).
* Read the PR body from ``--body-file`` when supplied, otherwise from
  ``PR_BODY``.

Architecture: pure functions on top, one thin :func:`_run` subprocess
boundary at the bottom that tests monkeypatch via the ``runner`` kwarg.

Wiring:

* CI: a step inside the ``gate`` job of
  ``.github/workflows/portable-pr-policy.yml``. The job's existing
  required-status-check context (``Portable PR policy / gate``,
  pinned in ``.github/rulesets/main.json``) covers this step too --
  no ruleset change needed. The job already checks out with
  ``fetch-depth: 0``, so the diff range is reachable without an extra
  checkout step.

Failure policy: gate per CLAUDE.md section 4; exits 1 with
``::error::`` annotations when drift is detected or git invocation
fails. Empty input (no README touched, or PR body without marker) is
the happy path, not a skip.

Tested by ``tests/test_verify_readme_translation.py``. Refs #476.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

_GIT_TIMEOUT_SECONDS: int = 15

README_PATHS: frozenset[str] = frozenset(
    {"README.md", "README.ja.md", "README.zh.md"}
)

# The marker is itself an HTML comment so it survives MD renderers
# without being visible. Matching is case-insensitive and tolerates
# inner whitespace so `<!--readme-translation-ack-->`,
# `<!-- readme-translation-ack -->`, and
# `<!--  Readme-Translation-ACK  -->` all qualify.
_SKIP_MARKER_RE = re.compile(
    r"<!--\s*readme-translation-ack\s*-->", re.IGNORECASE
)


def resolve_base() -> str:
    """Return the base ref the gate compares HEAD against.

    Resolution order:

    1. ``BASE_REF`` (explicit override the workflow / CLI passes).
    2. ``GITHUB_BASE_REF`` (set by GitHub Actions on ``pull_request``
       events; bare branch name like ``main``, so we prefix
       ``origin/``).
    3. Hard-coded fallback ``origin/main`` for local invocations.

    Empty environment values are treated as unset so ``GITHUB_BASE_REF=""``
    on push events does not silently win.
    """
    explicit = os.environ.get("BASE_REF")
    if explicit:
        return explicit
    actions_base = os.environ.get("GITHUB_BASE_REF")
    if actions_base:
        return f"origin/{actions_base}"
    return "origin/main"


def changed_readmes(
    base_ref: str, head: str = "HEAD", *, runner=subprocess.run
) -> frozenset[str]:
    """Return the subset of :data:`README_PATHS` modified in ``{base}..{head}``.

    Uses ``git diff --name-only`` so renames and deletes also surface.
    The returned set is the intersection with the README allowlist, so
    unrelated changes do not affect the gate.
    """
    result = _run(
        ["git", "diff", "--name-only", f"{base_ref}..{head}"], runner=runner
    )
    touched = {
        line.strip()
        for line in result.stdout.splitlines()
        if line.strip()
    }
    return frozenset(touched & README_PATHS)


def body_has_skip_marker(raw_body: str | None) -> bool:
    """Return True if *raw_body* contains the opt-out marker.

    Checked against the raw body (no HTML-comment stripping) because the
    marker itself is an HTML comment that would otherwise be removed.
    This mirrors :func:`issue_link.body_has_partial_marker` (#216).
    """
    if not raw_body:
        return False
    return _SKIP_MARKER_RE.search(raw_body) is not None


def evaluate_drift(
    changed: frozenset[str], skip: bool
) -> tuple[int, list[str]]:
    """Return ``(exit_code, error_lines)`` for the gate decision.

    Rules:

    * ``README.md`` changed AND both translations missing AND no skip
      marker -> exit 1 with a single ``::error::`` line listing the
      missing translations.
    * Anything else (no README touched, all three touched, translations
      only, or skip marker present) -> exit 0.

    Note: a PR that touches only ``README.ja.md`` is allowed; the
    contract guards the English-only-edit failure mode, not the inverse.
    Reviewers catch translation-only churn through normal review.
    """
    if "README.md" not in changed:
        return 0, []
    missing = sorted({"README.ja.md", "README.zh.md"} - changed)
    if not missing:
        return 0, []
    if skip:
        return 0, []
    pretty = ", ".join(missing)
    return 1, [
        "::error::README.md was modified without matching updates to "
        f"{pretty}. Either edit the missing translation(s) in the same "
        "PR, or add the literal marker '<!-- readme-translation-ack -->' "
        "to the PR body with a rationale. See "
        "docs/runbooks/readme-translation-drift.md and Issue #476."
    ]


def _resolve_body(args: argparse.Namespace) -> str:
    if args.body_file is not None:
        return Path(args.body_file).read_text(encoding="utf-8")
    return os.environ.get("PR_BODY", "")


def _resolve_base_ref(args: argparse.Namespace) -> str:
    if args.base_ref:
        return args.base_ref
    return resolve_base()


def _cmd_verify(args: argparse.Namespace) -> int:
    base = _resolve_base_ref(args)
    try:
        body = _resolve_body(args)
    except FileNotFoundError as exc:
        print(
            f"::error::verify_readme_translation: body file not found: {exc}",
            file=sys.stderr,
        )
        return 1
    try:
        changed = changed_readmes(base)
    except (
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
        FileNotFoundError,
    ) as exc:
        print(
            "::error::verify_readme_translation: git invocation failed "
            f"against base {base!r}: {exc}",
            file=sys.stderr,
        )
        return 1

    skip = body_has_skip_marker(body)
    code, errors = evaluate_drift(changed, skip)
    if code == 0:
        if "README.md" in changed and skip:
            print(
                "OK: README.md changed; opt-out marker present "
                "('<!-- readme-translation-ack -->')."
            )
        elif "README.md" in changed:
            print(
                "OK: README.md changed along with README.ja.md and "
                "README.zh.md."
            )
        elif changed:
            pretty = ", ".join(sorted(changed))
            print(
                f"OK: translation-only change ({pretty}); README.md "
                "untouched."
            )
        else:
            print("OK: no README files modified.")
        return 0
    for line in errors:
        print(line, file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_verify = sub.add_parser(
        "verify",
        help="Verify README translations move together with README.md.",
    )
    p_verify.add_argument(
        "--base-ref",
        help=(
            "Base ref to diff HEAD against. Falls back to BASE_REF, then "
            "to origin/$GITHUB_BASE_REF, then to origin/main."
        ),
    )
    p_verify.add_argument(
        "--body-file",
        help=(
            "Path to a file containing the PR body. Falls back to the "
            "PR_BODY env var when omitted."
        ),
    )
    p_verify.set_defaults(func=_cmd_verify)

    args = parser.parse_args(argv)
    return args.func(args)


def _run(cmd: list[str], *, runner=subprocess.run):
    """Thin subprocess boundary; the only impure surface in this module.

    ``check=True`` raises ``CalledProcessError`` on non-zero exit; the
    caller in :func:`_cmd_verify` translates that into the fail-loud
    ``::error::`` path. Tests monkeypatch ``runner`` to inject fake
    completed-process objects.
    """
    return runner(
        cmd,
        capture_output=True,
        text=True,
        timeout=_GIT_TIMEOUT_SECONDS,
        check=True,
    )


if __name__ == "__main__":
    raise SystemExit(main())
