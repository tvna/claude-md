#!/usr/bin/env python3
"""Require a declared token/cost budget before any LLM step enters CI.

Issue #2269 (loop-engineering gap G3: token blowout guard). No workflow
invokes an LLM today, so this gate passes trivially until #2268 introduces
one; it is that future workflow's precondition, not a retrofit.

Division of labor (mirrors the ``scan_gitapex_schema.py`` docstring, #2342):
the generic ``scan-gitapex-schema`` gate already validates every
``.gitapex/*.toml`` (including ``.gitapex/llm-budget-policy.toml``) against
its sibling ``.schema.json`` shape, so this module does not re-validate
shape. It owns only the semantic rules the schema subset cannot express:

* Scan every ``.yml`` / ``.yaml`` file under ``.github/workflows/`` for a
  marker substring declared in ``.gitapex/llm-budget-policy.toml`` (comment
  lines and shell continuations are handled the same way as
  ``scan_workflow_pip.py``, via the shared :mod:`_shell_lines` flattener).
* Any workflow with a marker hit must have a ``budgets[]`` entry naming it;
  that entry must carry ``max_runs_per_day``, ``max_retries``, and at least
  one of ``max_tokens_per_run`` / ``max_cost_usd_per_run`` (this "at least
  one of" rule has no ``oneOf``/``anyOf`` in the schema subset, the same
  documented limitation as ``scan_ssot_schema.py``'s kind/script XOR rule).
* Each present budget value must be a finite number of the expected sign
  (non-negative for ``max_runs_per_day``/``max_retries``, strictly positive
  for the cost/token keys); the schema subset's ``integer``/``number`` types
  alone accept ``inf``/``nan``/negative values, which would declare no real
  ceiling.

Contract:
- Inputs: the ``verify`` subcommand; ``--repo-root`` (default ``.``);
  ``--policy`` (default ``.gitapex/llm-budget-policy.toml``).
- Outputs: ``::error file=<path>,line=<n>::`` annotations on stderr, one per
  marker hit with an incomplete budget; an ``OK:``/``FAIL:`` summary line.
- Failure policy: fails loud (exit 1) per CLAUDE.md section 4 on any
  marker-matched workflow with a missing or incomplete budget, and on an
  unparseable policy file; exit 0 when every marker-matched workflow has a
  complete budget (including trivially, when no marker matches anything).

Tested by ``tests/test_scan_workflow_llm_budget.py``. Refs #2269.
"""

from __future__ import annotations

import argparse
import math
import sys
import tomllib
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from _shell_lines import flatten_shell_continuations

WORKFLOW_SUBDIR = ".github/workflows"
POLICY_PATH = ".gitapex/llm-budget-policy.toml"

_COMMENT_LINE_PREFIX = "#"

# Keys required on every budgets[] entry regardless of the token/cost choice.
_REQUIRED_BUDGET_KEYS = ("max_runs_per_day", "max_retries")
# At least one of these must be present; checked here (not in the schema)
# since the shared draft-2020-12 subset has no oneOf/anyOf combinator.
_COST_KEYS = ("max_tokens_per_run", "max_cost_usd_per_run")


@dataclass(frozen=True)
class MarkerHit:
    """One marker match in a workflow file."""

    workflow: Path
    lineno: int
    pattern: str


def load_policy(path: Path) -> dict[str, object]:
    """Return the parsed policy TOML at *path*."""
    with path.open("rb") as fh:
        return tomllib.load(fh)


def extract_markers(policy: dict[str, object]) -> list[str]:
    """Return the marker pattern strings declared in *policy*."""
    markers = policy.get("markers")
    if not isinstance(markers, list):
        return []
    return [
        m["pattern"]
        for m in markers
        if isinstance(m, dict) and isinstance(m.get("pattern"), str)
    ]


def extract_budgets(policy: dict[str, object]) -> dict[str, dict[str, object]]:
    """Return {workflow basename: budget entry} declared in *policy*."""
    budgets = policy.get("budgets")
    if not isinstance(budgets, list):
        return {}
    result: dict[str, dict[str, object]] = {}
    for entry in budgets:
        if isinstance(entry, dict) and isinstance(entry.get("workflow"), str):
            result[entry["workflow"]] = entry
    return result


def _is_finite_nonnegative(value: object) -> bool:
    """True if *value* is a finite, non-negative int/float (bool excluded)."""
    return (
        isinstance(value, int | float)
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value >= 0
    )


def _is_finite_positive(value: object) -> bool:
    """True if *value* is a finite, strictly positive int/float (bool excluded)."""
    return (
        isinstance(value, int | float)
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value > 0
    )


