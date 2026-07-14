from __future__ import annotations

import argparse
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

# Shared fixtures for the rename decide_label_action cases.
_RENAME_FROM = "layer:p2-precode"
_RENAME_NEW: dict[str, object] = {"name": "layer:p2-input-boundary", "color": "5319e7", "description": "New"}
_RENAME_OLD: dict[str, object] = {"name": _RENAME_FROM, "color": "5319e7", "description": "Old"}


def write_sot(tmp_path: Path, entries: list[dict[str, object]]) -> Path:
    path = tmp_path / "labels.json"
    path.write_text(json.dumps(entries), encoding="utf-8")
    return path


class TestValidateSot:
    def test_happy_path(self) -> None:
        labels_apply.validate_sot(VALID_SOT)

    def test_non_list_raises(self) -> None:
        with pytest.raises(ValueError, match="JSON array"):
            labels_apply.validate_sot({"name": "x"})  # type: ignore[arg-type]

    def test_missing_name(self) -> None:
        with pytest.raises(ValueError, match="name"):
            labels_apply.validate_sot([{"color": "ffffff", "description": ""}])

    def test_bad_color(self) -> None:
        with pytest.raises(ValueError, match="type:fix"):
            labels_apply.validate_sot([{"name": "type:fix", "color": "fff", "description": ""}])

    def test_non_string_description_raises(self) -> None:
        with pytest.raises(ValueError, match="description must be a string"):
            labels_apply.validate_sot([{"name": "type:fix", "color": "ffffff", "description": 42}])

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

    def test_rename_when_old_present_new_absent(self) -> None:
        decision = labels_apply.decide_label_action(
            sot_entry=_RENAME_NEW,
            live_entry=None,
            rename_from=_RENAME_FROM,
            live_old_entry=_RENAME_OLD,
        )

        assert decision["action"] == "RENAME"
        assert decision["method"] == "PATCH"
        # PATCH targets the OLD name; new_name carries the rename in place.
        assert decision["url_suffix"] == "/labels/layer%3Ap2-precode"
        assert decision["payload"] == {
            "new_name": "layer:p2-input-boundary",
            "color": "5319e7",
            "description": "New",
        }
        assert decision["color_changed"] is False
        assert decision["desc_changed"] is True

    def test_conflict_when_old_and_new_both_present(self) -> None:
        decision = labels_apply.decide_label_action(
            sot_entry=_RENAME_NEW,
            live_entry=_RENAME_NEW,
            rename_from=_RENAME_FROM,
            live_old_entry=_RENAME_OLD,
        )

        assert decision["action"] == "CONFLICT"
        assert decision["payload"] is None

    def test_rename_already_done_is_noop(self) -> None:
        # Old gone, new present and matching: an idempotent rerun must not act.
        decision = labels_apply.decide_label_action(
            sot_entry=_RENAME_NEW,
            live_entry=_RENAME_NEW,
            rename_from=_RENAME_FROM,
            live_old_entry=None,
        )

        assert decision["action"] == "NOOP"

    def test_rename_source_absent_creates_new(self) -> None:
        # Neither old nor new exists: fall through to a plain POST.
        decision = labels_apply.decide_label_action(
            sot_entry=_RENAME_NEW,
            live_entry=None,
            rename_from=_RENAME_FROM,
            live_old_entry=None,
        )

        assert decision["action"] == "POST"


class TestLoadRenameMap:
    def test_collects_rename_entries_only(self, tmp_path: Path) -> None:
        policy = tmp_path / "label-policy.toml"
        policy.write_text(
            "\n".join(
                [
                    "[[labels]]",
                    'name = "layer:p2-input-boundary"',
                    'status = "rename"',
                    'rename_from = "layer:p2-precode"',
                    "",
                    "[[labels]]",
                    'name = "type:fix"',
                    'status = "keep"',
                    "",
                    "[[labels]]",
                    'name = "ops:dependencies"',
                    'rename_from = "dependencies"',
                ]
            ),
            encoding="utf-8",
        )

        assert labels_apply.load_rename_map(policy) == {
            "layer:p2-input-boundary": "layer:p2-precode",
            "ops:dependencies": "dependencies",
        }


