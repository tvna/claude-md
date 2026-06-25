#!/usr/bin/env python3
"""Surface a non-functional commit signer before a commit lands unsigned.

Refs #1987 (PR #1985 retrospective, Fact 2). PR #1985's first commit (8d4919f)
landed UNSIGNED in a Claude Code on the Web session while ``commit.gpgsign`` was
``true``. Because force-push and branch deletion are both blocked by the branch
ruleset, the unsigned base commit could not be rewritten and the PR had to be
squash-merged to recover. The cost of a single silent unsigned commit on a
ruleset-protected branch is therefore high and effectively irreversible, which
is what makes a deterministic gate worth its weight here.

Primary-source finding (this is why the gate is a live test-sign, not a file
check). The retro hypothesised that the commit was unsigned *because* the
session key ``/home/claude/.ssh/commit_signing_key.pub`` was empty (0 bytes).
A live probe in the same environment showed otherwise: with that key file still
0 bytes, ``git commit -S`` produces a commit that DOES carry a ``gpgsig``
header. The configured signer is a program (``gpg.ssh.program`` ->
``/tmp/code-sign``), and the empty ``.pub`` is not the gating factor. The real
failure mode was a *cold signer* early in the session (later commits signed
once it was warm). So a file-size check on the signing key would be a proxy that
both false-positives (the key is routinely 0 bytes here while signing works) and
misses the real cause. The only sound, deterministic signal is to exercise the
real signing path and inspect the result; CLAUDE.md section 1's "live proof, not
a proxy" applied to a signer.

The probe (``probe_sign_status``) creates a throwaway git repo in a temp
directory, copies the merged signing config (``commit.gpgsign``, ``gpg.format``,
``user.signingkey``, ``gpg.ssh.program``, ``gpg.program``) into it, makes one
``--allow-empty`` signed commit, and inspects ``git cat-file commit HEAD`` for a
``gpgsig`` header. It never touches the real repository or its history. It reads
no key material (it only re-applies config *values* git already resolved and
stats nothing under ``~/.ssh``), so it stays inside the CLAUDE.md section 4
secret boundary. Outcomes:

* ``signed``: the test commit carries a signature (healthy; silent).
* ``unsigned``: the test commit succeeded but carries NO signature. This is
  the exact #1985 failure: signing is enabled yet a commit lands unsigned and
  silent. The gate fires LOUD on this and only this.
* ``unknown``: the probe could not be evaluated (git missing, signer errored
  non-zero, temp-dir failure). A non-zero ``git commit`` means git itself would
  fail loudly on the real commit too (not a silent unsigned landing), so the
  gate stays out of the way; fail-open per CLAUDE.md section 4.

Two modes, mirroring ``preflight_session_base_freshness.py`` (defense in depth,
CLAUDE.md section 4; surface early AND block at the commit boundary):

* ``session-start``: a SessionStart hook. In a remote session, when signing is
  required and the probe returns ``unsigned``, it emits a loud
  ``additionalContext`` warning so the cold/broken signer is fixed BEFORE any
  commit. Always exits 0; never wedges a session.
* hook mode (no subcommand, event JSON on stdin): a PreToolUse ``Bash`` hook.
  It DENIES a ``git commit`` only when the probe has just demonstrated an
  ``unsigned`` outcome, so the block is a proven true positive rather than a
  prediction; near-zero false-positive blast radius. An explicit, reviewed
  unsigned commit can still proceed by appending the ``# unsigned-ack`` marker
  (the same opt-in ``gate_unsigned_commit_bash.py`` honors).
* ``check``: print the verdict and exit 0 (signed / not required / unknown) or
  1 (unsigned). Lets the #1985 condition be reproduced deterministically.

Blast radius is bounded three ways: the active probe runs only in remote
sessions (``CLAUDE_CODE_REMOTE`` / ``CODEX_CODE_REMOTE``), where signing is
non-interactive via the signer program, so a local-dev gpg key with a pinentry
passphrase is never poked; the DENY fires only on a demonstrated unsigned
outcome; and every infrastructure error fails open. The block approach (over a
warning alone) is chosen because the retro's loss; an irreversible unsigned base
commit; cannot be undone after the fact, so the guarantee must hold at the
commit boundary, not merely be surfaced at session start where it can be missed.

Contract:
- Inputs: the ``session-start`` / ``check`` subcommand, or (no subcommand) a
  PreToolUse event on stdin.
- Outputs: ``session-start`` prints an ``additionalContext`` JSON object when
  signing is required but the probe is ``unsigned``; hook mode prints a deny
  decision in the same case; ``check`` prints the verdict. Exit 0 except
  ``check`` which exits 1 when ``unsigned``.
- Failure policy: fail-open (exit 0, no decision) on any internal error so the
  guard cannot wedge a session; the substantive signal still fails loud via the
  deny / the ``check`` exit code.

Tested by tests/test_check_commit_signing_ready.py. Refs #1987, #1713, #1985.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any

from _git import run_git
from _hook_runtime import build_deny, run_event_hook

# Both remote signals, mirroring the install-uv.sh dual-signal gate so the check
# is operative under Claude Code on the Web AND Codex/Devin cloud sessions.
_REMOTE_ENV_VARS = ("CLAUDE_CODE_REMOTE", "CODEX_CODE_REMOTE")

# Opt-in marker for a reviewed, intentional unsigned commit. Reuses the marker
# established by gate_unsigned_commit_bash.py for the same unsigned-commit
# category (CLAUDE.md section 4: one category, one control).
_ACK_MARKER = "# unsigned-ack"

# Match a ``git commit`` anywhere in the command (commits chain, e.g.
# ``git add -A && git commit``) but keep plumbing like ``git commit-tree`` out.
# Mirrors preflight_session_base_freshness / preflight_commit_session_branch.
_GIT_COMMIT_RE = re.compile(r"\bgit\s+commit(?![\w-])")

# Signing config copied verbatim into the throwaway probe repo. ``commit.gpgsign``
# is set separately (forced true in the probe); these are the resolver inputs
# that decide whether and how a signature is produced.
_SIGNING_CONFIG_KEYS = (
    "gpg.format",
    "user.signingkey",
    "gpg.ssh.program",
    "gpg.program",
)

_PROBE_TIMEOUT_SECONDS = 30
_GIT_TIMEOUT_SECONDS = 10


def _is_remote() -> bool:
    """Return True when either remote-session signal is set to ``true``."""
    return any(os.environ.get(var, "").lower() == "true" for var in _REMOTE_ENV_VARS)


def _git_config_get(key: str) -> str | None:
    """Return the merged git config value for *key*, or None when unset/error."""
    try:
        result = run_git(["config", "--get", key], timeout=_GIT_TIMEOUT_SECONDS)
    except (RuntimeError, OSError):
        return None
    if result.returncode != 0:
        return None
    value = result.stdout.strip()
    return value or None


def signing_required() -> bool:
    """Return True when ``commit.gpgsign`` resolves to git-boolean true.

    Uses ``--type=bool`` so git normalises every documented true spelling
    (``true``/``1``/``yes``/``on``) to ``true``; an unset or false-ish value
    yields False and the gate has nothing to guarantee.
    """
    try:
        result = run_git(["config", "--type=bool", "--get", "commit.gpgsign"], timeout=_GIT_TIMEOUT_SECONDS)
    except (RuntimeError, OSError):
        return False
    if result.returncode != 0:
        return False
    return result.stdout.strip().lower() == "true"


def probe_sign_status() -> str:
    """Exercise the real signing path in a throwaway repo; return the verdict.

    Returns ``"signed"`` when a test ``--allow-empty`` commit carries a
    ``gpgsig`` header, ``"unsigned"`` when the commit succeeds without one (the
    silent #1985 failure), or ``"unknown"`` when the probe cannot be evaluated
    (git missing, a non-zero commit/cat-file, or a temp-dir error). Never
    mutates the real repository.
    """
    try:
        tmp = tempfile.mkdtemp(prefix="commit-signing-probe-")
    except OSError:
        return "unknown"
    try:
        init = run_git(["init", "-q", tmp], timeout=_GIT_TIMEOUT_SECONDS)
        if init.returncode != 0:
            return "unknown"

        # Probe identity; never the operator's, since this commit is discarded.
        run_git(["-C", tmp, "config", "user.email", "signing-probe@local"], timeout=_GIT_TIMEOUT_SECONDS)
        run_git(["-C", tmp, "config", "user.name", "signing probe"], timeout=_GIT_TIMEOUT_SECONDS)
        run_git(["-C", tmp, "config", "commit.gpgsign", "true"], timeout=_GIT_TIMEOUT_SECONDS)
        for key in _SIGNING_CONFIG_KEYS:
            value = _git_config_get(key)
            if value is not None:
                run_git(["-C", tmp, "config", key, value], timeout=_GIT_TIMEOUT_SECONDS)

        commit = run_git(
            ["-C", tmp, "commit", "--allow-empty", "-S", "-m", "signing probe"],
            timeout=_PROBE_TIMEOUT_SECONDS,
        )
        if commit.returncode != 0:
            # git itself refused to produce the commit: a real commit would fail
            # loudly too, not land silently unsigned. Out of scope; fail-open.
            return "unknown"

        cat = run_git(["-C", tmp, "cat-file", "commit", "HEAD"], timeout=_GIT_TIMEOUT_SECONDS)
        if cat.returncode != 0:
            return "unknown"
        for line in cat.stdout.splitlines():
            if line.startswith("gpgsig"):
                return "signed"
        return "unsigned"
    except (RuntimeError, OSError, subprocess.TimeoutExpired):
        return "unknown"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _build_warning() -> str:
    return (
        "COMMIT SIGNING NOT READY: commit.gpgsign is true, but a test signature "
        "could not be produced; a `git commit` would land UNSIGNED and silent. "
        "This is the PR #1985 failure (retro #1987, Fact 2): an unsigned base "
        "commit on a ruleset-protected branch cannot be rewritten (force-push and "
        "branch deletion are both blocked), so it is effectively irreversible.\n"
        "Do NOT commit until signing works. The signer is usually cold at session "
        "start and warms up shortly; re-run the check before committing:\n"
        "  python3 scripts/check_commit_signing_ready.py check\n"
        "A git commit while signing is broken is blocked by "
        "scripts/check_commit_signing_ready.py until a test sign succeeds."
    )


def _build_deny_reason() -> str:
    return (
        "Blocked by scripts/check_commit_signing_ready.py: commit.gpgsign is true, "
        "but a live test signature just came back UNSIGNED, so this commit would "
        "land unsigned and silent. On this ruleset-protected branch force-push and "
        "branch deletion are blocked, so an unsigned base commit cannot be "
        "rewritten (the PR #1985 failure; retro #1987, Fact 2).\n\n"
        "The signer is usually cold at session start and warms up within moments. "
        "Wait briefly, confirm it is ready, then commit:\n"
        "  python3 scripts/check_commit_signing_ready.py check\n\n"
        "If an unsigned commit is genuinely intended and reviewed (e.g. a throwaway "
        f"scratch repo), append a '{_ACK_MARKER}' comment to the command to opt in. "
        "Refs #1987, #1985, #1713."
    )


def _emit_context(message: str) -> None:
    print(json.dumps({"hookSpecificOutput": {"additionalContext": message}}))


# ---------------------------------------------------------------------------
# session-start mode
# ---------------------------------------------------------------------------
def cmd_session_start(_args: argparse.Namespace) -> int:
    """SessionStart hook: warn loud when signing is required but not working."""
    if not _is_remote():
        return 0
    try:
        if not signing_required():
            return 0
        status = probe_sign_status()
    except Exception:
        return 0
    if status == "unsigned":
        _emit_context(_build_warning())
    return 0


# ---------------------------------------------------------------------------
# hook mode (PreToolUse Bash git commit)
# ---------------------------------------------------------------------------
def decide(event: dict[str, Any]) -> dict[str, Any] | None:
    """Return a deny dict when a git commit would land unsigned, else None."""
    if not _is_remote():
        return None
    if event.get("tool_name") != "Bash":
        return None
    command = str((event.get("tool_input") or {}).get("command") or "")
    if not _GIT_COMMIT_RE.search(command):
        return None
    if _ACK_MARKER in command:
        return None
    try:
        if not signing_required():
            return None
        status = probe_sign_status()
    except Exception:
        return None
    if status == "unsigned":
        return build_deny(_build_deny_reason())
    return None


# ---------------------------------------------------------------------------
# check mode
# ---------------------------------------------------------------------------
def cmd_check(_args: argparse.Namespace) -> int:
    """Print the signing verdict; exit 1 only on a demonstrated unsigned outcome."""
    try:
        if not signing_required():
            print("OK: commit.gpgsign is not enabled; nothing to verify.")
            return 0
        status = probe_sign_status()
    except Exception as exc:
        print(f"UNKNOWN: could not evaluate signing readiness ({exc}).")
        return 0
    if status == "signed":
        print("OK: commit signing produced a verified signature.")
        return 0
    if status == "unsigned":
        print(
            "FAIL: commit.gpgsign is true but a test commit landed UNSIGNED. "
            "Signing is not ready; do not commit yet (retro #1987).",
            file=sys.stderr,
        )
        return 1
    print("UNKNOWN: could not produce a test signature (signer/git unavailable).")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd")

    p_ss = sub.add_parser("session-start", help="SessionStart hook: warn when signing is broken.")
    p_ss.set_defaults(func=cmd_session_start)

    p_check = sub.add_parser("check", help="Print signing verdict (exit 0 ok/unknown, 1 unsigned).")
    p_check.set_defaults(func=cmd_check)

    args = parser.parse_args(argv)
    if args.cmd is None:
        return run_event_hook("check_commit_signing_ready", decide, auditable=False)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
