from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import prune_codespaces as pc

pytestmark = pytest.mark.shard_ci_ops

NOW = datetime(2026, 6, 24, tzinfo=UTC)


def _cs(
    name: str,
    state: str,
    age_days: int,
    *,
    never_used: bool = False,
) -> dict[str, Any]:
    last_used = None if never_used else (NOW - timedelta(days=age_days)).isoformat().replace("+00:00", "Z")
    created = (NOW - timedelta(days=age_days)).isoformat().replace("+00:00", "Z")
    return {
        "name": name,
        "state": state,
        "last_used_at": last_used,
        "created_at": created,
        "owner": {"login": "user1"},
        "repository": {"full_name": "org/repo"},
    }


# ---------------------------------------------------------------------------
# parse_bool
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("text", "expected"), [("true", True), ("FALSE", False), (" True ", True)])
def test_parse_bool_accepts_true_false(text: str, expected: bool) -> None:
    assert pc.parse_bool(text) is expected


def test_parse_bool_rejects_ambiguous() -> None:
    with pytest.raises(ValueError):
        pc.parse_bool("${{ inputs.dry_run }}")


# ---------------------------------------------------------------------------
# _activity_time
# ---------------------------------------------------------------------------


def test_activity_time_prefers_last_used_at() -> None:
    cs = _cs("cs1", "Shutdown", age_days=10)
    t = pc._activity_time(cs)
    assert t == NOW - timedelta(days=10)


def test_activity_time_falls_back_to_created_at() -> None:
    cs = _cs("cs2", "Shutdown", age_days=20, never_used=True)
    t = pc._activity_time(cs)
    assert t == NOW - timedelta(days=20)


def test_activity_time_returns_epoch_for_missing_fields() -> None:
    cs: dict[str, Any] = {"name": "cs3", "state": "Shutdown"}
    t = pc._activity_time(cs)
    assert t == datetime.fromtimestamp(0, tz=UTC)


# ---------------------------------------------------------------------------
# select_candidates
# ---------------------------------------------------------------------------


def test_select_candidates_returns_shutdown_above_threshold() -> None:
    codespaces = [
        _cs("old-shutdown", "Shutdown", age_days=40),
        _cs("young-shutdown", "Shutdown", age_days=10),
        _cs("old-available", "Available", age_days=40),
        _cs("old-starting", "Starting", age_days=40),
    ]
    result = pc.select_candidates(codespaces, min_age_days=30, now=NOW)
    assert [c["name"] for c in result] == ["old-shutdown"]


def test_select_candidates_never_used_falls_back_to_created_at() -> None:
    cs = _cs("never-used", "Shutdown", age_days=60, never_used=True)
    result = pc.select_candidates([cs], min_age_days=30, now=NOW)
    assert len(result) == 1


def test_select_candidates_excludes_running_states() -> None:
    for state in ("Available", "Starting", "Provisioning", "Exporting", "Rebuilding"):
        cs = _cs("cs", state, age_days=200)
        assert pc.select_candidates([cs], min_age_days=30, now=NOW) == []


def test_select_candidates_rejects_negative_min_age() -> None:
    with pytest.raises(ValueError):
        pc.select_candidates([], min_age_days=-1, now=NOW)


def test_select_candidates_empty_list() -> None:
    assert pc.select_candidates([], min_age_days=30, now=NOW) == []


# ---------------------------------------------------------------------------
# cmd_prune
# ---------------------------------------------------------------------------


def test_cmd_prune_requires_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GH_TOKEN", raising=False)
    rc = pc.main(["prune", "--org", "org", "--min-age-days", "30", "--dry-run", "true"])
    assert rc == 1


def test_cmd_prune_dry_run_does_not_delete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GH_TOKEN", "tok")
    monkeypatch.setattr(pc, "_list_codespaces", lambda *a, **k: [_cs("cs1", "Shutdown", 60)])
    deleted: list[str] = []

    def _fake_delete(org: str, name: str, token: str, **kw: Any) -> tuple[int, str]:
        deleted.append(name)
        return 202, ""

    monkeypatch.setattr(pc, "_delete_codespace", _fake_delete)
    summary = tmp_path / "summary.md"
    rc = pc.main([
        "prune", "--org", "org", "--min-age-days", "30",
        "--dry-run", "true", "--summary-file", str(summary),
    ])
    assert rc == 0
    assert deleted == []
    assert "dry-run" in summary.read_text(encoding="utf-8")


def test_cmd_prune_live_calls_delete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GH_TOKEN", "tok")
    monkeypatch.setattr(pc, "_list_codespaces", lambda *a, **k: [_cs("cs2", "Shutdown", 60)])
    deleted: list[str] = []

    def _fake_delete(org: str, name: str, token: str, **kw: Any) -> tuple[int, str]:
        deleted.append(name)
        return 202, ""

    monkeypatch.setattr(pc, "_delete_codespace", _fake_delete)
    rc = pc.main(["prune", "--org", "org", "--min-age-days", "30", "--dry-run", "false"])
    assert rc == 0
    assert deleted == ["cs2"]


def test_cmd_prune_delete_failure_returns_nonzero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GH_TOKEN", "tok")
    monkeypatch.setattr(pc, "_list_codespaces", lambda *a, **k: [_cs("cs3", "Shutdown", 60)])
    monkeypatch.setattr(pc, "_delete_codespace", lambda *a, **k: (403, "forbidden"))
    rc = pc.main(["prune", "--org", "org", "--min-age-days", "30", "--dry-run", "false"])
    assert rc == 1


def test_cmd_prune_list_failure_is_loud(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GH_TOKEN", "tok")

    def _boom(*a: Any, **k: Any) -> list[dict[str, Any]]:
        raise RuntimeError("HTTP 500: internal error")

    monkeypatch.setattr(pc, "_list_codespaces", _boom)
    rc = pc.main(["prune", "--org", "org", "--min-age-days", "30", "--dry-run", "false"])
    assert rc == 1


def test_cmd_prune_no_candidates_is_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GH_TOKEN", "tok")
    monkeypatch.setattr(pc, "_list_codespaces", lambda *a, **k: [_cs("cs4", "Available", 60)])
    deleted: list[str] = []
    monkeypatch.setattr(pc, "_delete_codespace", lambda *a, **k: deleted.append("x") or (202, ""))
    rc = pc.main(["prune", "--org", "org", "--min-age-days", "30", "--dry-run", "false"])
    assert rc == 0
    assert deleted == []


def test_cmd_prune_summary_written_on_dry_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GH_TOKEN", "tok")
    monkeypatch.setattr(pc, "_list_codespaces", lambda *a, **k: [])
    summary = tmp_path / "step-summary.md"
    rc = pc.main([
        "prune", "--org", "myorg", "--min-age-days", "30",
        "--dry-run", "true", "--summary-file", str(summary),
    ])
    assert rc == 0
    assert summary.exists()
    assert "Codespace prune" in summary.read_text(encoding="utf-8")