class TestLoadSotFromPolicy:
    def _write_policy(self, tmp_path: Path, body: str) -> Path:
        policy = tmp_path / "label-policy.toml"
        policy.write_text(body, encoding="utf-8")
        return policy

    def test_keeps_keep_and_rename_excludes_add(self, tmp_path: Path) -> None:
        policy = self._write_policy(
            tmp_path,
            "\n".join(
                [
                    "[[labels]]",
                    'name = "type:fix"',
                    'status = "keep"',
                    'description = "Defect or broken workflow."',
                    'color = "d73a4a"',
                    "",
                    "[[labels]]",
                    'name = "layer:p2-input-boundary"',
                    'status = "rename"',
                    'rename_from = "layer:p2-precode"',
                    'description = "Renamed layer."',
                    'color = "5319e7"',
                    "",
                    "[[labels]]",
                    'name = "area:apm"',
                    'status = "add"',
                    'description = "Design-only, not live yet."',
                    'color = "5319e7"',
                ]
            ),
        )

        catalog = labels_apply.load_sot_from_policy(policy)

        names = {entry["name"] for entry in catalog}
        assert names == {"type:fix", "layer:p2-input-boundary"}
        assert "area:apm" not in names

    def test_result_passes_validate_sot(self, tmp_path: Path) -> None:
        policy = self._write_policy(
            tmp_path,
            "\n".join(
                [
                    "[[labels]]",
                    'name = "type:fix"',
                    'status = "keep"',
                    'description = "Defect or broken workflow."',
                    'color = "d73a4a"',
                ]
            ),
        )

        catalog = labels_apply.load_sot_from_policy(policy)

        labels_apply.validate_sot(catalog)  # must not raise

    def test_duplicate_live_name_raises_value_error(self, tmp_path: Path) -> None:
        policy = self._write_policy(
            tmp_path,
            "\n".join(
                [
                    "[[labels]]",
                    'name = "type:fix"',
                    'status = "keep"',
                    'description = "First copy."',
                    'color = "d73a4a"',
                    "",
                    "[[labels]]",
                    'name = "type:fix"',
                    'status = "keep"',
                    'description = "Second copy."',
                    'color = "d73a4a"',
                ]
            ),
        )

        with pytest.raises(ValueError, match="type:fix"):
            labels_apply.load_sot_from_policy(policy)

    def test_unrecognized_status_raises_value_error(self, tmp_path: Path) -> None:
        policy = self._write_policy(
            tmp_path,
            "\n".join(
                [
                    "[[labels]]",
                    'name = "type:fix"',
                    'status = "Keep"',
                    'description = "Typo-cased status."',
                    'color = "d73a4a"',
                ]
            ),
        )

        with pytest.raises(ValueError, match="status"):
            labels_apply.load_sot_from_policy(policy)


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


def test_policy_derived_catalog_matches_labels_json_exactly() -> None:
    """Integration proof for #2442 Phase B batch 1: the TOML-derived live
    catalog and labels.json must describe the exact same label set. This is
    the direct evidence the issue's Verification section asks for (apply
    plan is the same whether sourced from labels.json or the TOML)."""
    repo_root = Path(__file__).resolve().parents[1]
    policy_path = repo_root / ".github" / "label-policy.toml"
    labels_json_path = repo_root / ".github" / "labels.json"

    derived = labels_apply.load_sot_from_policy(policy_path)
    direct = labels_apply.load_sot(labels_json_path)

    def _key(entry: dict[str, object]) -> tuple[object, object, object]:
        return (entry["name"], entry["color"], entry["description"])

    assert sorted(derived, key=_key) == sorted(direct, key=_key)


