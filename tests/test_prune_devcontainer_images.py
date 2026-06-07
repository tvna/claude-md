from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import prune_devcontainer_images as pdi

pytestmark = pytest.mark.shard_ci_ops

NOW = datetime(2026, 6, 7, tzinfo=UTC)


def _version(version_id: int, tags: list[str], age_days: int) -> dict[str, Any]:
    created = (NOW - timedelta(days=age_days)).isoformat().replace("+00:00", "Z")
    return {
        "id": version_id,
        "created_at": created,
        "metadata": {"container": {"tags": tags}},
    }


# ---------------------------------------------------------------------------
# parse_bool
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("text", "expected"), [("true", True), ("FALSE", False), (" True ", True)])
def test_parse_bool_accepts_true_false(text: str, expected: bool) -> None:
    assert pdi.parse_bool(text) is expected


def test_parse_bool_rejects_ambiguous() -> None:
    with pytest.raises(ValueError):
        pdi.parse_bool("${{ inputs.prune_dry_run }}")


# ---------------------------------------------------------------------------
# parse_pinned_shas
# ---------------------------------------------------------------------------


def test_parse_pinned_shas_extracts_sha(tmp_path: Path) -> None:
    sha = "a" * 40
    cfg = tmp_path / "devcontainer.json"
    cfg.write_text(
        json.dumps({"image": f"ghcr.io/tvna/claude-md-devcontainer-claude:{sha}"}),
        encoding="utf-8",
    )
    assert pdi.parse_pinned_shas([str(cfg)]) == {sha}


def test_parse_pinned_shas_ignores_non_sha_tag(tmp_path: Path) -> None:
    cfg = tmp_path / "devcontainer.json"
    cfg.write_text(json.dumps({"image": "ghcr.io/tvna/x:main"}), encoding="utf-8")
    assert pdi.parse_pinned_shas([str(cfg)]) == set()


def test_parse_pinned_shas_rejects_bad_image(tmp_path: Path) -> None:
    cfg = tmp_path / "devcontainer.json"
    cfg.write_text(json.dumps({"image": 123}), encoding="utf-8")
    with pytest.raises(ValueError):
        pdi.parse_pinned_shas([str(cfg)])


# ---------------------------------------------------------------------------
# is_protected_tag
# ---------------------------------------------------------------------------


def test_is_protected_tag_main_and_buildcache() -> None:
    assert pdi.is_protected_tag("main", set())
    assert pdi.is_protected_tag("buildcache-amd64", set())
    assert pdi.is_protected_tag("buildcache-arm64", set())


def test_is_protected_tag_pinned_sha_and_arch_variants() -> None:
    sha = "b" * 40
    pinned = {sha}
    assert pdi.is_protected_tag(sha, pinned)
    assert pdi.is_protected_tag(f"{sha}-amd64", pinned)
    assert pdi.is_protected_tag(f"{sha}-arm64", pinned)


def test_is_protected_tag_unprotected_sha() -> None:
    assert not pdi.is_protected_tag("c" * 40, {"d" * 40})


# ---------------------------------------------------------------------------
# select_versions_to_delete
# ---------------------------------------------------------------------------


def test_select_keeps_protected_and_recent_and_young() -> None:
    pinned = {"e" * 40}
    versions = [
        _version(1, ["main", "f" * 40], age_days=400),          # protected (main)
        _version(2, ["e" * 40], age_days=400),                  # protected (pinned)
        _version(3, ["buildcache-amd64"], age_days=400),        # protected (cache)
        _version(4, ["1" * 40], age_days=400),                  # old, unprotected -> delete
        _version(5, ["2" * 40], age_days=10),                   # young -> keep (age)
        _version(6, [], age_days=400),                          # untagged -> skip
    ]
    selected = pdi.select_versions_to_delete(versions, pinned, keep_recent=0, min_age_days=90, now=NOW)
    assert [v["id"] for v in selected] == [4]


def test_select_keep_recent_overrides_age() -> None:
    pinned: set[str] = set()
    # Three old unprotected versions; keep_recent=2 protects the two newest.
    versions = [
        _version(10, ["a" * 40], age_days=100),
        _version(11, ["b" * 40], age_days=200),
        _version(12, ["c" * 40], age_days=300),
    ]
    selected = pdi.select_versions_to_delete(versions, pinned, keep_recent=2, min_age_days=90, now=NOW)
    # Newest two (100d, 200d) kept; only the 300d version is deleted.
    assert [v["id"] for v in selected] == [12]


