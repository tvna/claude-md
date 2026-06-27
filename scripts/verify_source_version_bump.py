#!/usr/bin/env python3
"""Bidirectional drift gate: universal text changes iff apm.yml version bumps.

Issue #89; design record ``docs/prd/semantic-versioning-universal-text.md``
(requirement R4). The universal text - ``.apm/instructions/master.instructions.md``
and the compiled ``CLAUDE.md`` / ``AGENTS.md`` (see
``docs/standards/ubiquitous-language.md``, term "universal text") - is
semantically versioned through ``apm.yml: version``. The core invariant:

    The universal text changes if and only if ``apm.yml: version`` is bumped,
    and the bump component matches the declared ``semver:*`` label.

This gate forbids a one-sided update of the
{universal text, ``apm.yml: version``} pair in either direction. On every PR:

* universal-text-touching but version not bumped -> fail (drift);
* version bumped but not universal-text-touching -> fail (drift);
* both change together ->
  - exactly one ``semver:*`` label present (else fail), and
  - new version strictly greater than base, a clean single-component bump
    (else fail), and
  - the bumped component equals the label (else fail).

Labels live in repository state, not git, so they are read only at PR time.
When labels are unavailable (the pre-push mirror in ``scripts/preflight_all.py``
cannot see them) the caller passes ``labels=None``; the gate then keeps the
text-vs-version iff and the clean-bump check and skips only the label-match.

Architecture mirrors ``scripts/verify_text_delta_section.py``: pure functions
on top, one thin :func:`_run` subprocess boundary at the bottom that tests
monkeypatch via the ``runner`` kwarg. ``apm.yml`` content is read at the base
and head refs via ``git show``; the changed-file list via ``git diff
--name-only``.

Contract:
    Inputs: the ``verify`` subcommand; ``--base-ref`` (falls back to
        ``BASE_REF``, then ``origin/$GITHUB_BASE_REF``, then ``origin/main``);
        ``--head`` (default ``HEAD``); ``--labels`` (comma-separated, falls
        back to the ``PR_LABELS`` env var; absent entirely -> labels unknown,
        label-match skipped). No stdin.
    Outputs: ``::error file=apm.yml::`` annotations on stdout naming each
        violation; an ``OK:`` line on the happy path; exit 0 when the
        invariant holds (including the clean no-op), exit 1 otherwise.
    Failure policy: fails loud per CLAUDE.md section 4 (no silent default).

Tested by ``tests/test_verify_source_version_bump.py`` per
``docs/standards/workflow-script-quality.md``. Refs #89.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys

_GIT_TIMEOUT_SECONDS: int = 15

# R3: the universal-text change set is exactly these three files. A
# dependency-driven recompile that changes a compiled body touches one of
# CLAUDE.md / AGENTS.md and is caught the same way.
_UNIVERSAL_TEXT_FILES: frozenset[str] = frozenset({
    ".apm/instructions/master.instructions.md",
    "CLAUDE.md",
    "AGENTS.md",
})

_APM_FILE = "apm.yml"

# Canonical semver version line in apm.yml: ``version: 1.0.0``. Anchored,
# no nested quantifiers (ReDoS-safe).
_VERSION_RE = re.compile(r"^version:\s*(\d+)\.(\d+)\.(\d+)\s*$", re.MULTILINE)

_SEMVER_LABEL_PREFIX = "semver:"
_SEMVER_COMPONENTS: frozenset[str] = frozenset({"major", "minor", "patch"})

Version = tuple[int, int, int]


def parse_version(apm_yaml_text: str) -> Version:
    """Return ``(major, minor, patch)`` parsed from ``apm.yml`` content.

    Reads the first ``version: X.Y.Z`` line. Raises :class:`ValueError`
    when no well-formed version line is present so the caller fails loud
    rather than defaulting silently (CLAUDE.md section 4).
    """
    match = _VERSION_RE.search(apm_yaml_text)
    if match is None:
        raise ValueError(
            "no well-formed 'version: X.Y.Z' line found in apm.yml"
        )
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)))


def format_version(version: Version) -> str:
    """Return the dotted string form of a parsed version tuple."""
    return ".".join(str(part) for part in version)


def is_universal_text_path(path: str) -> bool:
    """Return True when *path* is one of the R3 universal-text files."""
    return path.strip() in _UNIVERSAL_TEXT_FILES


def touches_universal_text(changed_paths: frozenset[str]) -> bool:
    """Return True when any changed path is universal text (R3)."""
    return any(is_universal_text_path(path) for path in changed_paths)


def bump_component(base: Version, head: Version) -> str | None:
    """Return the single semver component bumped from *base* to *head*.

    A valid bump is strictly greater than the base and changes exactly one
    component, resetting every lower-order component to zero (the
    conventional semver increment):

    * major: ``(M+1, 0, 0)`` for any ``M+1 > base.major``;
    * minor: ``(M, m', 0)`` for ``m' > base.minor``;
    * patch: ``(M, m, p')`` for ``p' > base.patch``.

    Returns the component name (``"major"`` / ``"minor"`` / ``"patch"``) on a
    clean bump, or ``None`` for any other transition (no change, a decrease,
    or a multi-component change such as ``1.2.3 -> 2.1.0``).
    """
    b_major, b_minor, b_patch = base
    h_major, h_minor, h_patch = head
    if h_major > b_major:
        return "major" if (h_minor == 0 and h_patch == 0) else None
    if h_major == b_major and h_minor > b_minor:
        return "minor" if h_patch == 0 else None
    if h_major == b_major and h_minor == b_minor and h_patch > b_patch:
        return "patch"
    return None


def extract_semver_labels(labels: list[str]) -> list[str]:
    """Return the semver components named by ``semver:*`` labels.

    ``["semver:minor", "type:feat"]`` -> ``["minor"]``. Only the three
    declared components (major/minor/patch) are recognised; an unknown
    ``semver:*`` value is ignored here and surfaces as a cardinality
    failure (zero recognised) in :func:`evaluate`. Order is preserved.
    """
    components: list[str] = []
    for label in labels:
        name = label.strip()
        if name.startswith(_SEMVER_LABEL_PREFIX):
            component = name[len(_SEMVER_LABEL_PREFIX):]
            if component in _SEMVER_COMPONENTS:
                components.append(component)
    return components


def evaluate(
    text_changed: bool,
    base_version: Version,
    head_version: Version,
    labels: list[str] | None,
) -> tuple[int, list[str]]:
    """Return ``(exit_code, error_lines)`` for the drift-gate decision.

    *labels* is the list of PR label names, or ``None`` when labels are
    unavailable (pre-push); ``None`` skips only the label-match check.
    """
    version_changed = base_version != head_version
    errors: list[str] = []

    if not text_changed and not version_changed:
        return 0, []

    if text_changed and not version_changed:
        return 1, [
            "::error file=apm.yml::This PR changes the universal text "
            "(.apm/instructions/master.instructions.md, CLAUDE.md, or "
            "AGENTS.md) but does not bump 'version' in apm.yml. Bump the "
            "version and add the matching semver:major|minor|patch label. "
            "See docs/prd/semantic-versioning-universal-text.md."
        ]

    if version_changed and not text_changed:
        return 1, [
            "::error file=apm.yml::This PR bumps 'version' in apm.yml "
            f"({format_version(base_version)} -> "
            f"{format_version(head_version)}) but changes none of the "
            "universal-text files. Either revert the version bump or include "
            "the universal-text change it describes. See "
            "docs/prd/semantic-versioning-universal-text.md."
        ]

    # Both changed: require a clean single-component bump.
    component = bump_component(base_version, head_version)
    if component is None:
        return 1, [
            "::error file=apm.yml::apm.yml version "
            f"{format_version(base_version)} -> "
            f"{format_version(head_version)} is not a clean single-component "
            "bump. Increment exactly one of major/minor/patch and reset the "
            "lower components to zero (e.g. 1.2.3 -> 1.3.0)."
        ]

    if labels is None:
        # Pre-push: labels not observable; keep the iff and clean-bump
        # checks, skip only the label-match.
        return 0, []

    components = extract_semver_labels(labels)
    if len(components) != 1:
        errors.append(
            "::error file=apm.yml::A universal-text PR must carry exactly one "
            f"semver:major|minor|patch label; found {len(components)} "
            f"({', '.join(components) if components else 'none'}). The label "
            f"must match the bumped component ('{component}')."
        )
        return 1, errors

    declared = components[0]
    if declared != component:
        errors.append(
            "::error file=apm.yml::The semver label declares "
            f"'{declared}' but apm.yml bumps the '{component}' component "
            f"({format_version(base_version)} -> "
            f"{format_version(head_version)}). Make the label and the bump "
            "agree."
        )
        return 1, errors

    return 0, []


def resolve_base() -> str:
    """Return the base ref the gate compares against.

    Resolution order: ``BASE_REF`` env, then ``origin/$GITHUB_BASE_REF``,
    then ``origin/main``. Empty values are treated as unset.
    """
    explicit = os.environ.get("BASE_REF")
    if explicit:
        return explicit
    actions_base = os.environ.get("GITHUB_BASE_REF")
    if actions_base:
        return f"origin/{actions_base}"
    return "origin/main"


def changed_files(
    base_ref: str, head: str = "HEAD", *, runner=subprocess.run
) -> frozenset[str]:
    """Return the file paths modified in ``{base}..{head}``."""
    result = _run(
        ["git", "diff", "--name-only", f"{base_ref}..{head}"], runner=runner
    )
    return frozenset(
        line.strip() for line in result.stdout.splitlines() if line.strip()
    )


def read_version_at(ref: str, *, runner=subprocess.run) -> Version:
    """Return the parsed apm.yml version at *ref* via ``git show``."""
    result = _run(["git", "show", f"{ref}:{_APM_FILE}"], runner=runner)
    return parse_version(result.stdout)


def _resolve_labels(args: argparse.Namespace) -> list[str] | None:
    """Return the PR label list, or ``None`` when labels are unavailable.

    A present-but-empty source (``--labels ''`` or ``PR_LABELS=``) means
    "labels known, none set" and yields ``[]`` (which fails the
    exactly-one check when both sides changed). Only a wholly absent
    source yields ``None`` (label-match skipped).
    """
    if args.labels is not None:
        return [item.strip() for item in args.labels.split(",") if item.strip()]
    if "PR_LABELS" in os.environ:
        raw = os.environ["PR_LABELS"]
        return [item.strip() for item in raw.split(",") if item.strip()]
    return None


def _cmd_verify(args: argparse.Namespace) -> int:
    base = args.base_ref or resolve_base()
    head = args.head
    labels = _resolve_labels(args)

    try:
        changed = changed_files(base, head)
        base_version = read_version_at(base)
        head_version = read_version_at(head)
    except (
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
        FileNotFoundError,
        RuntimeError,
        ValueError,
    ) as exc:
        print(
            "::error file=apm.yml::verify_source_version_bump: could not read "
            f"the version-bump inputs against base {base!r}: {exc}",
            file=sys.stderr,
        )
        return 1

    text_changed = touches_universal_text(changed)
    code, errors = evaluate(text_changed, base_version, head_version, labels)
    if code == 0:
        if text_changed:
            label_note = (
                "labels not checked (pre-push)"
                if labels is None
                else "label matches the bump"
            )
            print(
                "OK: universal text and apm.yml version bumped together "
                f"({format_version(base_version)} -> "
                f"{format_version(head_version)}); {label_note}."
            )
        else:
            print("OK: no universal text modified and no version bump.")
        return 0
    for line in errors:
        print(line)
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_verify = sub.add_parser(
        "verify",
        help=(
            "Verify the universal text and apm.yml version are bumped "
            "together with a matching semver label."
        ),
    )
    p_verify.add_argument(
        "--base-ref",
        help=(
            "Base ref to diff and read apm.yml against. Falls back to "
            "BASE_REF, then origin/$GITHUB_BASE_REF, then origin/main."
        ),
    )
    p_verify.add_argument(
        "--head",
        default="HEAD",
        help="Head ref to compare (default HEAD).",
    )
    p_verify.add_argument(
        "--labels",
        help=(
            "Comma-separated PR label names. Falls back to the PR_LABELS env "
            "var. Omit entirely (and unset PR_LABELS) to skip the label-match "
            "check, as the pre-push mirror does."
        ),
    )
    p_verify.set_defaults(func=_cmd_verify)

    args = parser.parse_args(argv)
    return args.func(args)


def _run(cmd: list[str], *, runner=subprocess.run):
    """Thin subprocess boundary; the only impure surface in this module.

    ``check=True`` raises ``CalledProcessError`` on non-zero exit; the
    caller translates that into the fail-loud ``::error::`` path. Tests
    monkeypatch ``runner`` to inject fake completed-process objects.
    """
    return runner(
        cmd,
        capture_output=True,
        text=True,
        timeout=_GIT_TIMEOUT_SECONDS,
        check=True,
    )


if __name__ == "__main__":
    raise SystemExit(main())
