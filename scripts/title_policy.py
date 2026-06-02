#!/usr/bin/env python3
"""Validate issue and PR titles before they enter repository metadata.

The workflow ``.github/workflows/verify-title-policy.yml`` calls this
module for issue and pull request title checks. Title text is header-level
metadata: it appears in notifications, project lists, triage queues, and
agent summaries before body context is inspected. Keep it ASCII-only so
zero-width marks, RTL controls, emoji, Japanese text, and homoglyphs are
rejected at the boundary.

Contract:
- Inputs: the ``verify`` subcommand; ``--kind`` (``issue`` or ``pr``);
  the title from ``--title`` or the ``TITLE`` env var; the naming policy
  from ``.github/title-policy.toml``; PR/issue body text from ``PR_BODY``
  / ``ISSUE_BODY`` for the issue-reference check.
- Outputs: ``::error::`` annotations naming each violation on stdout;
  exit 0 when the title passes, exit 1 otherwise.
- Failure policy: fails loud per CLAUDE.md section 4 (gate: a malformed
  or policy-violating title exits non-zero).

Tracked by #155.
"""

from __future__ import annotations

import argparse
import os
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

from _trusted_bots import _TRUSTED_BOT_LOGINS

_DEFAULT_MAX_FINDINGS = 10
TITLE_POLICY_CONFIG = Path(__file__).resolve().parents[1] / ".github" / "title-policy.toml"


def _load_title_policy_config(path: Path = TITLE_POLICY_CONFIG) -> tuple[tuple[str, ...], str]:
    with path.open("rb") as fp:
        data = tomllib.load(fp)
    policy = data.get("title_policy")
    if not isinstance(policy, dict):
        raise ValueError(f"missing [title_policy] table in {path}")

    types = policy.get("types")
    if (
        not isinstance(types, list)
        or not types
        or any(not isinstance(item, str) or not item for item in types)
    ):
        raise ValueError(f"{path} [title_policy].types must be a non-empty string list")

    scope_pattern = policy.get("scope_pattern")
    if not isinstance(scope_pattern, str) or not scope_pattern:
        raise ValueError(f"{path} [title_policy].scope_pattern must be a non-empty string")

    re.compile(scope_pattern)
    return tuple(types), scope_pattern


_CONVENTIONAL_TYPES, _SCOPE_PATTERN = _load_title_policy_config()
_TYPE_PATTERN = "|".join(re.escape(item) for item in _CONVENTIONAL_TYPES)
_CONVENTIONAL_TITLE_RE = re.compile(rf"^(?:{_TYPE_PATTERN})(?:\({_SCOPE_PATTERN}\))?: .+")
# Per #167 and #214, PR subject lines must not carry issue refs like (#NNN);
# `.github/workflows/verify-issue-link.yml` already validates `Refs #NNN` in
# the PR body, so the title is redundant when it duplicates that link.
_PR_ISSUE_REF_RE = re.compile(r"\(#\d+\)")
_TITLE_PARTS_RE = re.compile(
    rf"^(?P<type>{_TYPE_PATTERN})(?:\((?P<scope>{_SCOPE_PATTERN})\))?: (?P<summary>.+)"
)

_PERFORMANCE_TERMS = frozenset(
    {
        "cache",
        "caching",
        "faster",
        "latency",
        "memory",
        "performance",
        "resource",
        "speed",
        "startup",
        "throughput",
    }
)
_PERFORMANCE_PHRASES = (
    "build cache",
    "cache image",
    "cache images",
    "image build cache",
    "prebuilt image",
    "prebuilt images",
    "reduce runtime",
    "speed up",
)
_PERF_ADJACENT_ALLOWED_TYPES = frozenset({"build", "ci", "docs", "perf", "test"})
_PERF_FIX_TERMS = frozenset({"bug", "defect", "error", "fail", "failure", "regression"})
_CI_INFRA_TERMS = frozenset({"action", "actions", "ci", "gate", "workflow", "workflows"})
_BUILD_INFRA_TERMS = frozenset({"build", "container", "image", "images", "package", "publish"})


@dataclass(frozen=True)
class TitleParts:
    """Parsed conventional title fields."""

    type: str
    scope: str
    summary: str