def test_render_action_row_escapes_pipes() -> None:
    assert labels_apply.render_action_row("a|b", "plan-only (POST)", "n/a", "n/a", "dry-run") == (
        "| `a\\|b` | plan-only (POST) | n/a | n/a | dry-run |"
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


class TestResolveSot:
    def test_labels_json_default(self) -> None:
        args = argparse.Namespace(source="labels-json", sot=Path("a/labels.json"), policy=Path("a/policy.toml"))

        sot_path, sot_loader = labels_apply._resolve_sot(args)

        assert sot_path == Path("a/labels.json")
        assert sot_loader is labels_apply.load_sot

    def test_label_policy_uses_policy_derived_loader(self, tmp_path: Path) -> None:
        policy = tmp_path / "label-policy.toml"
        policy.write_text(
            "\n".join(
                [
                    "[[labels]]",
                    'name = "type:fix"',
                    'status = "keep"',
                    'description = "Defect or broken workflow."',
                    'color = "d73a4a"',
                ]
            ),
            encoding="utf-8",
        )
        labels_json = tmp_path / "labels.json"
        args = argparse.Namespace(source="label-policy", sot=labels_json, policy=policy)

        sot_path, sot_loader = labels_apply._resolve_sot(args)

        assert sot_path == policy
        assert sot_loader is labels_apply.load_sot_from_policy
        names = {entry["name"] for entry in sot_loader(sot_path)}
        assert names == {"type:fix"}


def test_source_flag_help_documents_staged_migration() -> None:
    parser = argparse.ArgumentParser()
    labels_apply._add_common_args(parser)

    help_text = parser.format_help()

    assert "2442" in help_text


def test_main_source_label_policy_uses_policy_derived_catalog(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    policy = tmp_path / "label-policy.toml"
    policy.write_text(
        "\n".join(
            [
                "[[labels]]",
                'name = "type:fix"',
                'status = "keep"',
                'description = "Defect or broken workflow."',
                'color = "d73a4a"',
            ]
        ),
        encoding="utf-8",
    )
    labels_json = tmp_path / "labels.json"
    labels_json.write_text(json.dumps([]), encoding="utf-8")
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GH_TOKEN", "token")

    calls: list[dict[str, object]] = []

    def fake_fetch_live_labels(repo: str, token: str, **kwargs: object) -> list[dict[str, object]]:
        calls.append({"repo": repo, "token": token})
        return []

    monkeypatch.setattr(labels_apply, "fetch_live_labels", fake_fetch_live_labels)

    result = labels_apply.main(
        [
            "plan",
            "--repo",
            "owner/repo",
            "--sot",
            str(labels_json),
            "--policy",
            str(policy),
            "--source",
            "label-policy",
            "--dry-run",
            "true",
            "--prune",
            "false",
            "--summary-file",
            str(summary),
        ]
    )

    text = summary.read_text(encoding="utf-8")
    assert result == 0
    assert "| `type:fix` | plan-only (POST) | n/a | n/a | dry-run |" in text


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
        assert "| `new` | plan-only (POST) | n/a | n/a | dry-run |" in text
        assert "| `changed` | plan-only (PATCH) | yes | no | dry-run |" in text
        assert "| `same` | no-op | no | no | unchanged |" in text
        assert "| `old` | report-only (not in SoT) | n/a | n/a | kept (prune=false) |" in text

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

    def test_plan_renames_in_place_and_protects_old_from_prune(self, tmp_path: Path) -> None:
        sot = write_sot(
            tmp_path,
            [{"name": "layer:p2-input-boundary", "color": "5319e7", "description": "New"}],
        )
        summary = tmp_path / "summary.md"

        result = labels_apply.run(
            mode="plan",
            repo="owner/repo",
            sot_path=sot,
            prune=True,
            dry_run=True,
            summary_file=summary,
            token="token",
            live_labels=[{"name": "layer:p2-precode", "color": "5319e7", "description": "Old"}],
            rename_map={"layer:p2-input-boundary": "layer:p2-precode"},
        )

        text = summary.read_text(encoding="utf-8")
        assert result == 0
        assert "| `layer:p2-input-boundary` | plan-only (RENAME) |" in text
        # The old name is a rename source; prune must not target it (no data loss).
        assert "plan-only (DELETE)" not in text

    def test_apply_renames_via_new_name_patch(self, tmp_path: Path) -> None:
        sot = write_sot(
            tmp_path,
            [{"name": "ops:dependencies", "color": "0366d6", "description": "Deps"}],
        )
        calls: list[dict[str, object]] = []

        def apply_call(**kwargs: object) -> tuple[int, str]:
            calls.append(kwargs)
            return 200, "{}"

        result = labels_apply.run(
            mode="apply",
            repo="owner/repo",
            sot_path=sot,
            prune=True,
            dry_run=False,
            summary_file=tmp_path / "summary.md",
            token="token",
            live_labels=[{"name": "dependencies", "color": "0366d6", "description": "Deps"}],
            rename_map={"ops:dependencies": "dependencies"},
            apply_call=apply_call,
        )

        assert result == 0
        assert calls == [
            {
                "method": "PATCH",
                "url": "https://api.github.com/repos/owner/repo/labels/dependencies",
                "payload": {"new_name": "ops:dependencies", "color": "0366d6", "description": "Deps"},
                "token": "token",
            }
        ]

    def test_plan_uses_custom_sot_loader(self, tmp_path: Path) -> None:
        # sot_path is passed through to the loader unchanged; the loader's
        # return value becomes the SoT, without labels_apply.py touching
        # any file itself.
        sot = tmp_path / "unused-marker.txt"
        sot.write_text("not read directly", encoding="utf-8")
        summary = tmp_path / "summary.md"
        received_paths: list[Path] = []

        def fake_loader(path: Path) -> list[dict[str, object]]:
            received_paths.append(path)
            return [{"name": "from-loader", "color": "ffffff", "description": "From loader"}]

        result = labels_apply.run(
            mode="plan",
            repo="owner/repo",
            sot_path=sot,
            prune=False,
            dry_run=True,
            summary_file=summary,
            token="token",
            live_labels=[],
            sot_loader=fake_loader,
        )

        text = summary.read_text(encoding="utf-8")
        assert result == 0
        assert received_paths == [sot]
        assert "| `from-loader` | plan-only (POST) | n/a | n/a | dry-run |" in text

    def test_apply_conflict_aborts_when_both_names_live(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        sot = write_sot(
            tmp_path,
            [{"name": "ops:dependencies", "color": "0366d6", "description": "Deps"}],
        )

        def apply_call(**kwargs: object) -> tuple[int, str]:
            raise AssertionError("must not touch the API on a rename conflict")

        result = labels_apply.run(
            mode="apply",
            repo="owner/repo",
            sot_path=sot,
            prune=False,
            dry_run=False,
            summary_file=tmp_path / "summary.md",
            token="token",
            live_labels=[
                {"name": "ops:dependencies", "color": "0366d6", "description": "Deps"},
                {"name": "dependencies", "color": "0366d6", "description": "Deps"},
            ],
            rename_map={"ops:dependencies": "dependencies"},
            apply_call=apply_call,
        )

        assert result == 1
        assert "Cannot rename 'dependencies' to 'ops:dependencies'" in capsys.readouterr().out