def test_select_orders_manifest_list_before_arch_children() -> None:
    sha = "9" * 40
    pinned: set[str] = set()
    versions = [
        _version(20, [f"{sha}-amd64"], age_days=400),
        _version(21, [f"{sha}-arm64"], age_days=400),
        _version(22, [sha], age_days=400),
    ]
    selected = pdi.select_versions_to_delete(versions, pinned, keep_recent=0, min_age_days=90, now=NOW)
    # The bare-SHA manifest list (id 22) must be ordered first.
    assert selected[0]["id"] == 22
    assert {v["id"] for v in selected} == {20, 21, 22}


def test_select_rejects_negative_args() -> None:
    with pytest.raises(ValueError):
        pdi.select_versions_to_delete([], set(), keep_recent=-1, min_age_days=90, now=NOW)


# ---------------------------------------------------------------------------
# cmd_prune
# ---------------------------------------------------------------------------


def _pinned_config(tmp_path: Path) -> str:
    cfg = tmp_path / "devcontainer.json"
    cfg.write_text(json.dumps({"image": "ghcr.io/tvna/x:" + "e" * 40}), encoding="utf-8")
    return str(cfg)


def test_cmd_prune_requires_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GH_TOKEN", raising=False)
    rc = pdi.main(["prune", "--owner", "o", "--package", "p", "--keep-recent", "1", "--min-age-days", "1", "--dry-run", "true"])
    assert rc == 1


def test_cmd_prune_dry_run_deletes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GH_TOKEN", "tok")
    monkeypatch.setattr(pdi, "_list_versions", lambda *a, **k: [_version(1, ["1" * 40], 400)])
    deletes: list[int] = []

    def _record_delete(*a: Any, **k: Any) -> tuple[int, str]:
        deletes.append(1)
        return 204, ""

    monkeypatch.setattr(pdi, "_delete_version", _record_delete)
    summary = tmp_path / "summary.md"
    rc = pdi.main([
        "prune",
        "--owner", "o",
        "--package", "claude-md-devcontainer-claude",
        "--pinned-sha-from", _pinned_config(tmp_path),
        "--keep-recent", "0",
        "--min-age-days", "90",
        "--dry-run", "true",
        "--summary-file", str(summary),
    ])
    assert rc == 0
    assert deletes == []
    assert "dry-run" in summary.read_text(encoding="utf-8")


def test_cmd_prune_real_delete_calls_api(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GH_TOKEN", "tok")
    monkeypatch.setattr(pdi, "_list_versions", lambda *a, **k: [_version(7, ["1" * 40], 400)])
    deleted: list[int] = []

    def _fake_delete(owner: str, package: str, version_id: int, token: str, **kw: Any) -> tuple[int, str]:
        deleted.append(version_id)
        return 204, ""

    monkeypatch.setattr(pdi, "_delete_version", _fake_delete)
    rc = pdi.main([
        "prune",
        "--owner", "o",
        "--package", "p",
        "--keep-recent", "0",
        "--min-age-days", "90",
        "--dry-run", "false",
    ])
    assert rc == 0
    assert deleted == [7]


def test_cmd_prune_reports_delete_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GH_TOKEN", "tok")
    monkeypatch.setattr(pdi, "_list_versions", lambda *a, **k: [_version(8, ["1" * 40], 400)])
    monkeypatch.setattr(pdi, "_delete_version", lambda *a, **k: (403, "forbidden"))
    rc = pdi.main([
        "prune",
        "--owner", "o",
        "--package", "p",
        "--keep-recent", "0",
        "--min-age-days", "90",
        "--dry-run", "false",
    ])
    assert rc == 1


def test_cmd_prune_list_failure_is_loud(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GH_TOKEN", "tok")

    def _boom(*a: Any, **k: Any) -> list[dict[str, Any]]:
        raise RuntimeError("HTTP 500")

    monkeypatch.setattr(pdi, "_list_versions", _boom)
    rc = pdi.main([
        "prune",
        "--owner", "o",
        "--package", "p",
        "--keep-recent", "0",
        "--min-age-days", "90",
        "--dry-run", "false",
    ])
    assert rc == 1


# ---------------------------------------------------------------------------
# _list_versions pagination (opener injection)
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, body: str) -> None:
        self.status = 200
        self._body = body.encode("utf-8")

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *exc: object) -> None:
        return None


def test_list_versions_paginates(monkeypatch: pytest.MonkeyPatch) -> None:
    page1 = [{"id": i} for i in range(pdi._PER_PAGE)]
    page2 = [{"id": 999}]
    calls: list[str] = []

    def _opener(request: Any) -> _FakeResponse:
        calls.append(request.full_url)
        body = page1 if "&page=1&" in request.full_url else page2
        return _FakeResponse(json.dumps(body))

    versions = pdi._list_versions("o", "p", "tok", opener=_opener)
    assert len(versions) == pdi._PER_PAGE + 1
    assert len(calls) == 2
