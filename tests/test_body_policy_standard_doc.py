"""Keep the standard-doc prose in sync with ``scripts/body_policy.py``.

Issue #1191: the section-name lists written in the prose of
``docs/standards/issue-pr-body-standard.md`` ("Issue body sections" and
"PR body sections") are the contributor-facing description of the body
shape, but nothing cross-checked them against the required/allowed
constants in ``scripts/body_policy.py``. A change to either side that was
not mirrored in the other recreated the drift class #1091 was opened to
fix, one level up (prose vs validator).

These tests parse the ``## <Name>`` headings listed in those two doc
sections and assert they match the ``body_policy.py`` constants in either
direction:

* the PR list equals ``_PR_ALLOWED`` (``_PR_REQUIRED`` plus the
  conditional ``Text delta``);
* the issue list equals ``_ISSUE_COMMON_REQUIRED`` plus the optional
  ``_ISSUE_OPTIONAL`` (``Parent``);
* every ``_ISSUE_TRACKING_REQUIRED`` name is documented somewhere in the
  runbook (the tracking variants live in the ``type:tracking`` prose, not
  the single common list, so this side is a coverage check).

Refs #1191, #1396.
"""

from __future__ import annotations

import re
from pathlib import Path

import body_policy
import pytest

pytestmark = pytest.mark.shard_policy

REPO_ROOT = Path(__file__).resolve().parents[1]
BODY_STANDARD = REPO_ROOT / "docs" / "standards" / "issue-pr-body-standard.md"

# A top-level list item naming an H2 section, e.g. ``- `## Summary` - ...``.
# Anchored to the line start and the literal ``## `` (two hashes + space) so
# that indented H3 sub-bullets (``  - `### Bootstrap```) and inline mentions
# (``historically titled `## Why```) are not captured.
_SECTION_BULLET_RE = re.compile(r"^- `## ([^`]+)`", re.MULTILINE)
# Any backticked ``## Name`` anywhere in the doc, for coverage checks.
_ANY_H2_TOKEN_RE = re.compile(r"`## ([^`]+)`")


def _doc_text() -> str:
    return BODY_STANDARD.read_text(encoding="utf-8")


def _section_slice(text: str, heading: str) -> str:
    """Return the text from the H2 *heading* line to the next H2 heading."""
    pattern = re.compile(
        r"^## " + re.escape(heading) + r".*?$(.*?)(?=^## )",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(text)
    assert match is not None, f"section '## {heading}' not found in {BODY_STANDARD}"
    return match.group(1)


def _doc_section_headings(heading: str) -> set[str]:
    return set(_SECTION_BULLET_RE.findall(_section_slice(_doc_text(), heading)))


def test_pr_section_list_matches_allowlist() -> None:
    """The doc's PR section list must equal ``_PR_ALLOWED`` exactly."""
    documented = _doc_section_headings("PR body sections")
    assert documented == set(body_policy._PR_ALLOWED), (
        "PR body section prose and body_policy._PR_ALLOWED disagree; "
        f"only in doc: {sorted(documented - set(body_policy._PR_ALLOWED))}; "
        f"only in constant: {sorted(set(body_policy._PR_ALLOWED) - documented)}"
    )


def test_issue_section_list_matches_required_plus_optional() -> None:
    """The doc's issue section list must equal required + optional exactly."""
    documented = _doc_section_headings("Issue body sections")
    expected = set(body_policy._ISSUE_COMMON_REQUIRED) | set(
        body_policy._ISSUE_OPTIONAL
    )
    assert documented == expected, (
        "Issue body section prose and body_policy constants disagree; "
        f"only in doc: {sorted(documented - expected)}; "
        f"only in constants: {sorted(expected - documented)}"
    )


def test_tracking_required_sections_documented() -> None:
    """Every tracking-required section name appears somewhere in the doc."""
    documented_anywhere = set(_ANY_H2_TOKEN_RE.findall(_doc_text()))
    missing = [
        name
        for name in body_policy._ISSUE_TRACKING_REQUIRED
        if name not in documented_anywhere
    ]
    assert not missing, f"tracking-required sections not documented: {missing}"


def test_drift_in_either_direction_is_detectable() -> None:
    """A constant change not mirrored in the doc breaks set equality.

    Demonstrates the gate catches drift in both directions using the same
    comparison the real assertions rely on, without mutating the module.
    """
    documented = _doc_section_headings("PR body sections")
    # Adding a constant without documenting it -> sets differ.
    assert documented != set(body_policy._PR_ALLOWED) | {"Undocumented"}
    # Dropping a documented section from the constant -> sets differ.
    assert documented != set(body_policy._PR_ALLOWED) - {"Summary"}
