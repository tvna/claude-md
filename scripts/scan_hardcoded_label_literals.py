#!/usr/bin/env python3
"""CI gate: reject hardcoded GitHub label literals in ``scripts/*.py``.

Phase 3 of the gitapex SSoT migration (docs/prd/gitapex-ssot-gate-registry.md):
phase 2 moved the at-risk label consumers off frozen label strings onto
registry resolution via ``scripts/_ssot.py``, but nothing prevents a new
hardcoded literal from reappearing. This gate is the anti-regression guard the
migration plan names ("a new hardcoded label literal in scripts/*.py fails
CI"), and it closes #1041 acceptance criterion 3 by generalizing it: any frozen
``family:name`` label literal outside the sanctioned single sources is drift,
whether the label is retired, renamed-away, or (per #1041 follow-up comment B)
never registered in the catalog at all.

What counts as a violation
--------------------------
A string *constant* whose ENTIRE value is a ``family:name`` label token, where
``family`` is a known label family (see :data:`KNOWN_FAMILIES`) and ``name`` is
a non-empty label-name segment. Matching the whole constant, not a substring,
is deliberate and gives the gate three properties for free:

- family-prefix reads such as ``label.startswith("severity:")`` are NOT
  flagged: ``"severity:"`` has no name segment after the colon, so it never
  matches ``family:name`` (this is the migration-safe pattern #1041 follow-up
  comment A points at, in ``scripts/dependabot_automerge.py``);
- GitHub search-query fragments (``" type:pr is:merged"``) and HTML markers
  (``"<!-- auto-retro:back-link -->"``) are substrings, not whole constants, so
  they never match;
- docstrings and prose that merely mention a label are never exactly one label
  token, so they are excluded without a special docstring pass.

Sanctioned homes (the allowlist)
--------------------------------
Two tiers, both rationale-carrying (mirroring the ``scan_preflight_drift`` /
``scan_ssot_drift`` allowlist idiom):

- :data:`SSOT_HOME_FILES`: files that are the definitional single source for
  label names, exempt wholesale (``scripts/_retro_labels.py`` is the retro:*
  SSoT; ``scripts/_ssot.py`` returns names read from the registry).
- :data:`LITERAL_ALLOWLIST`: specific pre-existing label constants in
  otherwise-scanned files, keyed by ``(path, literal)`` so ONLY those exact
  literals are exempt and a new or different literal in the same file is still
  rejected. Each entry carries its rationale, so the exception stays auditable.

Test files are out of scope by construction: the gate scans ``scripts/*.py``
only.

Contract:
- Inputs: the ``verify`` subcommand; ``--scripts-dir`` (default ``scripts``);
  ``--label-policy`` (default ``.github/label-policy.toml``, read only to
  cross-check the known-family set stays a superset of the governed families;
  a drift there is a hard error).
- Outputs: ``::error file=...,line=...::`` annotations on stderr, one per
  hardcoded literal; an ``OK:`` line on success.
- Failure policy: fails loud (exit 1) per CLAUDE.md section 4; it is a CI gate,
  so any hardcoded literal, an unparseable scripts/*.py, or a label-policy that
  declares a family the gate does not know about exits non-zero. Exit 64 on an
  unrecognised subcommand.

Tested by ``tests/test_scan_hardcoded_label_literals.py``. Refs #2299, #2298,
#2246, #1041.
"""

from __future__ import annotations

import argparse
import ast
import re
import subprocess
import sys
import tomllib
from pathlib import Path

_SCRIPT = "scan_hardcoded_label_literals"
_REPO_ROOT = Path(__file__).resolve().parent.parent
_SCRIPTS_DIR = "scripts"
_LABEL_POLICY_PATH = ".github/label-policy.toml"

# The known label families. The seven governed families come from
# ``.github/label-policy.toml`` ``[[families]]`` (layer, type, state, severity,
# area, ops, semver); ``retro`` is the runtime-only family defined in
# ``scripts/_retro_labels.py`` and deliberately absent from the catalog (#1041
# follow-up comment B). This tuple is hardcoded for a small, stable, governed
# set; ``tests/test_scan_hardcoded_label_literals.py`` asserts it stays a
# superset of the label-policy families, so adding a family to the policy
# without teaching this gate fails that test (the drift guard, shipped here).
KNOWN_FAMILIES: tuple[str, ...] = (
    "layer",
    "type",
    "state",
    "severity",
    "area",
    "ops",
    "semver",
    "retro",
)

# A string constant is a hardcoded label iff its WHOLE value matches this.
_LABEL_RE = re.compile(r"^(?:" + "|".join(KNOWN_FAMILIES) + r"):[A-Za-z0-9][A-Za-z0-9._-]*$")

