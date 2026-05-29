#!/usr/bin/env python3
"""Verify repository-local Markdown links resolve without network access.

Refs #202. This gate checks the documentation surface that contributors
read most often and intentionally avoids external URL fetching so PR
verification remains deterministic. It verifies local Markdown links,
image targets, and heading fragments; HTTP(S), mailto, and template
placeholders are outside this first-pass gate.
"""

from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlsplit

REPO_ROOT = Path(__file__).resolve().parent.parent

DOC_GLOBS = (
    "*.md",
    "docs/INDEX.md",
    "docs/agent-provenance.md",
    "docs/runbooks/**/*.md",
    "docs/standards/**/*.md",
    ".github/*.md",
)

INLINE_LINK_RE = re.compile(r"!?\[[^\]\n]*\]\(([^)\n]+)\)")
REFERENCE_LINK_RE = re.compile(r"^\s{0,3}\[[^\]\n]+\]:\s+(\S+)", re.MULTILINE)
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
LINE_FRAGMENT_RE = re.compile(r"^L\d+(?:-L\d+)?$")
IGNORED_SCHEMES = frozenset({"http", "https", "mailto", "tel", "data"})
IGNORED_TARGETS = frozenset({"agent-session-url", "agent/session URL"})


@dataclass(frozen=True)
class MarkdownLink:
    """One Markdown link target found in a source file."""

    source: Path
    line: int
    target: str


def rel(path: Path, root: Path) -> str:
    """Return a stable repository-relative path string."""
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def iter_markdown_files(root: Path) -> list[Path]:
    """Return documentation Markdown files covered by the gate."""
    files: set[Path] = set()
    for pattern in DOC_GLOBS:
        files.update(path for path in root.glob(pattern) if path.is_file())
    return sorted(files)


def extract_target(raw: str) -> str:
    """Return the URL/path part of a Markdown link target."""
    target = raw.strip()
    if target.startswith("<") and ">" in target:
        return target[1 : target.index(">")]
    if " " in target:
        return target.split(" ", 1)[0]
    return target


def iter_links(path: Path) -> list[MarkdownLink]:
    """Return Markdown links found in *path* with source line numbers."""
    text = path.read_text(encoding="utf-8")
    links: list[MarkdownLink] = []
    for pattern in (INLINE_LINK_RE, REFERENCE_LINK_RE):
        for match in pattern.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            links.append(MarkdownLink(source=path, line=line, target=extract_target(match.group(1))))
    return links


def strip_inline_markdown(text: str) -> str:
    """Return heading text with common inline Markdown syntax removed."""
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = text.replace("*", "").replace("_", "").strip()
    return text


def slugify_heading(text: str) -> str:
    """Return the GitHub-style heading slug used by Markdown fragments."""
    text = strip_inline_markdown(text).lower()
    chars: list[str] = []
    for char in unicodedata.normalize("NFKC", text):
        category = unicodedata.category(char)
        if category[0] in {"L", "N"} or char in {" ", "-"}:
            chars.append(char)
    slug = "".join(chars).strip()
    slug = re.sub(r"\s", "-", slug)
    return slug


def collect_anchors(path: Path) -> set[str]:
    """Return GitHub-style heading anchors available in *path*."""
    anchors: set[str] = set()
    counts: dict[str, int] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = HEADING_RE.match(line)
        if not match:
            continue
        base = slugify_heading(match.group(2))
        if not base:
            continue
        seen = counts.get(base, 0)
        counts[base] = seen + 1
        anchors.add(base if seen == 0 else f"{base}-{seen}")
    return anchors


def should_skip_target(target: str) -> bool:
    """Return True for external URLs and intentional template placeholders."""
    if not target or target in IGNORED_TARGETS:
        return True
    parts = urlsplit(target)
    return parts.scheme in IGNORED_SCHEMES or target.startswith("//")


def resolve_link(link: MarkdownLink, root: Path) -> tuple[Path, str]:
    """Return the target path and fragment for a local Markdown link."""
    parts = urlsplit(link.target)
    raw_path = unquote(parts.path)
    fragment = unquote(parts.fragment)
    if raw_path in {"", "."}:
        return link.source, fragment
    if Path(raw_path).is_absolute():
        target_path = root / raw_path.lstrip("/")
    else:
        target_path = link.source.parent / raw_path
    return target_path.resolve(), fragment


def verify_link(link: MarkdownLink, root: Path) -> str | None:
    """Return a diagnostic for *link*, or None when it passes."""
    if should_skip_target(link.target):
        return None

    target_path, fragment = resolve_link(link, root)
    if root.resolve() not in (target_path, *target_path.parents):
        return f"{rel(link.source, root)}:{link.line}: local link escapes repository: {link.target}"
    if not target_path.exists():
        return f"{rel(link.source, root)}:{link.line}: missing local link target: {link.target}"
    if not fragment:
        return None
    if LINE_FRAGMENT_RE.match(fragment):
        return None
    if target_path.suffix.lower() != ".md":
        return f"{rel(link.source, root)}:{link.line}: fragment on non-Markdown target: {link.target}"

    anchors = collect_anchors(target_path)
    if fragment.lower() not in anchors:
        return f"{rel(link.source, root)}:{link.line}: missing heading fragment: {link.target}"
    return None


def verify(root: Path) -> list[str]:
    """Return all local Markdown link errors under *root*."""
    errors: list[str] = []
    for path in iter_markdown_files(root):
        for link in iter_links(path):
            error = verify_link(link, root)
            if error is not None:
                errors.append(error)
    return errors


def cmd_verify(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    errors = verify(root)
    for error in errors:
        print(f"::error::{error}", file=sys.stderr)
    if errors:
        return 1
    print("OK: repository-local Markdown links resolve.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(REPO_ROOT), help="Repository root to scan.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    verify_parser = subparsers.add_parser("verify", help="Verify local Markdown links.")
    verify_parser.set_defaults(func=cmd_verify)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