@dataclass(frozen=True)
class TypeFitFinding:
    """A high-confidence title type mismatch."""

    reason: str
    expected_types: tuple[str, ...]


def is_ascii_title(title: str) -> bool:
    """Return True if *title* contains only ASCII code points."""
    return title.isascii()


def follows_naming_convention(title: str, *, kind: str) -> bool:
    """Return True if *title* follows this repo's title convention."""
    if kind in {"issue", "pull_request"}:
        return _CONVENTIONAL_TITLE_RE.fullmatch(title) is not None
    raise ValueError(f"unsupported title kind: {kind!r}")


def parse_title_parts(title: str) -> TitleParts | None:
    """Return conventional title parts, or ``None`` when shape is invalid."""
    match = _TITLE_PARTS_RE.fullmatch(title)
    if match is None:
        return None
    return TitleParts(
        type=match.group("type"),
        scope=match.group("scope") or "",
        summary=match.group("summary"),
    )


def pr_title_has_issue_ref(title: str) -> bool:
    """Return True if *title* contains a `(#NNN)` issue-ref token."""
    return _PR_ISSUE_REF_RE.search(title) is not None


def pr_title_issue_refs(title: str) -> list[str]:
    """Return every ``(#NNN)`` token in *title* in source order.

    Empty list when *title* carries no issue-reference token. Pairs with
    :func:`pr_title_has_issue_ref` so client-side preflights can list
    the offending tokens without re-implementing the regex.
    """
    return _PR_ISSUE_REF_RE.findall(title)


def pr_title_strip_issue_refs(title: str) -> str:
    """Return *title* with every ``(#NNN)`` token removed and whitespace collapsed."""
    stripped = _PR_ISSUE_REF_RE.sub("", title)
    return re.sub(r"\s+", " ", stripped).strip()


def allowed_types_csv() -> str:
    """Return the allowed conventional-commit types as a CSV string.

    Single source for operator-facing hint text so client-side preflight
    hooks and any future error messages cannot drift from
    ``_CONVENTIONAL_TYPES``.
    """
    return ", ".join(_CONVENTIONAL_TYPES)


def type_fit_findings(title: str, *, kind: str, body: str = "") -> list[TypeFitFinding]:
    """Return high-confidence type/title mismatches.

    This is intentionally conservative: it only rejects cases where the
    title/body vocabulary strongly points at a better type. Ambiguous
    maintenance work still passes and should be handled in review.
    """
    if kind not in {"issue", "pull_request"}:
        raise ValueError(f"unsupported title kind: {kind!r}")
    parts = parse_title_parts(title)
    if parts is None:
        return []

    text = _normalized_policy_text(title, body)
    findings: list[TypeFitFinding] = []
    if _has_performance_signal(text):
        findings.extend(_performance_type_findings(parts, text))
    return findings


def format_type_fit_finding(finding: TypeFitFinding) -> str:
    """Return a concise human-facing explanation for a type-fit finding."""
    expected = ", ".join(finding.expected_types)
    return f"{finding.reason} Expected title type: {expected}."


def naming_convention_hint(kind: str) -> str:
    """Return the operator-facing expected title shape for *kind*."""
    if kind in {"issue", "pull_request"}:
        return "`type(scope): summary`"
    raise ValueError(f"unsupported title kind: {kind!r}")


def describe_non_ascii(title: str, limit: int = _DEFAULT_MAX_FINDINGS) -> list[str]:
    """Return human-readable descriptions of non-ASCII code points."""
    findings: list[str] = []
    for index, char in enumerate(title):
        if char.isascii():
            continue
        findings.append(f"index {index}: U+{ord(char):04X}")
        if len(findings) >= limit:
            break
    return findings


