from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import labels_apply

pytestmark = pytest.mark.shard_ci_ops

class Response:
    def __init__(self, payload: object) -> None:
        self.payload = json.dumps(payload).encode()
        self.status = 200

    def __enter__(self) -> Response:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self.payload

    def close(self) -> None:
        return None


VALID_SOT: list[dict[str, object]] = [{"name": "type:fix", "color": "d73a4a", "description": "Bug fix"}]


def write_sot(tmp_path: Path, entries: list[dict[str, object]]) -> Path:
    path = tmp_path / "labels.json"
    path.write_text(json.dumps(entries), encoding="utf-8")
    return path


class TestValidateSot:
    def test_happy_path(self) -> None:
        labels_apply.validate_sot(VALID_SOT)

    def test_missing_name(self) -> None:
        with pytest.raises(ValueError, match="name"):
            labels_apply.validate_sot([{"color": "ffffff", "description": ""}])

    def test_bad_color(self) -> None:
        with pytest.raises(ValueError, match="type:fix"):
            labels_apply.validate_sot([{"name": "type:fix", "color": "fff", "description": ""}])

    def test_description_over_100_chars_names_offender(self) -> None:
        with pytest.raises(ValueError, match="type:fix"):
            labels_apply.validate_sot([{"name": "type:fix", "color": "ffffff", "description": "x" * 101}])


class TestDecideLabelAction:
    def test_post_when_missing(self) -> None:
        decision = labels_apply.decide_label_action(sot_entry=VALID_SOT[0], live_entry=None)

        assert decision["action"] == "POST"
        assert decision["method"] == "POST"
        assert decision["url_suffix"] == "/labels"
        assert decision["payload"] == {"name": "type:fix", "color": "d73a4a", "description": "Bug fix"}

    @pytest.mark.parametrize(
        ("live", "color_changed", "desc_changed"),
        [
            ({"name": "type:fix", "color": "000000", "description": "Bug fix"}, True, False),
            ({"name": "type:fix", "color": "d73a4a", "description": "Old"}, False, True),
            ({"name": "type:fix", "color": "000000", "description": "Old"}, True, True),
            ({"name": "type:fix", "color": "d73a4a", "description": None}, False, True),
        ],
    )
    def test_patch_when_fields_differ(self, live: dict[str, object], color_changed: bool, desc_changed: bool) -> None:
        decision = labels_apply.decide_label_action(sot_entry=VALID_SOT[0], live_entry=live)

        assert decision["action"] == "PATCH"
        assert decision["method"] == "PATCH"
        assert decision["url_suffix"] == "/labels/type%3Afix"
        assert decision["payload"] == {"color": "d73a4a", "description": "Bug fix"}
        assert decision["color_changed"] is color_changed
        assert decision["desc_changed"] is desc_changed

    def test_noop_when_matching(self) -> None:
        decision = labels_apply.decide_label_action(sot_entry=VALID_SOT[0], live_entry=VALID_SOT[0])

        assert decision["action"] == "NOOP"
        assert decision["payload"] is None


class TestDecidePruneAction:
    @pytest.mark.parametrize(
        ("in_sot", "prune", "dry_run", "expected"),
        [
            (True, False, False, "skip"),
            (True, True, False, "skip"),
            (False, False, False, "report"),
            (False, False, True, "report"),
            (False, True, True, "plan-delete"),
            (False, True, False, "delete"),
        ],
    )
    def test_truth_table(self, in_sot: bool, prune: bool, dry_run: bool, expected: str) -> None:
        assert (
            labels_apply.decide_prune_action(live_name="old", in_sot=in_sot, prune=prune, dry_run=dry_run)
            == expected
        )


def test_render_action_row_escapes_pipes() -> None:
    assert labels_apply.render_action_row("a|b", "plan-only (POST)", "—", "—", "dry-run") == (
        "| `a\\|b` | plan-only (POST) | — | — | dry-run |"
    )


class TestFetchLiveLabels:
    def test_happy_path_and_auth_header(self) -> None:
        requests: list[urllib.request.Request] = []

        def opener(request: urllib.request.Request) -> Response:
            requests.append(request)
            return Response([{"name": "type:fix"}])

        labels = labels_apply.fetch_live_labels("owner/repo", "secret", opener=opener)

        assert labels == [{"name": "type:fix"}]
        assert requests[0].full_url == "https://api.github.com/repos/owner/repo/labels?per_page=100"
        assert requests[0].headers["Authorization"] == "Bearer secret"

    def test_length_guard(self) -> None:
        def opener(request: urllib.request.Request) -> Response:
            return Response([{"name": str(i)} for i in range(100)])

        with pytest.raises(RuntimeError, match="pagination required but not implemented"):
            labels_apply.fetch_live_labels("owner/repo", "secret", opener=opener)

    def test_does_not_paginate_when_under_guard_threshold(self) -> None:
        # Characterization: at 99 results (one below the >=100 guard) the
        # function returns directly without issuing a second page request.
        # Future paginator PRs must update this test to flip the contract.
        calls = 0

        def opener(request: urllib.request.Request) -> Response:
            nonlocal calls
            calls += 1
            return Response([{"name": str(i)} for i in range(99)])

        labels = labels_apply.fetch_live_labels("owner/repo", "secret", opener=opener)

        assert len(labels) == 99
        assert calls == 1


