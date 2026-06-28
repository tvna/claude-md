#!/usr/bin/env python3
"""Measure the per-request fixed-prefix token cost of repo-resident artifacts.

Cache-read is the dominant per-session cost in Claude Code web sessions
(measured at ~60% of one Opus 4.8 session in PR #1421's
``## Resource Consumption`` section). Cache-read is billed at ~0.1x the
base input rate; $0.50 / 1M tokens for ``claude-opus-4-8``; but it is
paid on *every* request, so the fixed prefix is a per-request multiplier.
Shrinking the prefix is therefore the highest-leverage cache-read lever.

This script establishes a **reproducible, token-accurate baseline** for the
repo-resident slice of that prefix, so reduction work can be measured rather
than guessed (measure-first). It counts tokens with the canonical Anthropic
``count_tokens`` endpoint via the official SDK; never a ``tiktoken``-style
approximation, which is wrong for Claude and undercounts code/non-English
text. Token counts are model-specific, so the model id is passed through to
the endpoint (default ``claude-opus-4-8``).

What this script CAN measure (repo-resident, exact bytes available):

* ``CLAUDE.md``              ; the Claude Code prefix injection (compiled).
* ``AGENTS.md``              ; the Codex prefix injection (compiled).
* ``.apm/instructions/master.instructions.md``; the editable APM source
  that both compiled artifacts are generated from (``apm compile``).
* Any extra file paths passed as positional arguments; e.g. a bundled
  skill body (``.../claude-api/SKILL.md``) whose exact bytes live outside
  the repo but are readable on the host running the measurement.

What this script CANNOT measure (harness-owned; the exact bytes the API
sees are injected by the Claude Code web harness / MCP servers and are not
present in this repository or on disk):

* The Claude Code base system prompt.
* Built-in tool schemas and the ``mcp__github__*`` schemas expanded via
  ToolSearch.
* The skill-list rendering.

Those components are enumerated in the output so the measurement boundary is
visible by inspection, not buried in prose.

Running it
----------
The ``anthropic`` SDK is intentionally NOT a locked project dependency (it
would touch the supply-chain surface this repo guards). Run it with an
ephemeral dependency where an Anthropic credential is available::

    ANTHROPIC_API_KEY=... uv run --with anthropic \
        python scripts/measure_prefix_tokens.py

    # measure an out-of-repo skill body too:
    ANTHROPIC_API_KEY=... uv run --with anthropic \
        python scripts/measure_prefix_tokens.py /path/to/claude-api/SKILL.md

    # machine-readable:
    ... python scripts/measure_prefix_tokens.py --json

Credential: create an API key at https://platform.claude.com (or supply an
``ANTHROPIC_AUTH_TOKEN`` from ``ant auth login``). The key value is read
from the environment, used only to call ``count_tokens``, and never printed.

Failure policy
--------------
The byte size of every target is always reported (it needs no network).
When no credential / SDK is available, token columns degrade to
``unavailable`` with a single explicit reason on stderr and the process
exits non-zero (per CLAUDE.md section 4: fail loudly, never silently swap
in a bogus number). A missing target file degrades only its own row.

Refs the cache-read reduction issue.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

MODEL_DEFAULT = "claude-opus-4-8"
_UNAVAILABLE = "unavailable"
REPO_ROOT = Path(__file__).resolve().parent.parent

# Repo-resident prefix sources, in (label, repo-relative path) form. The
# label is what appears in the rendered table; keep it ASCII for the
# GitHub-post non-ASCII gate.
_REPO_TARGETS: tuple[tuple[str, str], ...] = (
    ("CLAUDE.md (Claude prefix)", "CLAUDE.md"),
    ("AGENTS.md (Codex prefix)", "AGENTS.md"),
    ("master.instructions.md (APM source)", ".apm/instructions/master.instructions.md"),
)

# Prefix components that are injected by the harness and cannot be measured
# from the repository; surfaced in the output so the boundary is explicit.
_HARNESS_OWNED: tuple[str, ...] = (
    "Claude Code base system prompt",
    "Built-in tool schemas + mcp__github__* (ToolSearch-expanded) schemas",
    "Skill-list rendering",
)

# A token counter maps prompt text to its model-specific token count.
Counter = Callable[[str], int]


@dataclass(frozen=True)
class Target:
    """A file whose prefix contribution is being measured."""

    label: str
    path: Path


@dataclass(frozen=True)
class Measurement:
    """The result of measuring one :class:`Target`.

    ``tokens`` is ``None`` when the count could not be obtained (no API
    access, or the file was unreadable); ``error`` then carries the reason.
    ``byte_size`` is ``None`` only when the file itself is unreadable.
    """

    label: str
    path: Path
    byte_size: int | None
    tokens: int | None
    error: str | None


def repo_targets(repo_root: Path) -> list[Target]:
    """Return the canonical repo-resident prefix sources under *repo_root*."""
    return [Target(label, repo_root / rel) for label, rel in _REPO_TARGETS]


def extra_targets(paths: list[str]) -> list[Target]:
    """Return :class:`Target`s for ad-hoc file *paths* (e.g. a skill body)."""
    return [Target(f"extra: {p}", Path(p)) for p in paths]


def measure_target(target: Target, counter: Counter | None) -> Measurement:
    """Measure one *target*, never raising.

    Reads the file (byte size needs no network). When *counter* is ``None``
    the token count is reported unavailable; otherwise the counter is invoked
    and any failure is captured as the row's ``error`` rather than crashing
    the whole run.
    """
    try:
        text = target.path.read_text(encoding="utf-8")
    except OSError as exc:
        return Measurement(target.label, target.path, None, None, f"unreadable: {exc}")
    byte_size = len(text.encode("utf-8"))
    if counter is None:
        return Measurement(
            target.label, target.path, byte_size, None, "no API access"
        )
    try:
        tokens = counter(text)
    except Exception as exc:
        # Surface any SDK/HTTP failure as this row's error rather than
        # crashing the whole batch; one bad count must not lose the rest.
        return Measurement(
            target.label, target.path, byte_size, None, f"count failed: {exc}"
        )
    return Measurement(target.label, target.path, byte_size, tokens, None)


def measure(targets: list[Target], counter: Counter | None) -> list[Measurement]:
    """Measure every target in order."""
    return [measure_target(t, counter) for t in targets]


def _share(tokens: int | None, total: int) -> str:
    """Return the percentage *tokens* is of *total*, or ``-`` when unknown."""
    if tokens is None or total <= 0:
        return "-"
    return f"{tokens / total * 100:.1f}%"


def render_table(measurements: list[Measurement], model: str) -> str:
    """Return an ASCII markdown report of *measurements* for *model*.

    Includes a measured-token total, a per-row share of that total, and an
    explicit list of the harness-owned components that cannot be measured
    from the repo. ASCII-only so it is safe to paste into a GitHub issue.
    """
    measured_total = sum(m.tokens for m in measurements if m.tokens is not None)
    lines = [
        f"Fixed-prefix token measurement (model: {model})",
        "",
        "| Component | Path | Bytes | Tokens | Share |",
        "| --- | --- | ---: | ---: | ---: |",
    ]
    for m in measurements:
        bytes_txt = f"{m.byte_size:,}" if m.byte_size is not None else _UNAVAILABLE
        tokens_txt = f"{m.tokens:,}" if m.tokens is not None else _UNAVAILABLE
        rel = _display_path(m.path)
        lines.append(
            f"| {m.label} | {rel} | {bytes_txt} | {tokens_txt} "
            f"| {_share(m.tokens, measured_total)} |"
        )
    total_txt = f"{measured_total:,}" if measured_total else _UNAVAILABLE
    lines.append(f"| **Measured total** |  |  | **{total_txt}** | |")
    lines.append("")
    errors = [m for m in measurements if m.error]
    if errors:
        lines.append("Notes:")
        lines.extend(f"- {m.label}: {m.error}" for m in errors)
        lines.append("")
    lines.append("NOT measurable from repo (harness-owned prefix):")
    lines.extend(f"- {name}" for name in _HARNESS_OWNED)
    return "\n".join(lines) + "\n"


def render_json(measurements: list[Measurement], model: str) -> str:
    """Return a machine-readable JSON report of *measurements*."""
    payload = {
        "model": model,
        "measured_total_tokens": sum(
            m.tokens for m in measurements if m.tokens is not None
        ),
        "components": [
            {
                "label": m.label,
                "path": _display_path(m.path),
                "bytes": m.byte_size,
                "tokens": m.tokens,
                "error": m.error,
            }
            for m in measurements
        ],
        "harness_owned_not_measurable": list(_HARNESS_OWNED),
    }
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def _display_path(path: Path) -> str:
    """Return *path* relative to the repo root when possible, else as-is."""
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def make_api_counter(model: str) -> Counter:
    """Return a ``count_tokens`` counter bound to *model*, or raise.

    Imports the official Anthropic SDK lazily so this module loads without
    the dependency (it is run with ``uv run --with anthropic``). Raises
    ``RuntimeError``; with a remediation message that never echoes the
    credential; when the SDK is absent or no credential is set.
    """
    try:
        import anthropic  # type: ignore[import-not-found]  # optional, ephemeral dep (uv run --with anthropic)
    except ImportError as exc:
        raise RuntimeError(
            "the 'anthropic' SDK is not importable; run via "
            "`uv run --with anthropic python scripts/measure_prefix_tokens.py` "
            "or `pip install anthropic`"
        ) from exc
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        raise RuntimeError(
            "no Anthropic credential found; set ANTHROPIC_API_KEY "
            "(create one at https://platform.claude.com) before running"
        )
    client = anthropic.Anthropic()

    def counter(text: str) -> int:
        resp = client.messages.count_tokens(
            model=model, messages=[{"role": "user", "content": text}]
        )
        return int(resp.input_tokens)

    return counter


def main(argv: list[str] | None = None) -> int:
    """Measure the prefix, print the report, and return an exit code.

    Returns 0 when token counts were obtained, 2 when no API access was
    available (byte sizes are still printed). A missing target file does not
    fail the run; it degrades that row only.
    """
    parser = argparse.ArgumentParser(
        description="Measure repo-resident fixed-prefix token cost via count_tokens.",
    )
    parser.add_argument(
        "extra_paths",
        nargs="*",
        help="Additional file paths to measure (e.g. an out-of-repo skill body).",
    )
    parser.add_argument("--model", default=MODEL_DEFAULT, help="Model id for count_tokens.")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of a table.")
    parser.add_argument(
        "--repo-root",
        default=str(REPO_ROOT),
        help="Repository root containing the prefix sources.",
    )
    args = parser.parse_args(argv)

    counter: Counter | None
    try:
        counter = make_api_counter(args.model)
    except RuntimeError as exc:
        print(f"::warning::token counts unavailable: {exc}", file=sys.stderr)
        counter = None

    targets = repo_targets(Path(args.repo_root)) + extra_targets(args.extra_paths)
    measurements = measure(targets, counter)

    render = render_json if args.json else render_table
    sys.stdout.write(render(measurements, args.model))
    return 0 if counter is not None else 2


if __name__ == "__main__":
    raise SystemExit(main())
