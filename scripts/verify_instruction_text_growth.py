#!/usr/bin/env python3
"""Deterministic gate: net-positive instruction-text PRs declare a reason.

Issue #1670 (designed in the #1669 retrospective): the universal
instruction text grows monotonically with every clarification, with no
harness backstop. CLAUDE.md section 5 already requires that "a net
increase earns an explicit justification before the commit, not after",
but that rule is agent-remembered, not gated. PR #1664 grew +153 chars
before being trimmed to +62 by hand; a gate would have surfaced the
growth automatically.

The rule:

* Scope of measurement is a PR's diff to ``.apm/instructions/**`` only.
  ``CLAUDE.md`` / ``AGENTS.md`` are generated mirrors of that source, so
  counting them would double-count the same edit.
* Compute the net character delta (added chars minus removed chars)
  across the changed instruction-source files for ``{base}..HEAD`` by
  parsing a ``git diff --unified=0`` over the ``.apm/instructions/``
  pathspec.
* net delta <= 0 -> pass (a trim or neutral edit needs no justification).
* net delta > 0 -> the PR body must carry a plain-text
  ``text-growth-ack: <reason>`` line. Plain text, not an HTML comment,
  mirroring ``scan_design_philosophy_drift``'s ``philosophy-matrix-ack``
  (the GitHub MCP write tools strip HTML comments). A missing or
  malformed ack fails the gate with an ``::error::`` annotation naming
  the marker and the measured delta.
* Bodies created strictly before ``--cutoff`` are skipped so the
  back-catalog is not retro-failed (mirrors ``scripts/body_policy.py``
  and ``scripts/verify_text_delta_section.py``).

It does not forbid growth; some clarifications legitimately grow. It
forces the justification to be recorded, which is exactly what section 5
already requires. The ack matches per-PR, not per-commit, so a
multi-commit PR declares growth once.

Architecture: pure functions on top, one thin :func:`_run` subprocess
boundary at the bottom that tests monkeypatch via the ``runner`` kwarg.
The character accounting is a pure function on the diff text so its
arithmetic is unit-tested without a git repository.

Wiring: a step inside the ``portable-pr-policy`` job (named "Portable PR
policy / gate") of ``.github/workflows/verify-pr.yml``. That job's
required status-check context (``Portable PR policy / gate``, pinned in
``.github/rulesets/main.json``) covers this step too, and the job
already checks out with ``fetch-depth: 0`` so the diff range is
reachable. A mirrored step in ``scripts/preflight_all.py`` runs it
pre-push with ``PR_BODY`` unset (the stricter default).

Contract:
    Inputs: the ``verify`` subcommand; ``--base-ref`` (falls back to
        ``BASE_REF``, then ``origin/$GITHUB_BASE_REF``, then
        ``origin/main``); the PR body from ``--body-file`` or the
        ``PR_BODY`` env var; ``--created-at`` (falls back to
        ``PR_CREATED_AT``) and ``--cutoff`` (falls back to
        ``BODY_POLICY_CUTOFF``) for the back-catalog skip. No stdin.
    Outputs: an ``::error::`` annotation on stdout naming the marker and
        the measured delta when the gate fails; an ``OK:`` line on the
        happy path; exit 0 when net delta <= 0, the ack is present, or
        the PR is skipped, exit 1 otherwise.
    Failure policy: fails loud per CLAUDE.md section 4 (gate: a
        net-positive instruction-text PR without a ``text-growth-ack:``
        line exits non-zero; an unreachable diff range exits non-zero
        rather than passing silently).

Tested by ``tests/test_verify_instruction_text_growth.py``. Refs #1670,
#1669.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

from body_policy import is_within_gate_window

_GIT_TIMEOUT_SECONDS: int = 15

# The directory prefix every universal instruction-text *source* file
# lives under. The compiled mirrors (CLAUDE.md, AGENTS.md) are excluded
# on purpose: they are generated from this source, so counting them too
# would double-count the same edit.
_INSTRUCTION_DIR_PREFIX = ".apm/instructions/"

# Plain-text opt-out marker (MCP-safe, mirrors the ``philosophy-matrix-ack``
# pattern in scripts/scan_design_philosophy_drift.py): a line that, after
# optional indentation, begins with ``text-growth-ack:`` (case-insensitive)
# and carries a non-whitespace reason after the colon. HTML-comment markers
# are stripped by the GitHub MCP write tools, so a plain-text token is used.
# Requiring a reason means a bare ``text-growth-ack:`` is malformed and
# fails, matching the "missing/malformed ack -> fail" contract.
_ACK_RE = re.compile(
    r"^\s*text-growth-ack:\s*\S", re.IGNORECASE | re.MULTILINE
)


def resolve_base() -> str:
    """Return the base ref the gate compares HEAD against.

    Resolution order: ``BASE_REF`` env, then ``origin/$GITHUB_BASE_REF``
    (the bare branch name GitHub Actions sets on ``pull_request``
    events), then the local fallback ``origin/main``. Empty environment
    values are treated as unset. Mirrors
    ``verify_text_delta_section.resolve_base`` so the two instruction-text
    gates resolve their base identically.
    """
    explicit = os.environ.get("BASE_REF")
    if explicit:
        return explicit
    actions_base = os.environ.get("GITHUB_BASE_REF")
    if actions_base:
        return f"origin/{actions_base}"
    return "origin/main"


def net_char_delta(diff_text: str) -> int:
    """Return added chars minus removed chars in a unified diff.

    Counts the content characters (excluding the leading ``+`` / ``-``
    diff marker) of each added and removed line, then returns
    ``added - removed``. File headers (``+++``/``---``), hunk headers
    (``@@``), and the ``\\ No newline at end of file`` marker are not
    content and are skipped. A modified line shows under ``--unified=0``
    as one removed plus one added line, so an expanded bullet yields the
    positive net the gate is built to surface.

    The function is pure; it never touches git; so the character
    arithmetic is unit-tested directly on diff fixtures.
    """
    added = 0
    removed = 0
    for line in diff_text.splitlines():
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+"):
            added += len(line) - 1
        elif line.startswith("-"):
            removed += len(line) - 1
    return added - removed


def has_growth_ack(body: str) -> bool:
    """Return True when *body* carries the text-growth-ack opt-out line."""
    return _ACK_RE.search(body) is not None


def evaluate(net_delta: int, body: str) -> tuple[int, list[str]]:
    """Return ``(exit_code, error_lines)`` for the gate decision.

    * net delta <= 0 -> exit 0 (trim/neutral edit needs no justification).
    * net delta > 0 with a ``text-growth-ack:`` line -> exit 0.
    * net delta > 0 without the ack -> exit 1.
    """
    if net_delta <= 0:
        return 0, []
    if has_growth_ack(body):
        return 0, []
    return 1, [
        f"::error::This PR's net change to .apm/instructions/** is "
        f"+{net_delta} chars (added minus removed). CLAUDE.md section 5 "
        "requires a net increase to earn an explicit justification before "
        "the commit. Add a plain-text 'text-growth-ack: <reason>' line to "
        "the PR body recording why the growth is warranted, or trim the "
        "edit so the net delta is <= 0."
    ]


def instruction_diff(
    base_ref: str, head: str = "HEAD", *, runner=subprocess.run
) -> str:
    """Return the ``--unified=0`` diff of ``.apm/instructions/**``.

    The ``.apm/instructions/`` pathspec restricts the diff to the
    instruction source so the character accounting never sees unrelated
    files. ``--unified=0`` drops context lines so only genuine additions
    and removals are counted. ``--no-color`` keeps the output free of ANSI
    escapes that would corrupt the per-line marker check.
    """
    result = _run(
        [
            "git",
            "diff",
            "--no-color",
            "--unified=0",
            f"{base_ref}..{head}",
            "--",
            _INSTRUCTION_DIR_PREFIX,
        ],
        runner=runner,
    )
    return result.stdout


def _resolve_body(args: argparse.Namespace) -> str:
    if args.body_file is not None:
        return Path(args.body_file).read_text(encoding="utf-8")
    return os.environ.get("PR_BODY", "")


def _resolve_base_ref(args: argparse.Namespace) -> str:
    if args.base_ref:
        return args.base_ref
    return resolve_base()


def _resolve_created_at(args: argparse.Namespace) -> str:
    if args.created_at is not None:
        return args.created_at
    return os.environ.get("PR_CREATED_AT", "")


def _resolve_cutoff(args: argparse.Namespace) -> str:
    if args.cutoff is not None:
        return args.cutoff
    return os.environ.get("BODY_POLICY_CUTOFF", "")


def _cmd_verify(args: argparse.Namespace) -> int:
    created_at = _resolve_created_at(args)
    cutoff = _resolve_cutoff(args)
    if created_at and cutoff and not is_within_gate_window(created_at, cutoff):
        print(
            f"skipped: PR created at {created_at} predates gate cutoff "
            f"{cutoff}."
        )
        return 0

    base = _resolve_base_ref(args)
    try:
        body = _resolve_body(args)
    except FileNotFoundError as exc:
        print(
            "::error::verify_instruction_text_growth: body file not found: "
            f"{exc}",
            file=sys.stderr,
        )
        return 1
    try:
        diff_text = instruction_diff(base)
    except (
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
        FileNotFoundError,
        RuntimeError,
    ) as exc:
        print(
            "::error::verify_instruction_text_growth: git invocation failed "
            f"against base {base!r}: {exc}",
            file=sys.stderr,
        )
        return 1

    delta = net_char_delta(diff_text)
    code, errors = evaluate(delta, body)
    if code == 0:
        if delta > 0:
            print(
                f"OK: instruction text grew +{delta} chars and the PR body "
                "carries a 'text-growth-ack:' justification."
            )
        else:
            print(
                f"OK: net instruction-text delta is {delta} chars "
                "(<= 0); no justification required."
            )
        return 0
    for line in errors:
        print(line)
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_verify = sub.add_parser(
        "verify",
        help=(
            "Fail when a PR's net char growth on .apm/instructions/** is "
            "positive and the body lacks a 'text-growth-ack:' line."
        ),
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
    p_verify.add_argument(
        "--created-at",
        help=(
            "ISO-8601 creation timestamp of the PR. Compared against "
            "--cutoff to keep the back-catalog exempt. Falls back to "
            "PR_CREATED_AT when omitted."
        ),
    )
    p_verify.add_argument(
        "--cutoff",
        help=(
            "ISO-8601 cutoff. PRs created strictly before this moment are "
            "skipped. Falls back to BODY_POLICY_CUTOFF when omitted."
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
