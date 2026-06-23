"""Gate the worked examples against ``scripts/body_policy.py``.

The examples in ``docs/archive/issue-pr-body-examples.md`` are the
calibration material the issue/PR body standard points contributors to.
Before this gate the validator and ``tests/test_body_policy.py`` used
synthetic fixtures only, so a change to ``body_policy.py`` could leave the
published examples failing without any check noticing. This module extracts
each fenced example and asserts the validator accepts it for the matching
kind, so the documented examples cannot drift from the validator.

Extraction is deterministic and offline: it parses a machine-readable
directive placed immediately before each fenced block. The directive form
is documented in the example doc itself:

- ``<!-- body-policy-example: kind=issue -->``
- ``<!-- body-policy-example: kind=pull_request shape=yes -->``
- ``<!-- body-policy-example: skip="reason" -->``

For ``shape=yes`` the post-2026-05-26 PR shape is checked
(Verification command/result pairs and Checklist H3 subsections). The
agent-attribution footer check is intentionally excluded: a static
documentation example must not embed a live session footer.

The ``scripts/`` directory is on ``sys.path`` via the ``pythonpath`` key in
``pyproject.toml``. Refs #1091; hardens #206.
"""

from __future__ import annotations

import re
from pathlib import Path

import body_policy
import pytest

pytestmark = pytest.mark.shard_policy

_DOC = (
    Path(__file__).resolve().parent.parent
    / "docs"
    / "archive"
    / "issue-pr-body-examples.md"
)

_DIRECTIVE_RE = re.compile(
    r"^<!--\s*body-policy-example:\s*(?P<spec>.*?)\s*-->\s*$"
)
_SKIP_RE = re.compile(r'^skip="(?P<reason>[^"]*)"$')
_HEADING_RE = re.compile(r"^###\s+(?P<text>.+?)\s*$")


class _Example:
    """One fenced example plus the directive that governs it."""

    def __init__(self, heading: str | None, spec: str | None, body: str):
        self.heading = heading or "<no heading>"
        self.spec = spec
        self.body = body
        self.parsed = _parse_spec(spec) if spec is not None else None


def _parse_spec(spec: str) -> dict[str, str]:
    """Parse a directive spec into a key/value mapping.

    ``skip`` carries a quoted free-text reason; all other directives are
    whitespace-separated ``key=value`` tokens with unquoted values.
    """
    skip_match = _SKIP_RE.match(spec)
    if skip_match is not None:
        return {"skip": skip_match.group("reason")}
    out: dict[str, str] = {}
    for token in spec.split():
        if "=" not in token:
            raise ValueError(f"malformed directive token: {token!r}")
        key, value = token.split("=", 1)
        out[key] = value
    return out


def _extract_examples(text: str) -> list[_Example]:
    """Return every top-level fenced block paired with its directive.

    Headings and directives inside a fenced block are treated as content,
    not structure, so the post-2026-05-26 PR example's ``### Bootstrap``
    subsection does not masquerade as a section heading.
    """
    examples: list[_Example] = []
    in_fence = False
    fence_lines: list[str] = []
    fence_heading: str | None = None
    fence_directive: str | None = None
    pending_directive: str | None = None
    last_heading: str | None = None

    for line in text.splitlines():
        if line.strip() == "```":
            if not in_fence:
                in_fence = True
                fence_lines = []
                fence_directive = pending_directive
                fence_heading = last_heading
                pending_directive = None  # consumed by this block
            else:
                in_fence = False
                examples.append(
                    _Example(fence_heading, fence_directive, "\n".join(fence_lines))
                )
            continue
        if in_fence:
            fence_lines.append(line)
            continue
        directive_match = _DIRECTIVE_RE.match(line)
        if directive_match is not None:
            pending_directive = directive_match.group("spec")
            continue
        heading_match = _HEADING_RE.match(line)
        if heading_match is not None:
            last_heading = heading_match.group("text")
    return examples


_EXAMPLES = _extract_examples(_DOC.read_text(encoding="utf-8"))
_VALIDATED = [e for e in _EXAMPLES if e.parsed is not None and "skip" not in e.parsed]
_SKIPPED = [e for e in _EXAMPLES if e.parsed is not None and "skip" in e.parsed]


def _ids(examples: list[_Example]) -> list[str]:
    return [e.heading for e in examples]


class TestExtraction:
    def test_doc_exists_and_has_examples(self) -> None:
        assert _DOC.is_file()
        assert _EXAMPLES, "no fenced examples found in the example doc"

    def test_extraction_is_ascii(self) -> None:
        # Acceptance criterion: extraction is deterministic and ASCII-only.
        text = _DOC.read_text(encoding="utf-8")
        assert text.isascii(), "example doc must remain ASCII-only"

    def test_every_fenced_block_has_a_directive(self) -> None:
        # Fail loudly so a new example cannot land unvalidated.
        undirected = [e.heading for e in _EXAMPLES if e.spec is None]
        assert undirected == [], (
            "fenced examples missing a body-policy-example directive: "
            f"{undirected}"
        )

    def test_skip_directives_carry_a_reason(self) -> None:
        for example in _SKIPPED:
            assert example.parsed is not None
            assert example.parsed["skip"].strip(), (
                f"{example.heading}: skip directive needs a non-empty reason"
            )

    def test_expected_examples_are_validated(self) -> None:
        # Guards against silent loss: the five issue types plus the current
        # PR shape must be validated.
        kinds = [e.parsed["kind"] for e in _VALIDATED if e.parsed is not None]
        assert kinds.count("issue") >= 5, kinds
        assert kinds.count("pull_request") >= 1, kinds
        assert any(
            e.parsed is not None and e.parsed.get("shape") == "yes"
            for e in _VALIDATED
        ), "expected at least one shape-checked PR example"


@pytest.mark.parametrize("example", _VALIDATED, ids=_ids(_VALIDATED))
class TestValidatedExamples:
    def test_kind_is_recognised(self, example: _Example) -> None:
        assert example.parsed is not None
        assert example.parsed["kind"] in ("issue", "pull_request"), (
            f"{example.heading}: unknown kind {example.parsed.get('kind')!r}"
        )

    def test_baseline_sections_present(self, example: _Example) -> None:
        assert example.parsed is not None
        kind = example.parsed["kind"]
        required = body_policy.required_sections(kind, body=example.body)
        headings = body_policy.extract_headings(example.body)
        missing = body_policy.missing_sections(required, headings)
        assert missing == [], (
            f"{example.heading}: body_policy.py would reject this {kind} "
            f"example; missing required section(s): {missing}"
        )

    def test_pr_shape_when_requested(self, example: _Example) -> None:
        assert example.parsed is not None
        if example.parsed.get("shape") != "yes":
            pytest.skip("shape check not requested for this example")
        assert example.parsed["kind"] == "pull_request", (
            f"{example.heading}: shape=yes is only valid for pull_request"
        )
        errors = body_policy.verify_pr_verification_pairs(
            example.body
        ) + body_policy.verify_pr_checklist_subsections(example.body)
        assert errors == [], (
            f"{example.heading}: PR shape gate would reject this example "
            f"(footer check excluded): {errors}"
        )