class TestCli:
    def test_plan_mixed_actions(self, tmp_path: Path) -> None:
        sot = write_sot(
            tmp_path,
            [
                {"name": "new", "color": "ffffff", "description": "New"},
                {"name": "changed", "color": "000000", "description": "Changed"},
                {"name": "same", "color": "111111", "description": "Same"},
            ],
        )
        summary = tmp_path / "summary.md"

        result = labels_apply.run(
            mode="plan",
            repo="owner/repo",
            sot_path=sot,
            prune=False,
            dry_run=True,
            summary_file=summary,
            token="token",
            live_labels=[
                {"name": "changed", "color": "ffffff", "description": "Changed"},
                {"name": "same", "color": "111111", "description": "Same"},
                {"name": "old", "color": "222222", "description": "Old"},
            ],
        )

        text = summary.read_text(encoding="utf-8")
        assert result == 0
        assert "| `new` | plan-only (POST) | — | — | dry-run |" in text
        assert "| `changed` | plan-only (PATCH) | yes | no | dry-run |" in text
        assert "| `same` | no-op | no | no | unchanged |" in text
        assert "| `old` | report-only (not in SoT) | — | — | kept (prune=false) |" in text

    def test_apply_posts_patches_and_aborts_on_failure(self, tmp_path: Path) -> None:
        sot = write_sot(
            tmp_path,
            [
                {"name": "new", "color": "ffffff", "description": "New"},
                {"name": "changed", "color": "000000", "description": "Changed"},
            ],
        )
        calls: list[dict[str, object]] = []

        def apply_call(**kwargs: object) -> tuple[int, str]:
            calls.append(kwargs)
            if len(calls) == 2:
                return 503, "nope"
            return 201, '{"id":1}'

        result = labels_apply.run(
            mode="apply",
            repo="owner/repo",
            sot_path=sot,
            prune=False,
            dry_run=False,
            summary_file=tmp_path / "summary.md",
            token="token",
            live_labels=[{"name": "changed", "color": "ffffff", "description": "Changed"}],
            apply_call=apply_call,
        )

        assert result == 1
        assert [call["method"] for call in calls] == ["POST", "PATCH"]
        assert calls[0]["url"] == "https://api.github.com/repos/owner/repo/labels"
        assert calls[1]["url"] == "https://api.github.com/repos/owner/repo/labels/changed"

    def test_apply_aborts_on_403_without_leaking_token(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        sot = write_sot(tmp_path, [{"name": "new", "color": "ffffff", "description": "New"}])

        def apply_call(**kwargs: object) -> tuple[int, str]:
            return 403, '{"message":"Resource not accessible by integration"}'

        result = labels_apply.run(
            mode="apply",
            repo="owner/repo",
            sot_path=sot,
            prune=False,
            dry_run=False,
            summary_file=tmp_path / "summary.md",
            token="sentinel-secret-TOKEN",
            live_labels=[],
            apply_call=apply_call,
        )

        captured = capsys.readouterr()
        assert result == 1
        assert "::error::Failed to POST label 'new' (last HTTP 403)." in captured.out
        assert "sentinel-secret-TOKEN" not in captured.out
        assert "sentinel-secret-TOKEN" not in captured.err

    def test_apply_with_prune_deletes_live_not_in_sot(self, tmp_path: Path) -> None:
        sot = write_sot(tmp_path, VALID_SOT)
        calls: list[dict[str, object]] = []

        def apply_call(**kwargs: object) -> tuple[int, str]:
            calls.append(kwargs)
            return 204, ""

        result = labels_apply.run(
            mode="apply",
            repo="owner/repo",
            sot_path=sot,
            prune=True,
            dry_run=False,
            summary_file=tmp_path / "summary.md",
            token="token",
            live_labels=[VALID_SOT[0], {"name": "old label", "color": "ffffff", "description": ""}],
            apply_call=apply_call,
        )

        assert result == 0
        assert calls == [
            {
                "method": "DELETE",
                "url": "https://api.github.com/repos/owner/repo/labels/old%20label",
                "payload": None,
                "token": "token",
            }
        ]
