#!/usr/bin/env python3
"""Generate the PR body's ``## Resource Consumption`` section.

Emits the session resource cost of producing a PR: elapsed wall-clock time
from session start (the ``CCR_SPAWN_TIMESTAMP_MS`` container-spawn epoch, in
milliseconds) to now, and the ccusage token + cost figures for the current
Claude Code session (``ccusage session --json``, the row whose ``period``
field equals ``$CLAUDE_CODE_SESSION_ID``).

The section is required on every PR (``scripts/body_policy.py`` ``_PR_REQUIRED``);
this generator is the deterministic source for it so the numbers are
ccusage-observed rather than hand-typed. Paste the stdout over the placeholder
lines that ``.github/PULL_REQUEST_TEMPLATE.md`` ships.

Each field degrades independently to ``unavailable (no session data)`` when
its input is missing: no ``CCR_SPAWN_TIMESTAMP_MS`` -> elapsed unavailable; no
session id, ``ccusage`` absent from PATH, a non-zero ccusage exit, unparseable
JSON, or no row for the session -> token/cost/model unavailable. The script
never raises and always prints a presence-valid section to stdout (exit 0), so
a PR author on a host without ccusage -- or a human-authored PR with no
session at all -- still gets a section they can paste verbatim.

Refs #1413.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from collections.abc import Mapping
from typing import TypedDict

_HEADING = "Resource Consumption"
_UNAVAILABLE = "unavailable (no session data)"
_CCUSAGE_TIMEOUT_S = 20


class Usage(TypedDict):
    """Per-session token counts and cost extracted from ccusage JSON."""

    input: int
    output: int
    cache_create: int
    cache_read: int
    total: int
    cost: float
    models: list[str]


def _coerce_number(value: object) -> float:
    """Return *value* as a float, raising ``ValueError`` when it is not numeric.

    ``bool`` is rejected explicitly so a JSON ``true`` is never read as ``1``.
    The ccusage JSON shape is untrusted input, so a string or null where a
    number is expected degrades the whole row to unavailable rather than
    crashing the generator.
    """
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"not a number: {value!r}")
    return float(value)


def compute_elapsed(spawn_ms: object, now_ms: float) -> str | None:
    """Return ``H:MM:SS`` elapsed from *spawn_ms* to *now_ms*, or ``None``.

    *spawn_ms* is the ``CCR_SPAWN_TIMESTAMP_MS`` value (epoch milliseconds),
    typically a string from the environment. ``None`` is returned when it is
    missing, non-numeric, or yields a negative interval (a clock skew or a
    spawn timestamp in the future) -- the caller renders that as the
    unavailable marker rather than a bogus duration.
    """
    if spawn_ms is None:
        return None
    try:
        start = float(str(spawn_ms))
    except (TypeError, ValueError):
        return None
    delta = (now_ms - start) / 1000.0
    if delta < 0:
        return None
    total = int(delta)
    hours, rem = divmod(total, 3600)
    minutes, seconds = divmod(rem, 60)
    return f"{hours}:{minutes:02d}:{seconds:02d}"


def parse_usage(raw: object, session_id: str) -> Usage | None:
    """Return a usage dict for *session_id* from ccusage ``session --json``.

    Returns ``None`` when *raw* is not the expected JSON shape or carries no
    usable row. ccusage groups sessions under the ``period`` field, so a row
    whose ``period`` equals *session_id* is the exact match. ``--id`` already
    filters server-side, so when exactly one row is returned it is treated as
    the requested session even if the ``period`` text differs -- a schema
    variation must not blank the numbers ccusage did return.
    """
    try:
        data = json.loads(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    rows = data.get("session") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        return None
    row: dict[str, object] | None = None
    if session_id:
        for candidate in rows:
            if isinstance(candidate, dict) and candidate.get("period") == session_id:
                row = candidate
                break
    if row is None:
        if len(rows) == 1 and isinstance(rows[0], dict):
            row = rows[0]
        else:
            return None
    try:
        models_raw = row.get("modelsUsed", [])
        models = (
            [str(m) for m in models_raw if m]
            if isinstance(models_raw, list)
            else []
        )
        return Usage(
            input=int(_coerce_number(row["inputTokens"])),
            output=int(_coerce_number(row["outputTokens"])),
            cache_create=int(_coerce_number(row["cacheCreationTokens"])),
            cache_read=int(_coerce_number(row["cacheReadTokens"])),
            total=int(_coerce_number(row["totalTokens"])),
            cost=_coerce_number(row["totalCost"]),
            models=models,
        )
    except (KeyError, TypeError, ValueError):
        return None


def render_section(elapsed: str | None, usage: Usage | None) -> str:
    """Return the ``## Resource Consumption`` markdown block.

    *elapsed* is the ``H:MM:SS`` string or ``None``; *usage* is the
    :class:`Usage` from :func:`parse_usage` or ``None``. Any missing input
    renders as ``unavailable (no session data)`` so the section is always
    presence-valid for ``scripts/body_policy.py``. The output is ASCII so it
    passes the GitHub-post non-ASCII gate.
    """
    elapsed_txt = elapsed if elapsed else _UNAVAILABLE
    if usage is not None:
        total = (
            f"{usage['total']:,} (input {usage['input']:,} / "
            f"output {usage['output']:,} / cache-create {usage['cache_create']:,} / "
            f"cache-read {usage['cache_read']:,})"
        )
        cost = f"${usage['cost']:.4f}"
        models = ", ".join(usage["models"]) if usage["models"] else _UNAVAILABLE
    else:
        total = cost = models = _UNAVAILABLE
    return (
        f"## {_HEADING}\n\n"
        f"- Elapsed (session start to PR create): {elapsed_txt}\n"
        f"- Total tokens: {total}\n"
        f"- Cost (USD): {cost}\n"
        f"- Model(s): {models}\n"
    )


def _run_ccusage(session_id: str) -> str | None:
    """Return ccusage ``session --json`` stdout, or ``None`` on any failure.

    The grouped ``session --json`` form (no ``--id``) is used deliberately:
    it yields a ``{"session": [...]}`` array whose rows carry the
    per-session token breakdown, ``totalCost``, ``period`` (the session id),
    and ``modelsUsed`` that :func:`parse_usage` reads. The ``--id`` form
    returns a different, per-entry detail shape (``{"entries": [...]}``)
    without that breakdown, so it is not used here; the caller filters by
    *session_id* against the ``period`` field instead.

    ``None`` on any failure: missing session id, ccusage not on PATH, a
    non-zero exit, or a timeout. Never raises -- the generator must degrade,
    not crash, when the tool is unavailable.
    """
    if not session_id:
        return None
    binary = shutil.which("ccusage")
    if binary is None:
        return None
    try:
        proc = subprocess.run(  # noqa: S603 -- argv is fixed literals; binary is the absolute path from shutil.which, no shell, no user input
            [binary, "session", "--json"],
            capture_output=True,
            text=True,
            timeout=_CCUSAGE_TIMEOUT_S,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout


def gather(
    env: Mapping[str, str] | None = None, now_ms: float | None = None
) -> str:
    """Return the rendered section from live environment + ccusage inputs.

    *env* and *now_ms* are injectable for tests; they default to
    ``os.environ`` and the current wall clock.
    """
    env = os.environ if env is None else env
    if now_ms is None:
        now_ms = time.time() * 1000.0
    elapsed = compute_elapsed(env.get("CCR_SPAWN_TIMESTAMP_MS"), now_ms)
    session_id = env.get("CLAUDE_CODE_SESSION_ID", "")
    raw = _run_ccusage(session_id)
    usage = parse_usage(raw, session_id) if raw is not None else None
    return render_section(elapsed, usage)


def main(argv: list[str] | None = None) -> int:
    """Print the section to stdout and exit 0. Never raises on missing inputs."""
    del argv
    sys.stdout.write(gather())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
