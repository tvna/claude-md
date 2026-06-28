"""Tests for ``scripts/scan_nonexhaustive_invariant_drift.py``.

The gate locks the non-exhaustive marker onto the section 2/4 safety
invariant bullets so a later edit cannot quietly re-close an enumeration
(Refs #1239, #1241, #1242, #1243, #178).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import scan_nonexhaustive_invariant_drift as snid

pytestmark = pytest.mark.shard_default


def _compliant_master() -> str:
    """A minimal master carrying every registered anchor with its marker."""
    return "\n".join(
        f"- {anchor} ... these are {snid.MARKER}, not a closed list ... by default."
        for anchor in snid.REGISTERED_BULLETS.values()
    )


class TestFindViolations:
    def test_clean_when_every_bullet_keeps_marker(self) -> None:
        assert snid.find_violations(_compliant_master(), "m.md") == []

    def test_flags_bullet_that_dropped_marker(self) -> None:
        text = _compliant_master().replace(snid.MARKER, "a fixed list")
        problems = snid.find_violations(text, "m.md")
        # One annotation per registered bullet that lost the marker.
        assert len(problems) == len(snid.REGISTERED_BULLETS)
        assert all("::error file=m.md,line=" in p for p in problems)
        assert all(snid.MARKER in p for p in problems)

    def test_flags_missing_anchor(self) -> None:
        lines = _compliant_master().splitlines()
        # Drop the first registered bullet entirely.
        text = "\n".join(lines[1:])
        problems = snid.find_violations(text, "m.md")
        assert any("not found" in p for p in problems)

    def test_only_the_dropped_bullet_is_flagged(self) -> None:
        lines = _compliant_master().splitlines()
        first_label = next(iter(snid.REGISTERED_BULLETS))
        lines[0] = lines[0].replace(snid.MARKER, "a fixed list")
        problems = snid.find_violations("\n".join(lines), "m.md")
        assert len(problems) == 1
        assert first_label in problems[0]


class TestVerifyCommand:
    def test_missing_master_returns_2(self, tmp_path: Path) -> None:
        missing = tmp_path / "nope.md"
        assert snid.main(["verify", "--master", str(missing)]) == 2

    def test_drift_returns_1(self, tmp_path: Path) -> None:
        bad = tmp_path / "master.md"
        bad.write_text(_compliant_master().replace(snid.MARKER, "x"), encoding="utf-8")
        assert snid.main(["verify", "--master", str(bad)]) == 1

    def test_clean_returns_0(self, tmp_path: Path) -> None:
        good = tmp_path / "master.md"
        good.write_text(_compliant_master(), encoding="utf-8")
        assert snid.main(["verify", "--master", str(good)]) == 0


def test_real_master_is_locked() -> None:
    """The live master source must satisfy the gate (mirrors the CI step)."""
    assert snid.main(["verify"]) == 0
