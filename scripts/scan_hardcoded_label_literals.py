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
``family`` is a known label family (see :func:`known_families`) and ``name`` is
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

The known-family set is DERIVED from ``.github/label-policy.toml`` at run time,
not hardcoded: it unions the live ``[[families]]`` names with the family
prefixes of ``[[retired_labels]]`` (so a retired family such as ``threat`` or
``agent`` is still scanned, which is the whole point of catching a retired-label
regression), plus the runtime-only ``retro`` family defined in
``scripts/_retro_labels.py`` and deliberately absent from the catalog. A family
added to (or retired in) the policy therefore extends coverage with no gate
edit.

Sanctioned homes (the allowlist)
--------------------------------
Two tiers, both rationale-carrying (mirroring the ``scan_preflight_drift`` /
``scan_ssot_drift`` allowlist idiom):

- :data:`SSOT_HOME_FILES`: files that are the definitional single source for
  label names, exempt wholesale (``scripts/_retro_labels.py`` is the retro:*
  SSoT; ``scripts/_ssot.py`` returns names read from the registry).
- :data:`LITERAL_ALLOWLIST`: specific pre-existing label constants in
  otherwise-scanned files, keyed by ``(path, literal)`` and bound to an
  expected occurrence COUNT so a second copy of the same literal in the same
  file is still rejected (only the sanctioned constant is exempt, not every
  future reuse). Each entry carries its rationale, so the exception stays
  auditable.

