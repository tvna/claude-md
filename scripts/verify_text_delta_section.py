#!/usr/bin/env python3
"""Deterministic gate: instruction-text PRs declare their character delta.

Issue #1178: line count and character count can disagree. A consolidation
can drop a bullet (-1 line) while the source character count rises (+20),
so a line-only framing misleads a reviewer. When a PR changes the
universal instruction text, its body must make the character-level change
and the added/removed context visible by inspection (CLAUDE.md section 6),
harness-enforced rather than agent-remembered (section 3).

The rule:

* Read the changed-file list as ``git diff --name-only {base}..HEAD``.
* A file is "universal instruction text" when it is ``CLAUDE.md`` or
  ``AGENTS.md`` or lives under ``.apm/instructions/``.
* If none of those files changed, pass (the section is not required).
* Otherwise the PR body must carry a ``## Text delta`` section that
  contains all three of: a signed character-count change (e.g.
  ``+20 chars`` or ``chars: -3``), an ``Added context`` label, and a
  ``Removed context`` label. A missing or malformed section fails the
  gate with an ``::error::`` annotation.
* Bodies created strictly before ``--cutoff`` are skipped so the
  back-catalog is not retro-failed (mirrors ``scripts/body_policy.py``).

Architecture: pure functions on top, one thin :func:`_run` subprocess
boundary at the bottom that tests monkeypatch via the ``runner`` kwarg.
The ``## Text delta`` slice reuses ``body_policy.extract_section_body`` so
section parsing stays single-sourced with the other body gates.

Wiring: a step inside the ``gate`` job of
``.github/workflows/portable-pr-policy.yml``. That job's required
status-check context (``Portable PR policy / gate``, pinned in
``.github/rulesets/main.json``) covers this step too, and the job
already checks out with ``fetch-depth: 0`` so the diff range is
reachable.

Contract:
    Inputs: the ``verify`` subcommand; ``--base-ref`` (falls back to
        ``BASE_REF``, then ``origin/$GITHUB_BASE_REF``, then
        ``origin/main``); the PR body from ``--body-file`` or the
        ``PR_BODY`` env var; ``--created-at`` (falls back to
        ``PR_CREATED_AT``) and ``--cutoff`` (falls back to
        ``BODY_POLICY_CUTOFF``) for the back-catalog skip. No stdin.
    Outputs: ``::error::`` annotations on stdout naming each missing
        part; an ``OK:`` line on the happy path; exit 0 when the section
        is well-formed, not required, or skipped, exit 1 otherwise.
    Failure policy: fails loud per CLAUDE.md section 4 (gate: an
        instruction-text PR without a well-formed ``## Text delta``
        section exits non-zero).

Tested by ``tests/test_verify_text_delta_section.py``. Refs #1178.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

from body_policy import extract_section_body, is_within_gate_window

_GIT_TIMEOUT_SECONDS: int = 15

_TEXT_DELTA_HEADING = "Text delta"

# Exact-match instruction files plus the directory prefix that all other
# universal instruction sources live under.
_INSTRUCTION_FILES: frozenset[str] = frozenset({"CLAUDE.md", "AGENTS.md"})
_INSTRUCTION_DIR_PREFIX = ".apm/instructions/"

# A signed character-count change. Accepts the common spellings authors
# reach for: "+20 chars", "-3 characters", "chars: +20", "char count = -5".
# Line-anchored character classes with no nested quantifiers (ReDoS-safe).
_CHAR_DELTA_RE = re.compile(
    r"[+-]\d[\d,]*\s*char|char(?:acter)?s?\s*(?:count)?\s*[:=]?\s*[+-]\d",
    re.IGNORECASE,
)
_ADDED_RE = re.compile(r"\badded context\b", re.IGNORECASE)
_REMOVED_RE = re.compile(r"\bremoved context\b", re.IGNORECASE)


def is_instruction_path(path: str) -> bool:
    """Return True when *path* is universal instruction text.

    The universal instruction set is ``CLAUDE.md``, ``AGENTS.md``, and
    every file under ``.apm/instructions/`` (the APM source the two
    compiled files are generated from).
    """
    cleaned = path.strip()
    if not cleaned:
        return False
    return cleaned in _INSTRUCTION_FILES or cleaned.startswith(
        _INSTRUCTION_DIR_PREFIX
    )


def resolve_base() -> str:
    """Return the base ref the gate compares HEAD against.

    Resolution order: ``BASE_REF`` env, then ``origin/$GITHUB_BASE_REF``
    (the bare branch name GitHub Actions sets on ``pull_request``
    events), then the local fallback ``origin/main``. Empty environment
    values are treated as unset.
    """
    explicit = os.environ.get("BASE_REF")
    if explicit:
        return explicit
    actions_base = os.environ.get("GITHUB_BASE_REF")
    if actions_base:
        return f"origin/{actions_base}"
    return "origin/main"


def changed_instruction_files(
    base_ref: str, head: str = "HEAD", *, runner=subprocess.run
) -> frozenset[str]:
    """Return the instruction files modified in ``{base}..{head}``.

    Uses ``git diff --name-only`` so renames and deletes also surface.
    The result is the subset of the diff that :func:`is_instruction_path`
    accepts, so unrelated changes do not trigger the gate.
    """
    result = _run(
        ["git", "diff", "--name-only", f"{base_ref}..{head}"], runner=runner
    )
    return frozenset(
        line.strip()
        for line in result.stdout.splitlines()
        if is_instruction_path(line)
    )


def section_errors(section: str) -> list[str]:
    """Return ``::error::`` lines for a present ``## Text delta`` section.

    The section must contain all three parts. Returns ``[]`` when every
    part is present.
    """
    errors: list[str] = []
    if _CHAR_DELTA_RE.search(section) is None:
        errors.append(
            "::error::Text delta section must state a signed character-count "
            "change, for example '+20 chars' or 'chars: -3'."
        )
    if _ADDED_RE.search(section) is None:
        errors.append(
            "::error::Text delta section must label the Added context "
            "(a line containing 'Added context')."
        )
    if _REMOVED_RE.search(section) is None:
        errors.append(
            "::error::Text delta section must label the Removed context "
            "(a line containing 'Removed context')."
        )
    return errors


def evaluate(changed: frozenset[str], body: str) -> tuple[int, list[str]]:
    """Return ``(exit_code, error_lines)`` for the gate decision.

    * No instruction file changed -> exit 0 (section not required).
    * Instruction file changed but no ``## Text delta`` section -> exit 1.
    * Section present but missing a required part -> exit 1.
    * Section present and well-formed -> exit 0.
    """
    if not changed:
        return 0, []
    section = extract_section_body(body, _TEXT_DELTA_HEADING)
    if not section.strip():
        return 1, [
            "::error::This PR changes universal instruction text "
            "(.apm/instructions/**, CLAUDE.md, or AGENTS.md) but the body "
            "has no '## Text delta' section. Add it with a signed "
            "character-count change, an 'Added context' part, and a "
            "'Removed context' part. See "
            "docs/standards/issue-pr-body-standard.md."
        ]
    errors = section_errors(section)
    if errors:
        return 1, errors
    return 0, []


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
            f"::error::verify_text_delta_section: body file not found: {exc}",
            file=sys.stderr,
        )
        return 1
    try:
        changed = changed_instruction_files(base)
    except (
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
        FileNotFoundError,
        RuntimeError,
    ) as exc:
        print(
            "::error::verify_text_delta_section: git invocation failed "
            f"against base {base!r}: {exc}",
            file=sys.stderr,
        )
        return 1

    code, errors = evaluate(changed, body)
    if code == 0:
        if changed:
            print(
                "OK: instruction text changed and the '## Text delta' "
                "section is well-formed."
            )
        else:
            print("OK: no universal instruction text modified.")
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
            "Verify a PR that changes instruction text declares its "
            "character delta in a '## Text delta' section."
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