# Files that are the sanctioned single source for label names. Any label
# literal in these is definitional, not drift, so the whole file is exempt.
SSOT_HOME_FILES: dict[str, str] = {
    "scripts/_retro_labels.py": (
        "The retro:* SSoT: the four retro classification labels are defined " "here and nowhere else (#558)."
    ),
    "scripts/_ssot.py": (
        "The .gitapex/ssot.json registry reader; the label names it returns "
        "are resolved from the registry, not frozen in this module (#2266)."
    ),
    "scripts/scan_hardcoded_label_literals.py": (
        "This gate's own LITERAL_ALLOWLIST necessarily enumerates the label "
        "literals it catalogs, so the file is a sanctioned home by construction "
        "(#2299)."
    ),
}

# Specific pre-existing label constants in otherwise-scanned files, keyed by
# (path, literal) so only these exact literals are exempt; a new or different
# literal in the same file is still rejected. Each entry carries its rationale.
#
# The first four are the migration-safe SSoT constant homes #1041's
# label-control inventory records ("Migration-safe today (keep labels or
# family-prefix matching)"): each label is defined once, in its owning module.
#
# The last two are consumers phase 2 did not migrate. They are exempted so the
# gate is green on the tree that introduces it (its job is anti-regression, not
# a same-PR migration), but NOT silently: each names the follow-up. In
# particular ``_security_drift_families.py`` still references the RETIRED
# ``layer:meta`` (exactly #1041 AC#3's target), but its successor (AC#2) is
# an undecided owner decision, so it is exempted pending that decision rather
# than hidden. Tracked under the phase-3 umbrella #2298.
LITERAL_ALLOWLIST: dict[tuple[str, str], str] = {
    ("scripts/_ref_classifier.py", "type:tracking"): (
        "SSoT constant for the tracking label (#1041 inventory: migration-safe "
        "today; type:tracking is a live catalog label)."
    ),
    ("scripts/scan_non_ascii.py", "severity:non-ascii-content"): (
        "SSoT constant for the non-ASCII content severity label (#1041 " "inventory: migration-safe today)."
    ),
    ("scripts/dependabot_automerge.py", "severity:non-ascii-content"): (
        "The one exact advisory-label constant; blocking labels are matched by "
        "family prefix (the migration-safe #1041 comment A pattern), so this is "
        "the only frozen literal here (#1041 inventory: migration-safe today)."
    ),
    ("scripts/threat_intel_triage.py", "severity:security"): (
        "SSoT constant for the security severity label (#1041 inventory: " "migration-safe today)."
    ),
    ("scripts/ci_budget_issue.py", "type:tracking"): (
        "Rolling CI-budget issue label constant; both labels are live. Phase 2 "
        "did not migrate this consumer to _ssot resolution; follow-up under "
        "#2298."
    ),
    ("scripts/ci_budget_issue.py", "layer:p3-harness"): (
        "Rolling CI-budget issue label constant; both labels are live. Phase 2 "
        "did not migrate this consumer to _ssot resolution; follow-up under "
        "#2298."
    ),
    ("scripts/_security_drift_families.py", "type:fix"): (
        "Per-family drift issue label constant; phase 2 did not migrate this "
        "consumer to _ssot resolution. Follow-up under #2298."
    ),
    ("scripts/_security_drift_families.py", "layer:meta"): (
        "RETIRED label still referenced by the security-drift meta-fix lane "
        "(exactly #1041 AC#3's target), but its successor (#1041 AC#2) is an "
        "undecided owner decision, so it is exempted pending that decision "
        "rather than hidden. Migrate and successor tracked under #2298; tighten "
        "this entry once the successor lands."
    ),
}


# ---------------------------------------------------------------------------
# Detection (pure functions over source text)
# ---------------------------------------------------------------------------


def iter_label_literals(source: str) -> list[tuple[int, str]]:
    """Return ``(lineno, literal)`` for every full-value label constant.

    Raises :class:`SyntaxError` when *source* does not parse; the caller turns
    that into a loud gate failure rather than skipping the file silently.
    """
    tree = ast.parse(source)
    hits: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and _LABEL_RE.match(node.value):
            hits.append((node.lineno, node.value))
    return hits


def is_allowlisted(path: str, literal: str) -> bool:
    """Return True when *literal* in *path* is a sanctioned label home."""
    return path in SSOT_HOME_FILES or (path, literal) in LITERAL_ALLOWLIST


