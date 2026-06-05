#!/usr/bin/env python3
"""Keep ``$CLAUDE_ENV_FILE`` PATH persistence centralized in one helper.

Refs #1230. The SessionStart provisioning scripts (``install-uv.sh``,
``install-rtk.sh``, ``session_uv_local_pin.sh``) each used to inline the same
"append ``export PATH`` to ``$CLAUDE_ENV_FILE``" block. #1230 extracted that
into ``scripts/_session_path.sh`` (``persist_session_path``). This gate keeps
the symmetry from regressing: any *future* ``scripts/*.sh`` that writes to
``$CLAUDE_ENV_FILE`` directly -- instead of sourcing the helper and calling
``persist_session_path`` -- re-creates the duplication this refactor removed.

The rule:

* Exactly one file -- ``scripts/_session_path.sh`` -- may redirect (``>>`` /
  ``>``) into ``$CLAUDE_ENV_FILE``. Every other ``scripts/*.sh`` must persist
  PATH via ``persist_session_path``, never a private inline write.
* The helper itself MUST keep that write, so the centralization cannot be
  silently gutted while the call sites still expect persistence.

Comment mentions of ``$CLAUDE_ENV_FILE`` are fine; only an actual write
redirection (``>> "$CLAUDE_ENV_FILE"``) counts as a violation. The name-free
invariant means a brand-new provisioning script is covered without editing
this gate.

CLI::

    python3 scripts/scan_session_path_drift.py verify  # exit 1 on a stray write
    python3 scripts/scan_session_path_drift.py list     # print every env-file writer

Fails loud per CLAUDE.md section 4. Tested by
``tests/test_scan_session_path_drift.py``. Refs #1230.

Contract:
    Inputs: the ``verify`` or ``list`` subcommand; the ``scripts/`` directory
        (``--scripts-dir`` to override). No stdin, no env input.
    Outputs: ``verify`` prints ``::error::`` per stray write and per missing
        helper write, exit 0 when the invariant holds and exit 1 otherwise;
        ``list`` prints ``<file>:<lineno>: <line>`` for every env-file write.
    Failure policy: fails loud per CLAUDE.md section 4 -- a stray write, or a
        helper that no longer writes the env file, exits non-zero.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"

# The single file allowed to write $CLAUDE_ENV_FILE.
HELPER_NAME = "_session_path.sh"

# An actual write redirection into $CLAUDE_ENV_FILE: `>>` or `>` followed by
# the variable in any of its `$CLAUDE_ENV_FILE` / `${CLAUDE_ENV_FILE}` /
# quoted forms. Comments that merely name the variable do not match because
# they carry no redirection operator.
_ENV_FILE_WRITE = re.compile(r""">>?\s*["']?\$\{?CLAUDE_ENV_FILE\}?""")


@dataclass(frozen=True)
class EnvFileWrite:
    """One line that redirects into ``$CLAUDE_ENV_FILE``."""

    script: str  # file name, e.g. "install-uv.sh"
    lineno: int
    line: str


def _iter_writes(scripts_dir: Path) -> list[EnvFileWrite]:
    """Return every ``$CLAUDE_ENV_FILE`` write redirection under *scripts_dir*."""
    writes: list[EnvFileWrite] = []
    for path in sorted(scripts_dir.glob("*.sh")):
        for lineno, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), 1
        ):
            if _ENV_FILE_WRITE.search(line):
                writes.append(
                    EnvFileWrite(script=path.name, lineno=lineno, line=line.strip())
                )
    return writes


def stray_writes(scripts_dir: Path = SCRIPTS_DIR) -> list[EnvFileWrite]:
    """Return env-file writes outside the one allowed helper."""
    return [w for w in _iter_writes(scripts_dir) if w.script != HELPER_NAME]


def helper_writes_env_file(scripts_dir: Path = SCRIPTS_DIR) -> bool:
    """Return True iff the helper still owns a ``$CLAUDE_ENV_FILE`` write."""
    return any(w.script == HELPER_NAME for w in _iter_writes(scripts_dir))


def _cmd_verify(args: argparse.Namespace) -> int:
    scripts_dir = Path(args.scripts_dir)
    errors = 0

    for write in stray_writes(scripts_dir):
        errors += 1
        print(
            f"::error file=scripts/{write.script},line={write.lineno}::"
            f"scripts/{write.script}:{write.lineno} writes $CLAUDE_ENV_FILE "
            f"directly ({write.line!r}). Persist PATH via persist_session_path "
            f"from scripts/{HELPER_NAME} instead (#1230).",
            file=sys.stderr,
        )

    if not helper_writes_env_file(scripts_dir):
        errors += 1
        print(
            f"::error::scripts/{HELPER_NAME} no longer writes $CLAUDE_ENV_FILE; "
            f"the shared persist_session_path helper must keep the single "
            f"PATH-persistence write (#1230).",
            file=sys.stderr,
        )

    if errors:
        print(
            f"FAIL: {errors} $CLAUDE_ENV_FILE persistence drift issue(s).",
            file=sys.stderr,
        )
        return 1
    print("OK: $CLAUDE_ENV_FILE persistence is centralized in "
          f"scripts/{HELPER_NAME}.")
    return 0


def _cmd_list(args: argparse.Namespace) -> int:
    for write in _iter_writes(Path(args.scripts_dir)):
        print(f"scripts/{write.script}:{write.lineno}: {write.line}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_verify = sub.add_parser("verify", help="fail on a stray $CLAUDE_ENV_FILE write")
    p_verify.add_argument("--scripts-dir", default=str(SCRIPTS_DIR))
    p_verify.set_defaults(func=_cmd_verify)

    p_list = sub.add_parser("list", help="print every $CLAUDE_ENV_FILE writer")
    p_list.add_argument("--scripts-dir", default=str(SCRIPTS_DIR))
    p_list.set_defaults(func=_cmd_list)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
