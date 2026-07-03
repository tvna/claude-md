"""Tests for scripts/flake_pin_latest.py; the auto-follow decision logic.

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
from typing import Any

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
    def fetch(_repo: str) -> dict[str, Any]:
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


def test_bad_latest_version_holds(capsys: pytest.CaptureFixture[str]) -> None:
    # An upstream ``releases/latest`` tag that is not a parseable CLI version is
    # an external condition (an unrelated release stream sharing the repo), not
    # repo corruption -> hold (None), not raise. A one-line warning goes to
    # stderr for visibility. Refs #2221.
    assert _decide("vNOT.A.NUM", "2026-05-01T00:00:00Z") is None
    err = capsys.readouterr().err
    assert "does not look like" in err
    assert "microsoft/waza" in err


def test_non_cli_release_tag_holds() -> None:
    # Regression for #2221: microsoft/waza's ``releases/latest`` returned the
    # azd extension's tag, which the CLI version parser cannot interpret. The
    # refresh job must hold (exit 0), not hard-fail the whole matrix leg.
    assert _decide("azd-ext-microsoft-azd-waza_0.38.0", "2026-05-01T00:00:00Z") is None


def test_bad_pinned_version_fails_loud() -> None:
    # The pinned side (from flake.nix) staying fail-loud: a corrupt pinned value
    # signals repo-state corruption and must raise, not hold (CLAUDE.md sec 4).
    with pytest.raises(flake_pin_latest.LatestPinError):
        flake_pin_latest.decide(
            "waza",
            flake_text='wazaVersion = "NOT.A.NUM";\napmVersion = "0.12.1";\n',
            fetcher=_fetcher("v0.34.0", "2026-05-01T00:00:00Z"),
            cooldown_days=14,
            now=_NOW,
        )


def test_version_tuple_orders_numerically() -> None:
    vt = flake_pin_latest._version_tuple
    assert vt("0.9.0") < vt("0.10.0")  # numeric, not lexical
    assert vt("v1.2.3") == vt("1.2.3")


# ---------------------------------------------------------------------------
# github_latest_release() with mocked _github_api (lines 92-107)
# ---------------------------------------------------------------------------


def test_github_latest_release_success(monkeypatch: pytest.MonkeyPatch) -> None:
    # HTTP 200 + valid dict -> lines 92-94 (call), 101-102 (json.loads),
    # 105 (isinstance check False), 107 (return payload).
    import json as _json

    payload = {"tag_name": "v1.0.0", "published_at": "2026-01-01T00:00:00Z"}
    monkeypatch.setattr(
        flake_pin_latest._github_api,
        "apply_call",
        lambda **kw: (200, _json.dumps(payload)),
    )
    result = flake_pin_latest.github_latest_release("owner/repo")
    assert result["tag_name"] == "v1.0.0"


def test_github_latest_release_non_200_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    # Non-200 response -> lines 97-98 (LatestPinError raise).
    monkeypatch.setattr(
        flake_pin_latest._github_api,
        "apply_call",
        lambda **kw: (404, "not found"),
    )
    with pytest.raises(flake_pin_latest.LatestPinError, match="HTTP 404"):
        flake_pin_latest.github_latest_release("owner/repo")


def test_github_latest_release_non_json_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    # HTTP 200 but body is not JSON -> lines 103-104 (JSONDecodeError path).
    monkeypatch.setattr(
        flake_pin_latest._github_api,
        "apply_call",
        lambda **kw: (200, "not-json"),
    )
    with pytest.raises(flake_pin_latest.LatestPinError, match="non-JSON"):
        flake_pin_latest.github_latest_release("owner/repo")


def test_github_latest_release_non_dict_json_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    # HTTP 200, valid JSON but not a dict -> line 106 (LatestPinError).
    import json as _json

    monkeypatch.setattr(
        flake_pin_latest._github_api,
        "apply_call",
        lambda **kw: (200, _json.dumps([1, 2, 3])),
    )
    with pytest.raises(flake_pin_latest.LatestPinError, match="non-object"):
        flake_pin_latest.github_latest_release("owner/repo")


# ---------------------------------------------------------------------------
# _parse_release edge cases (lines 130-131, 135)
# ---------------------------------------------------------------------------


def test_parse_release_bad_published_at_raises() -> None:
    # published_at cannot be parsed by fromisoformat -> lines 130-131.
    with pytest.raises(flake_pin_latest.LatestPinError, match="bad published_at"):
        flake_pin_latest._parse_release(
            {"tag_name": "v1.0.0", "published_at": "not-a-date"}, "owner/repo"
        )


def test_parse_release_naive_datetime_gets_utc() -> None:
    # published_at has no timezone info -> line 135 sets tzinfo to UTC.
    tag, when = flake_pin_latest._parse_release(
        {"tag_name": "v1.0.0", "published_at": "2026-01-01T00:00:00"}, "owner/repo"
    )
    assert when.tzinfo is not None


# ---------------------------------------------------------------------------
# decide() negative cooldown (line 156)
# ---------------------------------------------------------------------------


def test_decide_negative_cooldown_raises() -> None:
    # cooldown_days < 0 -> line 156 LatestPinError before any API call.
    with pytest.raises(flake_pin_latest.LatestPinError, match="cooldown_days"):
        flake_pin_latest.decide(
            "waza",
            flake_text=_FLAKE,
            fetcher=_fetcher("v0.34.0", "2026-05-14T00:00:00Z"),
            cooldown_days=-1,
            now=_NOW,
        )