Test files are out of scope by construction: the gate scans ``scripts/*.py``
only.

Contract:
- Inputs: the ``verify`` subcommand; ``--scripts-dir`` (default ``scripts``);
  ``--label-policy`` (default ``.github/label-policy.toml``, the source of the
  known-family set; a policy that declares no families is a hard error).
- Outputs: ``::error file=...,line=...::`` annotations on stderr, one per
  hardcoded literal; an ``OK:`` line on success.
- Failure policy: fails loud (exit 1) per CLAUDE.md section 4; it is a CI gate,
  so any hardcoded literal, an unparseable scripts/*.py, or a label-policy that
  declares no families exits non-zero. Exit 64 on an unrecognised subcommand.

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
from collections import Counter
from pathlib import Path

_SCRIPT = "scan_hardcoded_label_literals"
_REPO_ROOT = Path(__file__).resolve().parent.parent
_SCRIPTS_DIR = "scripts"
_LABEL_POLICY_PATH = ".github/label-policy.toml"

# Families that are real but live in neither label-policy table: ``retro`` is
# defined in scripts/_retro_labels.py and deliberately absent from the catalog
# (#1041 follow-up comment B). Unioned into the derived family set.
RUNTIME_ONLY_FAMILIES: frozenset[str] = frozenset({"retro"})

# The name segment after ``family:`` in a full label token.
_NAME_SEGMENT = r"[A-Za-z0-9][A-Za-z0-9._-]*"

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
# (path, literal) and mapped to (expected_count, rationale). Only the sanctioned
# occurrences are exempt: a literal appearing more than expected_count times in
# the file is reported (a second hardcoded copy is not silently accepted).
#
# The first group is the migration-safe SSoT constant homes #1041's
# label-control inventory records ("Migration-safe today (keep labels or
# family-prefix matching)"): each label is defined once, in its owning module.
#
# The dependabot_automerge threat:* pair is the documented inert
# defense-in-depth guard for the retired threat:* labels; it must stay frozen
# (see its rationale).
#
# The last group is consumers phase 2 did not migrate. They are exempted so the
# gate is green on the tree that introduces it (its job is anti-regression, not
# a same-PR migration), but NOT silently: each names the follow-up. In
# particular ``_security_drift_families.py`` still references the RETIRED
# ``layer:meta`` (exactly #1041 AC#3's target), but its successor (AC#2) is an
# undecided owner decision, so it is exempted pending that decision rather than
# hidden. Tracked under the phase-3 umbrella #2298.
LITERAL_ALLOWLIST: dict[tuple[str, str], tuple[int, str]] = {
    ("scripts/_ref_classifier.py", "type:tracking"): (
        1,
        "SSoT constant for the tracking label (#1041 inventory: migration-safe "
        "today; type:tracking is a live catalog label).",
    ),
    ("scripts/scan_non_ascii.py", "severity:non-ascii-content"): (
        1,
        "SSoT constant for the non-ASCII content severity label (#1041 " "inventory: migration-safe today).",
    ),
    ("scripts/dependabot_automerge.py", "severity:non-ascii-content"): (
        1,
        "The one exact advisory-label constant; blocking labels are matched by "
        "family prefix (the migration-safe #1041 comment A pattern), so this is "
        "the only frozen severity literal here (#1041 inventory: migration-safe "
        "today).",
    ),
    ("scripts/dependabot_automerge.py", "threat:response-needed"): (
        1,
        "Inert defense-in-depth guard for the retired threat:* labels (#1264; "
        "definitions retired #1647, producer removed #1651). Intentionally "
        "frozen with no producer constant to mirror; test-pinned in "
        "tests/test_dependabot_automerge.py. Kept per CLAUDE.md section 4 (do "
        "not collapse a safety layer).",
    ),
    ("scripts/dependabot_automerge.py", "threat:intel-needed"): (
        1,
        "Second half of the inert retired-threat:* defense-in-depth guard; same "
        "rationale as threat:response-needed (#1264/#1647/#1651, test-pinned).",
    ),
    ("scripts/threat_intel_triage.py", "severity:security"): (
        1,
        "SSoT constant for the security severity label (#1041 inventory: " "migration-safe today).",
    ),
    ("scripts/ci_budget_issue.py", "type:tracking"): (
        1,
        "Rolling CI-budget issue label constant; both labels are live. Phase 2 "
        "did not migrate this consumer to _ssot resolution; follow-up under "
        "#2298.",
    ),
    ("scripts/ci_budget_issue.py", "layer:p3-harness"): (
        1,
        "Rolling CI-budget issue label constant; both labels are live. Phase 2 "
        "did not migrate this consumer to _ssot resolution; follow-up under "
        "#2298.",
    ),
    ("scripts/_security_drift_families.py", "type:fix"): (
        1,
        "Per-family drift issue label constant; phase 2 did not migrate this "
        "consumer to _ssot resolution. Follow-up under #2298.",
    ),
    ("scripts/_security_drift_families.py", "layer:meta"): (
        1,
        "RETIRED label still referenced by the security-drift meta-fix lane "
        "(exactly #1041 AC#3's target), but its successor (#1041 AC#2) is an "
        "undecided owner decision, so it is exempted pending that decision "
        "rather than hidden. Migrate and successor tracked under #2298; tighten "
        "this entry once the successor lands.",
    ),
}


# ---------------------------------------------------------------------------
# Known families (derived from label-policy; pure over parsed data)
# ---------------------------------------------------------------------------


def policy_family_names(label_policy: object) -> frozenset[str]:
    """Return the live family names declared in ``[[families]]``."""
    if not isinstance(label_policy, dict):
        return frozenset()
    return frozenset(
        fam["name"]
        for fam in label_policy.get("families", []) or []
        if isinstance(fam, dict) and isinstance(fam.get("name"), str)
    )


def retired_family_names(label_policy: object) -> frozenset[str]:
    """Return the family prefixes of ``[[retired_labels]]`` names.

    A retired label such as ``threat:intel-needed`` or the ``agent:*`` glob
    contributes its ``family`` prefix so a hardcoded reference to a retired
    family is still scanned (the retired-label regression class #1041 targets).
    Bare retired names with no colon (``bug``, ``question``) contribute nothing.
    """
    if not isinstance(label_policy, dict):
        return frozenset()
    families: set[str] = set()
    for entry in label_policy.get("retired_labels", []) or []:
        if isinstance(entry, dict) and isinstance(entry.get("name"), str):
            name = entry["name"]
            if ":" in name:
                families.add(name.split(":", 1)[0])
    return frozenset(families)


def known_families(label_policy: object) -> frozenset[str]:
    """Return live + retired label families plus the runtime-only families."""
    return policy_family_names(label_policy) | retired_family_names(label_policy) | RUNTIME_ONLY_FAMILIES


def build_label_re(families: frozenset[str]) -> re.Pattern[str]:
    """Return the full-value ``family:name`` matcher for *families*."""
    alternation = "|".join(sorted(families))
    return re.compile(rf"^(?:{alternation}):{_NAME_SEGMENT}$")


# ---------------------------------------------------------------------------
# Detection (pure functions over source text)
# ---------------------------------------------------------------------------


def iter_label_literals(source: str, label_re: re.Pattern[str]) -> list[tuple[int, str]]:
    """Return ``(lineno, literal)`` for every full-value label constant.

    Raises :class:`SyntaxError` when *source* does not parse; the caller turns
    that into a loud gate failure rather than skipping the file silently.
    """
    tree = ast.parse(source)
    hits: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and label_re.match(node.value):
            hits.append((node.lineno, node.value))
    return hits


def allowed_occurrences(path: str, literal: str) -> int:
    """Return how many times *literal* may legitimately appear in *path*."""
    return LITERAL_ALLOWLIST.get((path, literal), (0, ""))[0]


def scan_file(path: str, source: str, label_re: re.Pattern[str]) -> list[str]:
    """Return ``::error::`` strings for non-allowlisted label literals in *path*."""
    if path in SSOT_HOME_FILES:
        return []  # whole-file sanctioned home; nothing to check
    try:
        hits = iter_label_literals(source, label_re)
    except SyntaxError as exc:
        return [f"::error file={path}::{_SCRIPT}: cannot parse {path}: {exc.msg} " f"(line {exc.lineno})."]
    seen: Counter[str] = Counter()
    errors: list[str] = []
    for lineno, literal in hits:
        seen[literal] += 1
        allowed = allowed_occurrences(path, literal)
        if seen[literal] <= allowed:
            continue
        if allowed:
            reason = (
                f"occurrence {seen[literal]} exceeds the {allowed} allowlisted "
                f"for this file; the LITERAL_ALLOWLIST exempts only the "
                f"sanctioned constant, not a second hardcoded copy."
            )
        else:
            reason = (
                "Resolve the label through scripts/_ssot.py (the "
                ".gitapex/ssot.json registry) instead of freezing the string; "
                "if this file is a sanctioned single source for the label, add "
                "a rationale-carrying LITERAL_ALLOWLIST entry."
            )
        errors.append(
            f"::error file={path},line={lineno}::{_SCRIPT}: hardcoded label " f"literal {literal!r}. {reason}"
        )
    return errors


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
    if not policy_family_names(label_policy):
        return [
            f"::error file={_LABEL_POLICY_PATH}::{_SCRIPT}: label-policy declares "
            f"no [[families]]; cannot derive the known-family set to scan for."
        ]

    label_re = build_label_re(known_families(label_policy))
    errors: list[str] = []
    for path in list_script_files(repo_root, scripts_dir):
        source = (repo_root / path).read_text(encoding="utf-8")
        errors.extend(scan_file(path, source, label_re))
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
            f"FAIL: {_SCRIPT}: {len(errors)} hardcoded label literal(s) or " f"configuration error(s) above.",
            file=sys.stderr,
        )
        return 1

    print(
        f"OK: {_SCRIPT}: no hardcoded label literals in {args.scripts_dir}/*.py.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