def missing_budget_keys(budget: dict[str, object] | None) -> list[str]:
    """Return the required keys *budget* lacks or declares with an invalid value.

    A missing budget entry (``None``) is reported as lacking every required
    key. Otherwise: both of :data:`_REQUIRED_BUDGET_KEYS` must be present and
    a finite number >= 0, and at least one of :data:`_COST_KEYS` must be
    present and a finite number > 0. The schema subset only constrains these
    fields to ``integer``/``number``, so a value has to be checked here too:
    ``inf``, ``nan``, a negative count, or a zero cost/token cap would
    otherwise pass shape validation while declaring no real ceiling, which
    defeats the token-blowout guard this gate exists to provide.
    """
    if budget is None:
        return [*_REQUIRED_BUDGET_KEYS, " or ".join(_COST_KEYS)]
    missing = [
        key
        for key in _REQUIRED_BUDGET_KEYS
        if key not in budget or not _is_finite_nonnegative(budget[key])
    ]
    if not any(key in budget and _is_finite_positive(budget[key]) for key in _COST_KEYS):
        missing.append(" or ".join(_COST_KEYS))
    return missing


def scan_line(line: str, markers: list[str]) -> str | None:
    """Return the first marker matching *line*, or None.

    Comment lines (first non-whitespace char is ``#``) are skipped so the
    marker list can be documented inside workflow YAML without self-tripping.
    """
    stripped = line.lstrip()
    if stripped.startswith(_COMMENT_LINE_PREFIX):
        return None
    for pattern in markers:
        if pattern in line:
            return pattern
    return None


def scan_text(text: str, markers: list[str]) -> list[tuple[int, str]]:
    """Return (1-based line number, matched pattern) for every marker hit in *text*.

    Shell backslash continuations are flattened first (see
    :func:`_shell_lines.flatten_shell_continuations`) so a marker split across
    a ``\\`` continuation is still caught.
    """
    hits: list[tuple[int, str]] = []
    for lineno, line in flatten_shell_continuations(text):
        pattern = scan_line(line, markers)
        if pattern is not None:
            hits.append((lineno, pattern))
    return hits


def _iter_workflow_files(workflow_dir: Path) -> Iterator[Path]:
    for path in sorted(workflow_dir.rglob("*")):
        if path.is_file() and path.suffix in (".yml", ".yaml"):
            yield path


def find_marker_hits(repo_root: Path, markers: list[str]) -> list[MarkerHit]:
    """Return every marker hit across ``.github/workflows/*.{yml,yaml}``.

    Returns an empty list when the directory is absent or *markers* is empty.
    """
    workflow_dir = repo_root / WORKFLOW_SUBDIR
    if not workflow_dir.exists() or not markers:
        return []
    hits: list[MarkerHit] = []
    for path in _iter_workflow_files(workflow_dir):
        rel = path.relative_to(repo_root)
        text = path.read_text(encoding="utf-8", errors="ignore")
        for lineno, pattern in scan_text(text, markers):
            hits.append(MarkerHit(workflow=rel, lineno=lineno, pattern=pattern))
    return hits


def find_violations(
    repo_root: Path,
    *,
    policy: dict[str, object],
) -> list[tuple[MarkerHit, list[str]]]:
    """Return (marker hit, missing budget keys) for every under-budgeted workflow.

    A workflow with no marker hit is not returned at all. A workflow with a
    marker hit and a complete budget entry is not returned either; only
    incomplete or absent budgets are violations.
    """
    markers = extract_markers(policy)
    budgets = extract_budgets(policy)
    violations: list[tuple[MarkerHit, list[str]]] = []
    for hit in find_marker_hits(repo_root, markers):
        missing = missing_budget_keys(budgets.get(hit.workflow.name))
        if missing:
            violations.append((hit, missing))
    return violations


def _cmd_verify(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root).resolve()
    policy_path = repo_root / args.policy

    try:
        policy = load_policy(policy_path)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        print(f"::error file={args.policy}::cannot parse policy file: {exc}", file=sys.stderr)
        return 1

    violations = find_violations(repo_root, policy=policy)
    for hit, missing in violations:
        print(
            f"::error file={hit.workflow},line={hit.lineno}::"
            f"LLM-invoking marker {hit.pattern!r} matched with no complete budget "
            f"declared in {args.policy} for workflow {hit.workflow.name!r}; "
            f"missing: {', '.join(missing)}.",
            file=sys.stderr,
        )
    if violations:
        print(
            f"FAIL: {len(violations)} undeclared-LLM-budget violation(s) in workflow YAML.",
            file=sys.stderr,
        )
        return 1

    print("OK: every LLM-invoking workflow step declares a complete budget.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_verify = sub.add_parser(
        "verify",
        help="Scan workflow YAML for undeclared LLM budgets; exit 1 on violation.",
    )
    p_verify.add_argument("--repo-root", default=".")
    p_verify.add_argument("--policy", default=POLICY_PATH)
    p_verify.set_defaults(func=_cmd_verify)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
