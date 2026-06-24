"""Shared helper: detect unsigned commits in a git revision range.

Refs #1959. PRs #1744 / #1766 / #1767 were authored on macOS via codex
desktop with a broken signing setup; the operator skipped the signing-config
repair and pushed unsigned commits anyway. The push succeeded locally and was
only blocked later, at merge time, by the server-side ``required_signatures``
ruleset (``.github/rulesets/main.json``). Two local gates close that gap
earlier and share this module so the "is this commit signed" rule lives in one
place (DRY; CLAUDE.md section 5):

* ``preflight_signed_commits.py``; the pre-push preflight step that fails the
  push when an unsigned commit is in the branch range.
* ``gate_unsigned_commit_push.py``; the agent PreToolUse ``git push`` gate that
  denies the Bash push before it leaves the working tree.

Detection model
---------------
A commit is "signed" iff its object carries a ``gpgsig`` header. This is a
*presence* check, not a *trust* check, and is deliberately NOT based on git's
``%G?`` placeholder. ``%G?`` is unreliable for this purpose: an SSH-signed
commit reports ``%G?`` = ``N`` ("no signature") whenever
``gpg.ssh.allowedSignersFile`` is unset, which is the common case on a fresh
clone. Keying off ``N`` would therefore false-positive on every legitimately
SSH-signed commit in any clone without an allowed-signers file. The raw
``gpgsig`` header, by contrast, is present for a signed commit regardless of
signature format (GPG or SSH) and regardless of whether the verifier holds the
public key, so it answers "is a signature attached" without any verification
infrastructure. This was confirmed empirically against this repository: a real
SSH-signed commit (``gpgsig -----BEGIN SSH SIGNATURE-----`` header) reports
``%G?`` = ``N`` here, yet is unmistakably signed. Refs #1959.

The header block is the lines before the first blank line of the commit object;
git emits a multi-line signature as continuation lines (leading space), never a
blank line, so the header/message split is unambiguous.

Opt-in
------
A deliberately unsigned commit can carry the ``unsigned-ack`` marker in its
message, reusing the marker ``scan_workflow_unsigned_commit`` /
``gate_unsigned_commit_bash`` established for the same unsigned-commit category.
An acked commit is reported but not flagged.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from _git import run_git

# Commit-object header that carries the signature (GPG or SSH). Its presence is
# the format-agnostic "this commit is signed" signal.
_SIGNATURE_HEADER = "gpgsig"

# Per-commit opt-in marker for a deliberately unsigned commit. Shares the token
# scan_workflow_unsigned_commit / gate_unsigned_commit_bash use so the
# unsigned-commit category has one ack spelling across the repo.
ACK_MARKER = "unsigned-ack"


@dataclass(frozen=True)
class CommitSignature:
    """One commit's signature state, read from its raw object."""

    sha: str
    signed: bool  # a gpgsig header is present
    subject: str  # first line of the message, for human-facing annotations
    acked: bool  # the unsigned-ack marker is present in the message


def parse_commit_object(sha: str, raw: str) -> CommitSignature:
    """Build a :class:`CommitSignature` from a ``git cat-file commit`` *raw* body.

    Pure function (no I/O) so the parse is unit-testable without a live repo.
    Splits the object into its header block (before the first blank line) and
    its message; a ``gpgsig`` header marks the commit signed, and the message is
    scanned for the ack marker.
    """
    header_block, _, message = raw.partition("\n\n")
    signed = any(line.startswith(_SIGNATURE_HEADER + " ") for line in header_block.splitlines())
    subject = message.splitlines()[0] if message.strip() else ""
    return CommitSignature(
        sha=sha,
        signed=signed,
        subject=subject,
        acked=ACK_MARKER in message,
    )


def select_unsigned(records: list[CommitSignature]) -> list[CommitSignature]:
    """Return the records that are unsigned and not acked.

    Pure function so the unsigned-selection policy is testable in isolation.
    """
    return [r for r in records if not r.signed and not r.acked]


def resolve_base(repo: Path, candidates: tuple[str, ...]) -> str | None:
    """Return the first *candidate* ref that resolves under *repo*, else None.

    Used to find the branch's base ref (``origin/main`` then ``main``) so the
    range under inspection is the branch's own commits rather than all history.
    """
    for ref in candidates:
        completed = run_git(["rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"], cwd=repo)
        if completed.returncode == 0 and completed.stdout.strip():
            return ref
    return None


def _rev_list(repo: Path, rev_args: list[str]) -> list[str]:
    """Return the commit shas selected by ``git rev-list`` over *rev_args*.

    Raises :class:`RuntimeError` on a git error so callers decide between
    fail-loud (the preflight gate) and fail-open (the PreToolUse hook).
    """
    completed = run_git(["rev-list", *rev_args], cwd=repo)
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise RuntimeError(f"git rev-list {' '.join(rev_args)} failed: {detail}")
    return [line.strip() for line in completed.stdout.splitlines() if line.strip()]


def list_signatures(repo: Path, rev_args: list[str]) -> list[CommitSignature]:
    """Inspect the signature state of each commit ``git rev-list`` *rev_args* yields.

    *rev_args* is the selector passed to ``git rev-list``, e.g.
    ``["origin/main..HEAD"]`` or ``["--max-count=1", "HEAD"]``. Each commit's raw
    object is read with ``git cat-file commit`` and parsed for a ``gpgsig``
    header. Raises :class:`RuntimeError` when git exits non-zero.
    """
    records: list[CommitSignature] = []
    for sha in _rev_list(repo, rev_args):
        completed = run_git(["cat-file", "commit", sha], cwd=repo)
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout).strip()
            raise RuntimeError(f"git cat-file commit {sha} failed: {detail}")
        records.append(parse_commit_object(sha, completed.stdout))
    return records