def verify_title(title: str, *, kind: str, body: str = "", author: str = "") -> int:
    """Print a GitHub Actions annotation and return a process exit code.

    When *author* is a trusted bot (``_trusted_bots._TRUSTED_BOT_LOGINS``),
    the body is dropped from the type-fit heuristic (#1127): a dependabot PR
    relays upstream release notes whose ``cache`` / ``memory`` wording would
    otherwise mis-classify a correct ``chore(deps):`` title as performance
    work. The title-only checks (ASCII, naming convention, issue-ref) still
    apply to every author including bots.
    """
    fail = 0
    if not is_ascii_title(title):
        details = ", ".join(describe_non_ascii(title))
        if details:
            details = f" Non-ASCII code points: {details}."
        print(f"::error::{kind} title must be ASCII-only for prompt-injection " f"defense.{details}")
        fail = 1

    if not follows_naming_convention(title, kind=kind):
        print(f"::error::{kind} title must follow repository naming convention: " f"{naming_convention_hint(kind)}.")
        fail = 1
    else:
        policy_body = "" if _is_trusted_bot_author(author) else (body or _body_from_env())
        for finding in type_fit_findings(title, kind=kind, body=policy_body):
            print(f"::error::{kind} title type does not fit the work: {format_type_fit_finding(finding)}")
            fail = 1

    if kind == "pull_request" and pr_title_has_issue_ref(title):
        print(
            "::error::pull_request title must not contain issue references "
            "like (#NNN). Put `Refs #NNN` in the PR body instead. See #167."
        )
        fail = 1

    if fail:
        return 1

    print(f"OK: {kind} title is ASCII-only and follows naming convention.")
    return 0


def _normalized_policy_text(title: str, body: str) -> str:
    text = f"{title}\n{body}".lower()
    return re.sub(r"[^a-z0-9#+.-]+", " ", text)


def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9][a-z0-9+-]*", text))


def _has_performance_signal(text: str) -> bool:
    words = _words(text)
    return bool(words & _PERFORMANCE_TERMS) or any(phrase in text for phrase in _PERFORMANCE_PHRASES)


def _performance_type_findings(parts: TitleParts, text: str) -> list[TypeFitFinding]:
    words = _words(text)
    if parts.type == "perf":
        return []
    if parts.type in {"docs", "test"}:
        return []
    if parts.type == "ci" and words & _CI_INFRA_TERMS:
        return []
    if parts.type == "build" and words & _BUILD_INFRA_TERMS:
        return []
    if parts.type == "fix" and words & _PERF_FIX_TERMS:
        return []
    if parts.type == "feat" and ("benchmark" in words or "metrics" in words):
        return []
    return [
        TypeFitFinding(
            reason=(
                "performance, cache, latency, throughput, startup, memory, or resource wording "
                "is high-confidence performance work"
            ),
            expected_types=tuple(sorted(_PERF_ADJACENT_ALLOWED_TYPES)),
        )
    ]


def _body_from_env() -> str:
    return os.environ.get("PR_BODY") or os.environ.get("ISSUE_BODY") or ""


def _author_from_env() -> str:
    return os.environ.get("PR_AUTHOR") or ""


def _is_trusted_bot_author(author: str) -> bool:
    return bool(author) and author in _TRUSTED_BOT_LOGINS


def _cmd_verify(args: argparse.Namespace) -> int:
    title = args.title
    if title is None:
        title = os.environ.get("TITLE", "")
    body = _read_body_arg(args)
    author = args.author if args.author is not None else _author_from_env()
    return verify_title(title, kind=args.kind, body=body or "", author=author)


def _read_body_arg(args: argparse.Namespace) -> str | None:
    if args.body_file:
        return Path(args.body_file).read_text()
    if args.body is not None:
        return args.body
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_verify = sub.add_parser(
        "verify",
        help="Verify a title is ASCII-only.",
    )
    p_verify.add_argument(
        "--kind",
        choices=("issue", "pull_request"),
        required=True,
        help="GitHub event object kind being validated.",
    )
    p_verify.add_argument(
        "--title",
        help="Title to validate. Defaults to the TITLE environment variable.",
    )
    p_verify.add_argument(
        "--body",
        help="Optional issue or PR body used for conservative type-fit checks.",
    )
    p_verify.add_argument(
        "--body-file",
        help="Optional file containing the issue or PR body used for type-fit checks.",
    )
    p_verify.add_argument(
        "--author",
        help=(
            "Optional PR/issue author login. Defaults to the PR_AUTHOR env var. "
            "A trusted-bot author drops the body from the type-fit heuristic."
        ),
    )
    p_verify.set_defaults(func=_cmd_verify)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
