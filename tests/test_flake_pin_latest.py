"""Tests for scripts/flake_pin_latest.py -- the auto-follow decision logic.

The cooldown + version-comparison decision is exercised here with an injected
fetcher and a fixed ``now``, so it never hits the GitHub API. This pins the two
hold conditions (not newer; still within cooldown) and the fail-loud behaviour
on malformed release payloads. Refs #1171, #643.
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.shard_ci_ops

REPO_ROOT = Path(__file__).resolve().parent.parent
_SPEC = importlib.util.spec_from_file_location(
    "flake_pin_latest", REPO_ROOT / "scripts" / "flake_pin_latest.py"
)
assert _SPEC and _SPEC.loader
flake_pin_latest = importlib.util.module_from_spec(_SPEC)
sys.modules["flake_pin_latest"] = flake_pin_latest
_SPEC.loader.exec_module(flake_pin_latest)

_FLAKE = 'wazaVersion = "0.33.0";\napmVersion = "0.12.1";\n'
_NOW = dt.datetime(2026, 6, 3, tzinfo=dt.UTC)


def _fetcher(tag: str, published: str):
    def fetch(_repo: str) -> dict:
        return {"tag_name": tag, "published_at": published}

    return fetch


def _decide(tag: str, published: str, *, cooldown_days: int = 14):
    return flake_pin_latest.decide(
        "waza",
        flake_text=_FLAKE,
        fetcher=_fetcher(tag, published),
        cooldown_days=cooldown_days,
        now=_NOW,
    )


def test_adopts_newer_release_past_cooldown() -> None:
    # 20 days old > 14 day cooldown -> adoptable.
    assert _decide("v0.34.0", "2026-05-14T00:00:00Z") == "0.34.0"


def test_holds_when_not_newer() -> None:
    assert _decide("v0.33.0", "2026-05-14T00:00:00Z") is None
    assert _decide("v0.32.9", "2026-05-14T00:00:00Z") is None


def test_holds_within_cooldown() -> None:
    # Published 5 days ago, cooldown 14 days -> hold even though newer.
    assert _decide("v0.34.0", "2026-05-29T00:00:00Z") is None


def test_cooldown_boundary_exactly_n_days_adopts() -> None:
    # Exactly 14 days old -> age == cooldown -> not < cooldown -> adopt.
    assert _decide("v0.34.0", "2026-05-20T00:00:00Z") == "0.34.0"


def test_strips_leading_v_in_comparison() -> None:
    # Pinned 0.33.0, latest tag "v0.33.1" -> newer.
    assert _decide("v0.33.1", "2026-05-01T00:00:00Z") == "0.33.1"


def test_missing_tag_fails_loud() -> None:
    with pytest.raises(flake_pin_latest.LatestPinError):
        flake_pin_latest.decide(
            "waza",
            flake_text=_FLAKE,
            fetcher=lambda _r: {"published_at": "2026-05-01T00:00:00Z"},
            cooldown_days=14,
            now=_NOW,
        )


def test_missing_published_at_fails_loud() -> None:
    with pytest.raises(flake_pin_latest.LatestPinError):
        flake_pin_latest.decide(
            "waza",
            flake_text=_FLAKE,
            fetcher=lambda _r: {"tag_name": "v0.34.0"},
            cooldown_days=14,
            now=_NOW,
        )


def test_bad_version_fails_loud() -> None:
    with pytest.raises(flake_pin_latest.LatestPinError):
        flake_pin_latest.decide(
            "waza",
            flake_text=_FLAKE,
            fetcher=_fetcher("vNOT.A.NUM", "2026-05-01T00:00:00Z"),
            cooldown_days=14,
            now=_NOW,
        )


def test_version_tuple_orders_numerically() -> None:
    vt = flake_pin_latest._version_tuple
    assert vt("0.9.0") < vt("0.10.0")  # numeric, not lexical
    assert vt("v1.2.3") == vt("1.2.3")
