#!/usr/bin/env python3
"""SessionStart hook: pin plan-mode language to the CODEOWNERS owner.

Resolves the primary owner from ``.github/CODEOWNERS``, looks up that
handle in ``.github/owners.yaml`` (ISO-639-1 code), and emits a
``hookSpecificOutput.additionalContext`` block telling the model to
write plan-mode artifacts (plan files at ``/root/.claude/plans/*.md``
and chat responses while planning) in that language.

The injected context explicitly carves out GitHub posts via
``mcp__github__*`` write tools, which remain ASCII-only under Layer 2.5
(``scripts/preflight_non_ascii.py``). The two hooks compose: this one
shapes local plan output, the other gates GitHub I/O.

Architecture mirrors :mod:`preflight_non_ascii`: pure functions on top,
one thin stdin/stdout boundary at the bottom (:func:`main`). Any error
fails open per CLAUDE.md Sec.4 -- a hook bug must never wedge the
session, and the absence of the injected context degrades to the
pre-existing (English) behavior. Refs #211.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

_CODEOWNERS_PATH = Path(".github") / "CODEOWNERS"
_OWNERS_YAML_PATH = Path(".github") / "owners.yaml"


# ---------------------------------------------------------------------------
# Pure functions
# ---------------------------------------------------------------------------


def parse_codeowners(text: str) -> list[tuple[str, list[str]]]:
    """Return ``[(pattern, [handles])]`` rules from CODEOWNERS text.

    Comments (``#``-leading after lstrip) and blank lines are skipped.
    Each remaining line is split on whitespace; the first token is the
    glob pattern, the rest are owner handles (kept with the leading
    ``@`` so equality with ``owners.yaml`` keys is literal).
    """
    rules: list[tuple[str, list[str]]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 2:
            # Pattern without owners -- valid CODEOWNERS (unsets
            # ownership) but uninteresting for language resolution.
            continue
        pattern, handles = parts[0], [p for p in parts[1:] if p.startswith("@")]
        if handles:
            rules.append((pattern, handles))
    return rules


def primary_owner(rules: list[tuple[str, list[str]]]) -> str | None:
    """Return the most frequent handle across rules, or ``None``.

    Frequency-based so the function works on repositories with or
    without a ``*`` catch-all line. Ties are broken by first-appearance
    order, which keeps the result stable as new specific rules are
    added below the primary one.
    """
    counts: dict[str, int] = {}
    order: list[str] = []
    for _pattern, handles in rules:
        for handle in handles:
            if handle not in counts:
                order.append(handle)
            counts[handle] = counts.get(handle, 0) + 1
    if not counts:
        return None
    max_count = max(counts.values())
    for handle in order:
        if counts[handle] == max_count:
            return handle
    return None  # unreachable, but keeps the type narrow


def load_owner_languages(yaml_text: str) -> dict[str, str]:
    """Return a ``{handle: iso639_1}`` map parsed from owners.yaml.

    Empty text yields ``{}``. Non-mapping top-level structures raise
    ``ValueError`` so :func:`main` fails open with a diagnostic. Entries
    whose key or value is not a string are dropped silently -- the
    sidecar is owner-authored config, not user input, so loud failure
    on a single bad row would over-block.
    """
    if not yaml_text.strip():
        return {}
    # Lazy import: declared in pyproject.toml, but a fresh clone before
    # `uv sync` (or an older venv) may lack it. ImportError bubbles up
    # to main() which logs and fails open per CLAUDE.md Sec.4.
    import yaml

    data = yaml.safe_load(yaml_text)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError(
            f"owners.yaml top-level must be a mapping, got {type(data).__name__}"
        )
    out: dict[str, str] = {}
    for key, value in data.items():
        if isinstance(key, str) and isinstance(value, str):
            out[key] = value
    return out


def resolve_language(
    codeowners_text: str, owners_yaml_text: str
) -> tuple[str | None, str | None]:
    """Return ``(owner_handle, iso_code)`` or ``(owner, None)`` / ``(None, None)``.

    Two-value return so :func:`build_context_message` can quote the
    handle in the injected text (useful for the reader to verify the
    source). ``None`` for the language means "no entry in owners.yaml"
    -- the caller treats this as "no context to inject".
    """
    owner = primary_owner(parse_codeowners(codeowners_text))
    if owner is None:
        return None, None
    languages = load_owner_languages(owners_yaml_text)
    return owner, languages.get(owner)


def build_context_message(owner: str, iso: str) -> str:
    """Return the additionalContext string for SessionStart.

    Wording is deliberate: it names the source files (so a reader can
    audit the policy), pins the scope to plan-mode artifacts, and
    carves out ``mcp__github__*`` write tools so it cannot be read as
    softening the Layer 2.5 ASCII gate.
    """
    return (
        f"Repository language policy (sourced from .github/CODEOWNERS "
        f"primary owner {owner} -> .github/owners.yaml). While in plan "
        f"mode, you MUST write plan files at /root/.claude/plans/*.md "
        f"AND chat responses in language code '{iso}'; this SessionStart "
        f"injection is the authoritative source and MUST NOT be "
        f"overridden by an English default. If you draft any portion in "
        f"another language, STOP and re-emit in '{iso}' -- drift is a "
        f"defect, not a style choice. Exception: GitHub posts created "
        f"via mcp__github__* write tools (issues, PRs, comments, "
        f"reviews) MUST remain ASCII/English -- "
        f"scripts/preflight_non_ascii.py (Layer 2.5) will deny "
        f"non-ASCII bodies there. Code identifiers, file paths, and "
        f"command output stay in their source form."
    )


def decide(
    codeowners_text: str, owners_yaml_text: str
) -> dict[str, Any] | None:
    """Return the SessionStart hook output dict, or ``None`` to no-op.

    Order:
      1. No primary owner -> None (CODEOWNERS empty or unreadable upstream).
      2. Owner not mapped in owners.yaml -> None (operator hasn't opted in).
      3. Otherwise -> hookSpecificOutput dict with additionalContext.
    """
    owner, iso = resolve_language(codeowners_text, owners_yaml_text)
    if owner is None or iso is None:
        return None
    return {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": build_context_message(owner, iso),
        }
    }


# ---------------------------------------------------------------------------
# Side-effecting boundary -- the only impure surface, monkeypatched in tests
# ---------------------------------------------------------------------------


def _project_root() -> Path:
    """Resolve the repo root, preferring the harness-supplied env var."""
    root = os.environ.get("CLAUDE_PROJECT_DIR")
    return Path(root) if root else Path.cwd()


def main(argv: list[str] | None = None) -> int:
    """Read project files, write SessionStart decision JSON to stdout.

    Fails open per CLAUDE.md Sec.4: any OSError, YAML error, or import
    failure emits ``::error::...`` to stderr and exits 0 with empty
    stdout. A hook bug must not block session start; the absence of
    additionalContext degrades to the pre-existing English default.
    """
    del argv  # not used; SessionStart events have no actionable stdin
    root = _project_root()
    try:
        codeowners_text = (root / _CODEOWNERS_PATH).read_text(encoding="utf-8")
        owners_yaml_text = (root / _OWNERS_YAML_PATH).read_text(encoding="utf-8")
    except OSError as exc:
        print(
            f"::error::plan_language_context: cannot read config: {exc}",
            file=sys.stderr,
        )
        return 0

    try:
        import yaml
    except ImportError as exc:
        print(
            f"::error::plan_language_context: PyYAML not installed: {exc}",
            file=sys.stderr,
        )
        return 0

    try:
        decision = decide(codeowners_text, owners_yaml_text)
    except (yaml.YAMLError, ValueError) as exc:
        print(
            f"::error::plan_language_context: cannot parse owners.yaml: {exc}",
            file=sys.stderr,
        )
        return 0

    if decision is None:
        return 0

    sys.stdout.write(json.dumps(decision))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
