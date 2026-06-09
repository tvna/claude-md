#!/usr/bin/env python3
"""Generate the PR body's ``## Resource Consumption`` section.

Emits the session resource cost of producing a PR as a *per-PR window*: the
wall-clock time and the ccusage token + cost figures spent since the previous
PR-create in this session (or since session start for the first PR), rather
than the cumulative session total.

Why per-PR. ``ccusage session --json`` reports the running cumulative total for
a session. Pasting that verbatim into every PR body double-counts: a session
that opens PR #1 then PR #2 would report PR #1's tokens again under PR #2, and
the Elapsed (computed from the fixed ``CCR_SPAWN_TIMESTAMP_MS`` session-spawn
epoch) would describe the whole session rather than the work for that PR. The
two metrics then describe different windows (#1435).

The fix is a per-PR checkpoint. On each real PR-create the ``checkpoint``
subcommand snapshots the cumulative ccusage totals and a timestamp to a
session-scoped file. The report then subtracts that baseline so both the token
window and the Elapsed window start at the same point -- the previous
PR-create. The checkpoint is advanced only by the ``checkpoint`` subcommand
(wired to the ``mcp__github__create_pull_request`` PostToolUse hook), never by
generating the section, so regenerating a body is idempotent.

The section is required on every PR (``scripts/body_policy.py`` ``_PR_REQUIRED``);
this generator is the deterministic source for it so the numbers are
ccusage-observed rather than hand-typed. Paste the stdout over the placeholder
lines that ``.github/PULL_REQUEST_TEMPLATE.md`` ships.

Each field degrades independently to ``unavailable (no session data)`` when
its input is missing: no checkpoint and no ``CCR_SPAWN_TIMESTAMP_MS`` -> elapsed
unavailable; no session id, ``ccusage`` absent from PATH, a non-zero ccusage
exit, unparseable JSON, or no row for the session -> token/cost/model
unavailable. The script never raises and always prints a presence-valid section
to stdout (exit 0), so a PR author on a host without ccusage -- or a
human-authored PR with no session at all -- still gets a section they can paste
verbatim.

Refs #1413, #1435.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Mapping
from pathlib import Path
from typing import TypedDict

_HEADING = "Resource Consumption"
_UNAVAILABLE = "unavailable (no session data)"
_CCUSAGE_TIMEOUT_S = 20

# Session-scoped per-PR checkpoint file. The directory defaults to the system
# temp dir (ephemeral, container-lifetime); ``CCR_CCUSAGE_CHECKPOINT_DIR``
# overrides it so tests can inject an isolated path. The session id is hashed
# into the file name to keep it filesystem-safe and avoid printing the raw id.
_CHECKPOINT_DIR_ENV = "CCR_CCUSAGE_CHECKPOINT_DIR"
_CHECKPOINT_PREFIX = "claude-md-ccusage-checkpoint-"


class Usage(TypedDict):
    """Per-session token counts and cost extracted from ccusage JSON."""

    input: int
    output: int
    cache_create: int
    cache_read: int
    total: int
    cost: float
    models: list[str]


class Checkpoint(TypedDict):
    """A per-PR snapshot: when the last PR was created and the cumulative
    ccusage totals at that moment, so the next report can subtract them."""

    ts_ms: float
    usage: Usage


_USAGE_INT_FIELDS = ("input", "output", "cache_create", "cache_read", "total")


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

    *spawn_ms* is the window-start epoch in milliseconds: the previous
    PR-create checkpoint timestamp when one exists, otherwise the
    ``CCR_SPAWN_TIMESTAMP_MS`` session-spawn value (typically a string from the
    environment). ``None`` is returned when it is missing, non-numeric, or
    yields a negative interval (a clock skew or a start timestamp in the
    future) -- the caller renders that as the unavailable marker rather than a
    bogus duration.
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


def _coerce_stored_usage(value: object) -> Usage | None:
    """Return a :class:`Usage` from a previously persisted checkpoint mapping.

    The stored shape uses this module's own keys (``input``, ``output``, ...),
    not the ccusage keys :func:`parse_usage` reads. A malformed or partial file
    degrades to ``None`` so a corrupt checkpoint is ignored rather than
    crashing the report.
    """
    if not isinstance(value, Mapping):
        return None
    try:
        ints = {field: int(_coerce_number(value[field])) for field in _USAGE_INT_FIELDS}
        cost = _coerce_number(value["cost"])
    except (KeyError, TypeError, ValueError):
        return None
    models_raw = value.get("models", [])
    models = (
        [str(m) for m in models_raw if m] if isinstance(models_raw, list) else []
    )
    return Usage(cost=cost, models=models, **ints)  # type: ignore[typeddict-item]


def delta_usage(cumulative: Usage, baseline: Usage | None) -> Usage:
    """Return *cumulative* minus *baseline*, the tokens/cost spent for this PR.

    With no *baseline* (the first PR of a session) the cumulative total is the
    window. When any field would go negative the *baseline* is treated as stale
    or belonging to a different session and is ignored -- the cumulative total
    is returned rather than a nonsensical negative delta. ``models`` always
    reflects the current cumulative row.
    """
    if baseline is None:
        return cumulative
    d_input = cumulative["input"] - baseline["input"]
    d_output = cumulative["output"] - baseline["output"]
    d_cache_create = cumulative["cache_create"] - baseline["cache_create"]
    d_cache_read = cumulative["cache_read"] - baseline["cache_read"]
    d_total = cumulative["total"] - baseline["total"]
    d_cost = cumulative["cost"] - baseline["cost"]
    if min(d_input, d_output, d_cache_create, d_cache_read, d_total) < 0 or d_cost < 0:
        return cumulative
    return Usage(
        input=d_input,
        output=d_output,
        cache_create=d_cache_create,
        cache_read=d_cache_read,
        total=d_total,
        cost=d_cost,
        models=cumulative["models"],
    )


_MODEL_TIERS = ("opus", "sonnet", "haiku")
_UNKNOWN_MODEL_TIER = "other-class"


def redact_model(model: str) -> str:
    """Map a ccusage model id to a non-identifying capability tier.

    The runtime model-identity policy withholds the configured model
    identifier from pushed artifacts, so the exact ccusage ``modelsUsed`` id
    (for example ``claude-opus-4-8``) must never be written verbatim into a PR
    body. A ``claude-`` id whose name carries ``opus`` / ``sonnet`` / ``haiku``
    collapses to ``Opus-class`` / ``Sonnet-class`` / ``Haiku-class``; any other
    id (a non-Claude model or an unrecognized shape) collapses to the harmless
    ``other-class`` fallback so an unknown id never leaks through. The match is
    a case-insensitive substring so both the current ``claude-opus-4-8`` shape
    and an older ``claude-3-5-sonnet-...`` shape resolve to the same tier.
    """
    lowered = model.lower()
    for tier in _MODEL_TIERS:
        if tier in lowered:
            return f"{tier.capitalize()}-class"
    return _UNKNOWN_MODEL_TIER


def redact_models(models: list[str]) -> list[str]:
    """Return the order-preserving, de-duplicated capability tiers for *models*.

    Two model ids in the same family (for example two Opus versions) collapse
    to a single ``Opus-class`` entry rather than repeating the tier.
    """
    seen: dict[str, None] = {}
    for model in models:
        seen.setdefault(redact_model(model), None)
    return list(seen)


def render_section(elapsed: str | None, usage: Usage | None) -> str:
    """Return the ``## Resource Consumption`` markdown block.

    *elapsed* is the ``H:MM:SS`` string or ``None``; *usage* is the per-PR
    :class:`Usage` delta or ``None``. Any missing input renders as
    ``unavailable (no session data)`` so the section is always presence-valid
    for ``scripts/body_policy.py``. The ``Model(s)`` line carries the redacted
    capability tier (:func:`redact_models`), never the verbatim model id. The
    output is ASCII so it passes the GitHub-post non-ASCII gate.
    """
    elapsed_txt = elapsed if elapsed else _UNAVAILABLE
    if usage is not None:
        total = (
            f"{usage['total']:,} (input {usage['input']:,} / "
            f"output {usage['output']:,} / cache-create {usage['cache_create']:,} / "
            f"cache-read {usage['cache_read']:,})"
        )
        cost = f"${usage['cost']:.4f}"
        tiers = redact_models(usage["models"])
        models = ", ".join(tiers) if tiers else _UNAVAILABLE
    else:
        total = cost = models = _UNAVAILABLE
    return (
        f"## {_HEADING}\n\n"
        f"- Elapsed (since previous PR or session start): {elapsed_txt}\n"
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


def _checkpoint_path(session_id: str, env: Mapping[str, str]) -> Path | None:
    """Return the checkpoint file path for *session_id*, or ``None``.

    ``None`` when there is no session id (nothing to key on). The directory is
    ``CCR_CCUSAGE_CHECKPOINT_DIR`` when set, else the system temp dir. The
    session id is hashed so the file name is filesystem-safe and the raw id is
    not written into a path.
    """
    if not session_id:
        return None
    base = env.get(_CHECKPOINT_DIR_ENV) or tempfile.gettempdir()
    digest = hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:32]
    return Path(base) / f"{_CHECKPOINT_PREFIX}{digest}.json"


def load_checkpoint(session_id: str, env: Mapping[str, str]) -> Checkpoint | None:
    """Return the persisted per-PR checkpoint for *session_id*, or ``None``.

    ``None`` when no checkpoint exists yet (first PR of the session), the file
    is unreadable, or its contents are malformed -- any of those falls back to
    the session-start baseline rather than crashing.
    """
    path = _checkpoint_path(session_id, env)
    if path is None:
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, Mapping):
        return None
    ts = data.get("ts_ms")
    if isinstance(ts, bool) or not isinstance(ts, int | float):
        return None
    usage = _coerce_stored_usage(data.get("usage"))
    if usage is None:
        return None
    return Checkpoint(ts_ms=float(ts), usage=usage)


def save_checkpoint(
    session_id: str, ts_ms: float, usage: Usage, env: Mapping[str, str]
) -> None:
    """Persist *usage* + *ts_ms* as the checkpoint for *session_id*.

    A best-effort, fail-open write: an unwritable directory or any OS error is
    swallowed so a checkpoint failure can never wedge PR creation (the hook
    that calls this runs after the PR already exists). Written atomically via a
    temp file + ``os.replace`` so a concurrent reader never sees a half file.
    """
    path = _checkpoint_path(session_id, env)
    if path is None:
        return
    payload = json.dumps({"ts_ms": ts_ms, "usage": usage})
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(payload, encoding="utf-8")
        tmp.replace(path)
    except OSError:
        return


def gather(
    env: Mapping[str, str] | None = None, now_ms: float | None = None
) -> str:
    """Return the rendered per-PR section from environment + ccusage inputs.

    *env* and *now_ms* are injectable for tests; they default to
    ``os.environ`` and the current wall clock. The Elapsed window starts at the
    previous PR-create checkpoint when one exists, else at
    ``CCR_SPAWN_TIMESTAMP_MS``; the token/cost figures are the cumulative
    ccusage totals minus the checkpoint baseline.
    """
    env = os.environ if env is None else env
    if now_ms is None:
        now_ms = time.time() * 1000.0
    session_id = env.get("CLAUDE_CODE_SESSION_ID", "")
    checkpoint = load_checkpoint(session_id, env)
    window_start = (
        checkpoint["ts_ms"] if checkpoint else env.get("CCR_SPAWN_TIMESTAMP_MS")
    )
    elapsed = compute_elapsed(window_start, now_ms)
    raw = _run_ccusage(session_id)
    cumulative = parse_usage(raw, session_id) if raw is not None else None
    baseline = checkpoint["usage"] if checkpoint else None
    usage = delta_usage(cumulative, baseline) if cumulative is not None else None
    return render_section(elapsed, usage)


def write_checkpoint(
    env: Mapping[str, str] | None = None, now_ms: float | None = None
) -> None:
    """Advance the per-PR checkpoint to the current cumulative ccusage totals.

    Called by the ``mcp__github__create_pull_request`` PostToolUse hook (the
    real PR-create event). Reads the cumulative ccusage totals and records them
    with *now_ms* so the next report subtracts this boundary. A no-op when
    ccusage yields nothing (no session id, ccusage absent, unparseable) -- any
    prior checkpoint is left intact rather than blanked.
    """
    env = os.environ if env is None else env
    if now_ms is None:
        now_ms = time.time() * 1000.0
    session_id = env.get("CLAUDE_CODE_SESSION_ID", "")
    raw = _run_ccusage(session_id)
    cumulative = parse_usage(raw, session_id) if raw is not None else None
    if cumulative is None:
        return
    save_checkpoint(session_id, now_ms, cumulative, env)


def main(argv: list[str] | None = None) -> int:
    """Dispatch the subcommand.

    No argument (the default): print the ``## Resource Consumption`` section to
    stdout and exit 0. ``checkpoint``: advance the per-PR checkpoint and exit 0.
    Never raises on missing inputs.
    """
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] == "checkpoint":
        write_checkpoint()
        return 0
    sys.stdout.write(gather())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