def scan_file(path: str, source: str) -> list[str]:
    """Return ``::error::`` strings for non-allowlisted label literals in *path*."""
    if path in SSOT_HOME_FILES:
        return []  # whole-file sanctioned home; nothing to check
    try:
        hits = iter_label_literals(source)
    except SyntaxError as exc:
        return [f"::error file={path}::{_SCRIPT}: cannot parse {path}: {exc.msg} " f"(line {exc.lineno})."]
    errors: list[str] = []
    for lineno, literal in hits:
        if is_allowlisted(path, literal):
            continue
        errors.append(
            f"::error file={path},line={lineno}::{_SCRIPT}: hardcoded label "
            f"literal {literal!r}. Resolve the label through scripts/_ssot.py "
            f"(the .gitapex/ssot.json registry) instead of freezing the string; "
            f"if this file is a sanctioned single source for the label, add a "
            f"rationale-carrying LITERAL_ALLOWLIST entry."
        )
    return errors


# ---------------------------------------------------------------------------
# Family drift guard (pure)
# ---------------------------------------------------------------------------


def policy_family_names(label_policy: object) -> frozenset[str]:
    """Return the family names declared in the parsed label-policy TOML."""
    if not isinstance(label_policy, dict):
        return frozenset()
    return frozenset(
        fam["name"]
        for fam in label_policy.get("families", []) or []
        if isinstance(fam, dict) and isinstance(fam.get("name"), str)
    )


def uncovered_families(label_policy: object) -> frozenset[str]:
    """Return governed families the gate's KNOWN_FAMILIES does not cover."""
    return policy_family_names(label_policy) - frozenset(KNOWN_FAMILIES)


# ---------------------------------------------------------------------------
# IO boundary
# ---------------------------------------------------------------------------

_SCRIPT_PATH_RE = re.compile(r"^scripts/[^/]+\.py$")


def list_script_files(repo_root: Path, scripts_dir: str) -> list[str]:
    """Return repo-relative paths of tracked ``scripts/*.py`` files, sorted.

    Uses ``git ls-files``; if git is unavailable the listing degrades to an
    on-disk glob so the gate still runs.
    """
    try:
        completed = subprocess.run(  # noqa: S603 -- fixed argv, shell=False
            ["git", "-C", str(repo_root), "ls-files", f"{scripts_dir}/*.py"],  # noqa: S607
            capture_output=True,
            text=True,
            timeout=30,
        )
        if completed.returncode == 0:
            return sorted(line.strip() for line in completed.stdout.splitlines() if _SCRIPT_PATH_RE.match(line.strip()))
    except (OSError, subprocess.SubprocessError):
        pass
    return sorted(f"{scripts_dir}/{p.name}" for p in (repo_root / scripts_dir).glob("*.py") if p.is_file())


def verify(repo_root: Path, scripts_dir: str, label_policy: object) -> list[str]:
    """Return every ``::error::`` line for the working tree; empty means clean."""
    errors: list[str] = []

    missing = uncovered_families(label_policy)
    if missing:
        errors.append(
            f"::error file={_LABEL_POLICY_PATH}::{_SCRIPT}: label-policy declares "
            f"family/families {sorted(missing)} that {_SCRIPT}.KNOWN_FAMILIES "
            f"does not cover; add them so the gate scans their literals."
        )

    for path in list_script_files(repo_root, scripts_dir):
        source = (repo_root / path).read_text(encoding="utf-8")
        errors.extend(scan_file(path, source))
    return errors


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    command = argv[0] if argv else None
    if command != "verify":
        print(
            f"::error::{_SCRIPT}: unknown subcommand {command!r}; expected 'verify'.",
            file=sys.stderr,
        )
        return 64

    parser = argparse.ArgumentParser(description="Reject hardcoded GitHub label literals in scripts/*.py.")
    parser.add_argument("command", help="Must be 'verify'.")
    parser.add_argument("--scripts-dir", default=_SCRIPTS_DIR)
    parser.add_argument("--label-policy", default=_LABEL_POLICY_PATH)
    args = parser.parse_args(argv)

    label_policy_path = _REPO_ROOT / args.label_policy
    if not label_policy_path.exists():
        print(
            f"::error::{_SCRIPT}: label-policy file not found at {label_policy_path}.",
            file=sys.stderr,
        )
        return 1
    try:
        label_policy = tomllib.loads(label_policy_path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        print(f"::error::{_SCRIPT}: cannot parse label-policy: {exc}", file=sys.stderr)
        return 1

    errors = verify(_REPO_ROOT, args.scripts_dir, label_policy)

    if errors:
        for message in errors:
            print(message, file=sys.stderr)
        print(
            f"FAIL: {_SCRIPT}: {len(errors)} hardcoded label literal(s) or " f"family-coverage error(s) above.",
            file=sys.stderr,
        )
        return 1

    print(f"OK: {_SCRIPT}: no hardcoded label literals in {args.scripts_dir}/*.py.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
