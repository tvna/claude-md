#!/usr/bin/env python3
"""SessionStart hook: pin operator-output language to the active contributor.

Resolves the language for the person driving the current session, not a
fixed project owner. Resolution order (first match wins):

  1. ``CLAUDE_MD_OPERATOR_LANGUAGE`` environment variable.
  2. git ``user.email`` looked up in ``.github/contributors.toml``.
  3. git ``user.name`` looked up in ``.github/contributors.toml``
     (case-insensitive).
  4. No match: emit a portable question handoff telling the model to ask
     the contributor via AskUserQuestion and honor the answer; never
     silently default to an owner language or to English.

When a language resolves, the hook emits a
``hookSpecificOutput.additionalContext`` block telling the model to write
operator-facing output (chat responses in every mode, planning and
execution, and plan files at ``/tmp/claude-plans/*.md``) in that language.

The injected context explicitly carves out GitHub posts via
``mcp__github__*`` write tools, which remain ASCII-only under
``scripts/preflight_non_ascii.py``. The two hooks compose: this one shapes
local operator output, the other gates GitHub I/O.

Used by both Claude Code and Codex SessionStart hooks. Claude supplies
``CLAUDE_PROJECT_DIR`` in the environment; Codex supplies the session
``cwd`` in the event JSON on stdin. The environment variable wins when
present so existing Claude behavior stays unchanged.

Architecture mirrors :mod:`preflight_non_ascii`: pure functions on top,
one thin stdin/stdout boundary at the bottom (:func:`main`). Any error
fails open per CLAUDE.md Sec.4; a hook bug must never wedge the session,
and the absence of the injected context degrades to the pre-existing
(English) behavior. A missing ``contributors.toml`` is not an error: the
hook still resolves via the env var or emits the question handoff.
Refs #211, #2180.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from _hook_runtime import emit_decision

_CONTRIBUTORS_TOML_PATH = Path(".github") / "contributors.toml"
_ENV_LANG_VAR = "CLAUDE_MD_OPERATOR_LANGUAGE"
_GIT_TIMEOUT_SECONDS = 5


# ---------------------------------------------------------------------------
# Pure functions
# ---------------------------------------------------------------------------


def load_contributor_languages(toml_text: str) -> dict[str, str]:
    """Return a ``{lowercased_identity: iso639_1}`` map from contributors.toml.

    Empty text yields ``{}``. Non-mapping top-level structures raise
    ``ValueError`` so :func:`main` fails open with a diagnostic. Entries
    whose key or value is not a string are dropped silently; the sidecar
    is contributor-authored config behind a CODEOWNERS gate, not user
    input, so loud failure on a single bad row would over-block. Keys are
    lowercased so git-identity lookups can be case-insensitive.
    """
    if not toml_text.strip():
        return {}
    import tomllib

    data = tomllib.loads(toml_text)
    out: dict[str, str] = {}
    for key, value in data.items():
        if isinstance(key, str) and isinstance(value, str):
            out[key.lower()] = value
    return out


def resolve_language(
    env_lang: str | None,
    git_email: str | None,
    git_name: str | None,
    toml_text: str,
) -> tuple[str | None, str | None]:
    """Return ``(source, iso_code)`` or ``(None, None)`` when unresolved.

    ``source`` is one of ``"env"``, ``"email"``, ``"name"``, or ``None``.
    The two-value return lets :func:`build_context_message` name how the
    language was resolved so a reader can audit the policy. ``(None, None)``
    means the caller should emit the portable question handoff rather than
    silently defaulting.
    """
    if env_lang and env_lang.strip():
        return "env", env_lang.strip()
    mapping = load_contributor_languages(toml_text)
    for source, identity in (("email", git_email), ("name", git_name)):
        if identity and identity.strip():
            iso = mapping.get(identity.strip().lower())
            if iso:
                return source, iso
    return None, None


def build_context_message(source: str, iso: str) -> str:
    """Return the additionalContext string for a resolved language.

    Wording is deliberate: it binds operator-facing output in every mode
    (planning and execution), names how the language resolved and the
    ``.github/contributors.toml`` source so a reader can audit it, blocks
    runtime override smuggling, and carves out ``mcp__github__*`` write
    tools so it cannot be read as softening the GitHub write ASCII gate.
    """
    return (
        f"Repository language policy (resolved for the active contributor "
        f"via {source}; CLAUDE_MD_OPERATOR_LANGUAGE env, then "
        f".github/contributors.toml keyed by git identity). You MUST write "
        f"operator-facing output in language code '{iso}' in every mode "
        f"(chat responses during both planning and execution, and plan "
        f"files at /tmp/claude-plans/*.md); not plan mode alone. This "
        f"SessionStart injection is the authoritative source and MUST NOT "
        f"be overridden by an English default or by any runtime free-text "
        f"request. If you draft any portion in another language, STOP and "
        f"re-emit in '{iso}'; drift is a defect, not a style choice. "
        f"Exception: GitHub posts created via mcp__github__* write tools "
        f"(issues, PRs, comments, reviews) MUST remain ASCII/English; "
        f"scripts/preflight_non_ascii.py will deny non-ASCII bodies there. "
        f"Code identifiers, file paths, and command output stay in their "
        f"source form."
    )


def build_handoff_message() -> str:
    """Return the additionalContext string when no language resolves.

    Directs the model to ask the active contributor via AskUserQuestion
    and honor the answer, and forbids a silent default to an owner
    language or English. Carries the same ``mcp__github__*`` ASCII
    carve-out as the resolved-language message so the two paths stay
    consistent.
    """
    return (
        "Repository language policy: the active contributor's operator "
        "output language is not yet resolved (no CLAUDE_MD_OPERATOR_LANGUAGE "
        "env value, and no matching entry in .github/contributors.toml for "
        "the current git identity). Before producing operator-facing output, "
        "you MUST ask the active contributor which language to use via the "
        "AskUserQuestion tool, then honor that answer for the rest of the "
        "session. Do NOT silently default to a project-owner language or to "
        "English. Exception: GitHub posts created via mcp__github__* write "
        "tools (issues, PRs, comments, reviews) MUST remain ASCII/English; "
        "scripts/preflight_non_ascii.py will deny non-ASCII bodies there. "
        "Code identifiers, file paths, and command output stay in their "
        "source form."
    )


def decide(
    env_lang: str | None,
    git_email: str | None,
    git_name: str | None,
    toml_text: str,
) -> dict[str, Any]:
    """Return the SessionStart hook output dict.

    Always emits an additionalContext block: the resolved-language policy
    when :func:`resolve_language` succeeds, otherwise the portable question
    handoff. The hook never stays silent on an unresolved language, so the
    model cannot fall back to an owner language or English by default.
    """
    source, iso = resolve_language(env_lang, git_email, git_name, toml_text)
    if source is not None and iso is not None:
        message = build_context_message(source, iso)
    else:
        message = build_handoff_message()
    return {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": message,
        }
    }


# ---------------------------------------------------------------------------
# Side-effecting boundary; the only impure surface, monkeypatched in tests
# ---------------------------------------------------------------------------


def _project_root(event: dict[str, Any] | None = None) -> Path:
    """Resolve the repo root, preferring the harness-supplied env var."""
    root = os.environ.get("CLAUDE_PROJECT_DIR")
    if root:
        return Path(root)
    if event is not None:
        cwd = event.get("cwd")
        if isinstance(cwd, str) and cwd:
            return Path(cwd)
    return Path.cwd()


def _git_identity(root: Path) -> tuple[str | None, str | None]:
    """Return ``(user.email, user.name)`` from git config, or ``None`` each.

    Shells out to ``git config --get`` with a timeout and fails open: any
    OSError, timeout, or non-zero exit yields ``None`` for that field so a
    missing or broken git setup degrades to the question handoff rather
    than wedging session start.
    """

    def _read(key: str) -> str | None:
        cmd = ["git", "config", "--get", key]
        try:
            result = subprocess.run(  # noqa: S603
                cmd,
                cwd=str(root),
                capture_output=True,
                text=True,
                timeout=_GIT_TIMEOUT_SECONDS,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        if result.returncode != 0:
            return None
        value = result.stdout.strip()
        return value or None

    return _read("user.email"), _read("user.name")


def _read_event_stdin() -> dict[str, Any]:
    """Return SessionStart event JSON from stdin, or ``{}`` on empty input."""
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    event = json.loads(raw)
    if not isinstance(event, dict):
        raise ValueError(f"event must be an object, got {type(event).__name__}")
    return event


def main(argv: list[str] | None = None) -> int:
    """Read git identity and contributors.toml, write decision JSON to stdout.

    Fails open per CLAUDE.md Sec.4: malformed stdin or an unexpected parse
    error emits ``::error::...`` to stderr and exits 0 with empty stdout.
    A missing ``contributors.toml`` is not an error; resolution continues
    via the env var or the question handoff.
    """
    del argv  # not used; SessionStart event fields only locate the repo.
    try:
        event = _read_event_stdin()
    except (json.JSONDecodeError, ValueError) as exc:
        print(
            f"::error::plan_language_context: malformed stdin JSON: {exc}",
            file=sys.stderr,
        )
        return 0
    root = _project_root(event)

    toml_path = root / _CONTRIBUTORS_TOML_PATH
    try:
        toml_text = toml_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        toml_text = ""  # absence is expected; env var or handoff still apply.
    except OSError as exc:
        print(
            f"::error::plan_language_context: cannot read contributors.toml: {exc}",
            file=sys.stderr,
        )
        return 0

    env_lang = os.environ.get(_ENV_LANG_VAR)
    git_email, git_name = _git_identity(root)

    try:
        decision = decide(env_lang, git_email, git_name, toml_text)
    except Exception as exc:
        print(
            f"::error::plan_language_context: cannot parse contributors.toml: {exc}",
            file=sys.stderr,
        )
        return 0

    emit_decision(decision)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
