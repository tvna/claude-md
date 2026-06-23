#!/usr/bin/env python3
"""Deterministic gate: every scheduled control family meets the auto-file floor.

The workflow ``.github/workflows/verify-agents.yml`` invokes this module from
the ``lint-scripts-static`` job. It reads ``.github/security-control-floor.toml``
-- the machine-readable floor for scheduled security-control drift detection --
and fails CI when any listed family sits below the agreed floor without an
explicit, non-empty exemption reason.

Why a gate (CLAUDE.md section 3): the project raised ``labels``,
``apm-instructions`` and ``uv-pin-literal`` to the ``detect-and-file`` floor
(auto-filing a per-family issue on drift, matching ``rulesets``). Without a
deterministic check, a future family could land at ``detect-only``; detected
but silently un-filed; and only reviewer memory would catch it. This gate
makes the floor a continuous, fail-loud invariant.

Tier ladder (see the TOML header for the full contract):
    pr-gate-only < detect-only < detect-and-file (== floor)

Contract:
- Inputs: ``--config`` (defaults to ``.github/security-control-floor.toml``).
- Outputs: ``::error::`` annotations on stderr naming each below-floor family
  or malformed entry; exit 0 when every family meets the floor (or carries a
  non-empty ``exempt_reason``), exit 1 otherwise.
- Failure policy: fails loud per CLAUDE.md section 4 (it is a CI gate).

Tested by ``tests/test_verify_security_control_floor.py``. Refs #178.
"""
from __future__ import annotations

import argparse
import sys
import tomllib
from pathlib import Path
from typing import Any

DEFAULT_CONFIG = Path(".github/security-control-floor.toml")

# Lowest to highest capability. A family meets the floor when its tier rank is
# greater than or equal to the floor's rank.
TIER_ORDER: dict[str, int] = {
    "pr-gate-only": 0,
    "detect-only": 1,
    "detect-and-file": 2,
}


def evaluate(config: dict[str, Any]) -> list[str]:
    """Return a list of human-readable violation messages (empty == clean).

    Pure: takes the parsed TOML mapping, performs no I/O. A family below the
    floor is a violation unless it declares a non-empty ``exempt_reason``.
    Malformed shapes (missing/unknown ``floor`` or ``tier``, non-table
    ``families``) are violations in their own right so the gate never passes
    on a config it could not fully understand.
    """
    errors: list[str] = []

    floor = config.get("floor")
    if floor not in TIER_ORDER:
        errors.append(
            f"floor must be one of {sorted(TIER_ORDER)}; got {floor!r}"
        )
        return errors
    floor_rank = TIER_ORDER[floor]

    families = config.get("families")
    if not isinstance(families, dict) or not families:
        errors.append("[families] must be a non-empty table")
        return errors

    for name, spec in families.items():
        if not isinstance(spec, dict):
            errors.append(f"family {name!r}: entry must be a table")
            continue
        tier = spec.get("tier")
        if tier not in TIER_ORDER:
            errors.append(
                f"family {name!r}: tier must be one of {sorted(TIER_ORDER)}; "
                f"got {tier!r}"
            )
            continue
        if TIER_ORDER[tier] < floor_rank:
            reason = spec.get("exempt_reason")
            if not (isinstance(reason, str) and reason.strip()):
                errors.append(
                    f"family {name!r}: tier {tier!r} is below the floor "
                    f"{floor!r} and carries no exempt_reason. Raise it to "
                    f"'{floor}' (auto-file a per-family issue on drift) or add "
                    f"a non-empty exempt_reason justifying the lower tier."
                )

    return errors


def _load_config(path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args(argv)

    try:
        config = _load_config(args.config)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        print(f"::error::cannot read {args.config}: {exc}", file=sys.stderr)
        return 1

    errors = evaluate(config)
    for message in errors:
        print(f"::error::{message}", file=sys.stderr)
    if errors:
        print(
            f"::error::security-control floor gate failed "
            f"({len(errors)} violation(s)).",
            file=sys.stderr,
        )
        return 1
    print(f"OK: every family in {args.config} meets the security-control floor.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
