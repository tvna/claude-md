#!/usr/bin/env python3
"""Static per-family catalog for the security-control drift aggregator.

Split out of ``scripts/security_drift_report.py`` (#1488) to keep that module
within its maintainability size budget: this file holds only the inert data --
which families auto-file an issue on drift, the issue labels, and the per-family
issue text; while the aggregator keeps the runtime classify/report/IO logic.
``security_drift_report`` re-imports these names, so ``sdr.TARGET_FAMILIES`` etc.
stay stable for callers and tests. Refs #180, parent #178.
"""
from __future__ import annotations

import dataclasses

import _ssot

STATUS_COVERED = "covered"
STATUS_DRIFT = "drift"
STATUS_PENDING = "pending"
STATUS_ERROR = "error"
_VALID_STATUSES = frozenset({STATUS_COVERED, STATUS_DRIFT, STATUS_PENDING, STATUS_ERROR})


@dataclasses.dataclass(frozen=True)
class FamilyRow:
    family: str
    detector: str
    status: str
    evidence: str
    action: str

    def __post_init__(self) -> None:
        if self.status not in _VALID_STATUSES:
            raise ValueError(
                f"FamilyRow.status must be one of {sorted(_VALID_STATUSES)}; "
                f"got {self.status!r}"
            )


def issue_labels() -> tuple[str, ...]:
    """Return the labels applied to every auto-filed per-family drift issue.

    Resolved from the ``.gitapex/ssot.json`` registry (mirrors
    scripts/branch_cleanup.py, scripts/ruleset_drift.py) rather than frozen
    here, so a label rename or retirement (e.g. the retired-meta-layer
    successor decided at #1041 comment 4882932274) is a registry-only edit. Wraps
    :func:`_ssot.consumer_labels`'s ``KeyError``/``TypeError`` (a drifted
    registry entry) as ``RuntimeError`` so callers fail loud at this single
    boundary. Refs #2313, #1041.
    """
    try:
        return _ssot.consumer_labels("scripts/_security_drift_families.py")
    except (KeyError, TypeError) as exc:
        raise RuntimeError(f"security-drift-families registry labels: {exc}") from exc

# Families this aggregator auto-files an issue for when they drift, raising them
# to the `detect-and-file` floor (.github/security-control-floor.toml). The
# `rulesets` family is deliberately excluded; the dedicated ruleset-drift job
# already files its own issues, so including it here would double-file. The
# advisory `uv-pin-staleness` signal is excluded by design (warning-only).
TARGET_FAMILIES: tuple[str, ...] = (
    "labels",
    "apm-instructions",
    "uv-pin-literal",
    "workflow-permissions",
)

# Per-family static issue text. Detector/evidence mirror the classify_* rows;
# remediation is the actionable next step a responder runs.
FAMILY_ISSUE_SPEC: dict[str, dict[str, str]] = {
    "labels": {
        "scope": "labels-drift",
        "detector": "scripts/labels_apply.py plan",
        "evidence": ".github/label-policy.toml",
        "remediation": (
            "Review the labels plan in the run log, then dispatch apply-labels.yml "
            "with dry_run=false after review (docs/runbooks/issue-triage.md)."
        ),
    },
    "apm-instructions": {
        "scope": "apm-drift",
        "detector": "apm compile --target all + git status --porcelain; CLAUDE.md AGENTS.md GEMINI.md .github/copilot-instructions.md",
        "evidence": ".apm/instructions/master.instructions.md",
        "remediation": (
            "Recompile with `uv run --with apm-cli==<pin> --exclude-newer \"14 days\" "
            "apm compile --target all` and commit the regenerated CLAUDE.md / "
            "AGENTS.md / GEMINI.md."
        ),
    },
    "uv-pin-literal": {
        "scope": "uv-pin-drift",
        "detector": "scripts/uv_pin.py drift",
        "evidence": "pyproject.toml [tool.uv].required-version",
        "remediation": (
            "Remove the offending pin literal or update pyproject.toml so the pin "
            "lives only in [tool.uv].required-version "
            "(docs/standards/remote-environment.md)."
        ),
    },
    "workflow-permissions": {
        "scope": "workflow-permissions-drift",
        "detector": "scripts/rulesets_apply.py workflow-permissions --mode drift",
        "evidence": ".github/actions-permissions/workflow.json",
        "remediation": (
            "Dispatch apply-rulesets.yml with enable_workflow_permissions=true and "
            "dry_run=false after review (docs/runbooks/workflow-permissions.md)."
        ),
    },
}
