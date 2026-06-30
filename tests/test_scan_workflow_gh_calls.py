"""Tests for ``scripts/scan_workflow_gh_calls.py``.

The ``scripts/`` directory is added to ``sys.path`` via the
``pythonpath`` key under ``[tool.pytest.ini_options]`` in
``pyproject.toml``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import scan_workflow_gh_calls as swgc
import yaml

pytestmark = pytest.mark.shard_ci_ops

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"

_REQUIRED_KEYS = {"workflow", "step", "rationale"}


# ---------------------------------------------------------------------------
# Allowlist structure invariants
# ---------------------------------------------------------------------------


class TestAllowlistEntries:
    def test_all_required_keys_present(self) -> None:
        for i, entry in enumerate(swgc.ALLOWLIST_ENTRIES):
            missing = _REQUIRED_KEYS - entry.keys()
            assert not missing, f"entry[{i}] missing keys: {missing!r}; {entry}"

    def test_all_values_are_non_empty_strings(self) -> None:
        for i, entry in enumerate(swgc.ALLOWLIST_ENTRIES):
            for key in _REQUIRED_KEYS:
                assert isinstance(entry[key], str) and entry[key].strip(), (
                    f"entry[{i}][{key!r}] is empty or not a string"
                )

    def test_rationale_references_tracking_issue(self) -> None:
        for i, entry in enumerate(swgc.ALLOWLIST_ENTRIES):
            assert "#" in entry["rationale"], (
                f"entry[{i}] rationale must cite a tracking issue: {entry['rationale']!r}"
            )

    def test_no_duplicate_workflow_step_pairs(self) -> None:
        seen: set[tuple[str, str]] = set()
        for i, entry in enumerate(swgc.ALLOWLIST_ENTRIES):
            key = (entry["workflow"], entry["step"])
            assert key not in seen, f"entry[{i}] duplicates key {key!r}"
            seen.add(key)

    def test_allowlist_keys_derived_from_entries(self) -> None:
        expected = frozenset((e["workflow"], e["step"]) for e in swgc.ALLOWLIST_ENTRIES)
        assert expected == swgc._ALLOWLIST_KEYS


# ---------------------------------------------------------------------------
# _iter_run_steps
# ---------------------------------------------------------------------------


class TestIterRunSteps:
    def test_yields_step_with_run_block(self, tmp_path: Path) -> None:
        wf = tmp_path / "foo.yml"
        wf.write_text(
            "jobs:\n  build:\n    steps:\n      - name: Say hi\n        run: echo hello\n",
            encoding="utf-8",
        )
        results = list(swgc._iter_run_steps(tmp_path))
        assert results == [("foo.yml", "build", "Say hi", "echo hello")]

    def test_skips_step_with_uses_not_run(self, tmp_path: Path) -> None:
        wf = tmp_path / "bar.yml"
        wf.write_text(
            "jobs:\n  build:\n    steps:\n      - name: Checkout\n        uses: actions/checkout@abc\n",
            encoding="utf-8",
        )
        assert list(swgc._iter_run_steps(tmp_path)) == []

    def test_step_with_no_name_yields_empty_step_name(self, tmp_path: Path) -> None:
        wf = tmp_path / "anon.yml"
        wf.write_text(
            "jobs:\n  build:\n    steps:\n      - run: echo hi\n",
            encoding="utf-8",
        )
        results = list(swgc._iter_run_steps(tmp_path))
        assert len(results) == 1
        assert results[0][2] == ""  # step_name is empty

    def test_skips_unparseable_file(self, tmp_path: Path) -> None:
        wf = tmp_path / "bad.yml"
        wf.write_text(": - invalid: yaml: [[\n", encoding="utf-8")
        assert list(swgc._iter_run_steps(tmp_path)) == []

    def test_multiline_run_block(self, tmp_path: Path) -> None:
        wf = tmp_path / "multi.yml"
        wf.write_text(
            "jobs:\n  j:\n    steps:\n      - name: Multi\n        run: |\n          echo a\n          echo b\n",
            encoding="utf-8",
        )
        results = list(swgc._iter_run_steps(tmp_path))
        assert len(results) == 1
        assert "echo a" in results[0][3]


# ---------------------------------------------------------------------------
# find_violations
# ---------------------------------------------------------------------------


def _write_wf(tmp_path: Path, name: str, content: str) -> Path:
    wf = tmp_path / name
    wf.write_text(content, encoding="utf-8")
    return wf


class TestFindViolations:
    def test_returns_empty_for_clean_workflow(self, tmp_path: Path) -> None:
        _write_wf(
            tmp_path,
            "clean.yml",
            "jobs:\n  j:\n    steps:\n      - name: Run tests\n        run: pytest\n",
        )
        assert swgc.find_violations(tmp_path) == []

    def test_detects_unallowlisted_gh_call(self, tmp_path: Path) -> None:
        _write_wf(
            tmp_path,
            "new.yml",
            "jobs:\n  j:\n    steps:\n      - name: Create PR\n        run: gh pr create --title foo\n",
        )
        violations = swgc.find_violations(tmp_path)
        assert len(violations) == 1
        v = violations[0]
        assert v.workflow == "new.yml"
        assert v.step == "Create PR"
        assert "gh pr" in v.fragment

    def test_allowlisted_step_produces_no_violation(self, tmp_path: Path) -> None:
        if not swgc.ALLOWLIST_ENTRIES:
            pytest.skip("ALLOWLIST_ENTRIES is empty; no entries to validate")
        first = swgc.ALLOWLIST_ENTRIES[0]
        content = yaml.dump(
            {
                "jobs": {
                    "j": {
                        "steps": [
                            {
                                "name": first["step"],
                                "run": "gh pr create --title test",
                            }
                        ]
                    }
                }
            }
        )
        _write_wf(tmp_path, first["workflow"], content)
        assert swgc.find_violations(tmp_path) == []

    def test_unnamed_step_with_gh_call_is_violation(self, tmp_path: Path) -> None:
        _write_wf(
            tmp_path,
            "unnamed.yml",
            "jobs:\n  j:\n    steps:\n      - run: gh pr merge --auto\n",
        )
        violations = swgc.find_violations(tmp_path)
        assert len(violations) == 1
        assert violations[0].step == ""

    def test_detects_gh_call_split_across_continuation(self, tmp_path: Path) -> None:
        # `gh \` then `pr create` splits the command across a `\` continuation;
        # flattening must rejoin it so the gate still fires (issue #2164).
        _write_wf(
            tmp_path,
            "cont.yml",
            "jobs:\n  j:\n    steps:\n      - name: Create PR\n"
            "        run: |\n          gh \\\n            pr create --title foo\n",
        )
        violations = swgc.find_violations(tmp_path)
        assert len(violations) == 1
        assert violations[0].kind == "gh"


class TestScanRunText:
    def test_gh_continuation_is_caught(self) -> None:
        assert swgc.scan_run_text("gh \\\n  api repos/o/r")[0][0] == "gh"

    def test_curl_to_api_continuation_is_caught(self) -> None:
        hits = swgc.scan_run_text("curl \\\n  https://api.github.com/repos/o/r")
        assert any(kind == "curl" for kind, _ in hits)

    def test_clean_run_text_has_no_hits(self) -> None:
        assert swgc.scan_run_text("pytest -q\nuv sync --locked") == []

    def test_no_violations_in_current_workflows(self) -> None:
        violations = swgc.find_violations(WORKFLOW_DIR)
        assert violations == [], (
            "Unallowlisted gh CLI calls or direct GitHub-API curls found in current workflows:\n"
            + "\n".join(
                f"  ({v.kind}) {v.workflow} / {v.job} / {v.step!r}: {v.fragment!r}"
                for v in violations
            )
            + "\n\nEither migrate the call to a tested Python script, or add an"
            " allowlist entry with rationale in scripts/scan_workflow_gh_calls.py."
        )


# ---------------------------------------------------------------------------
# curl-to-GitHub-API detection (Refs #911)
# ---------------------------------------------------------------------------


class TestCurlGitHubApi:
    def test_detects_curl_to_api_github_com(self, tmp_path: Path) -> None:
        _write_wf(
            tmp_path,
            "curl.yml",
            "jobs:\n  j:\n    steps:\n      - name: Post comment\n"
            '        run: curl -X POST "https://api.github.com/repos/o/r/issues/1/comments"\n',
        )
        violations = swgc.find_violations(tmp_path)
        assert len(violations) == 1
        assert violations[0].kind == "curl"
        assert violations[0].step == "Post comment"
        assert "api.github.com" in violations[0].fragment

    def test_detects_multiline_curl_to_api(self, tmp_path: Path) -> None:
        _write_wf(
            tmp_path,
            "multi.yml",
            "jobs:\n  j:\n    steps:\n      - name: Post\n        run: |\n"
            "          curl -sS -X POST \\\n"
            '            "https://api.github.com/repos/o/r/issues/1/comments"\n',
        )
        violations = swgc.find_violations(tmp_path)
        assert len(violations) == 1
        assert violations[0].kind == "curl"

    def test_detects_uploads_github_com(self, tmp_path: Path) -> None:
        _write_wf(
            tmp_path,
            "up.yml",
            "jobs:\n  j:\n    steps:\n      - name: Upload\n"
            '        run: curl -X POST "https://uploads.github.com/x"\n',
        )
        assert swgc.find_violations(tmp_path)[0].kind == "curl"

    def test_uv_release_download_is_not_violation(self, tmp_path: Path) -> None:
        _write_wf(
            tmp_path,
            "uv.yml",
            "jobs:\n  j:\n    steps:\n      - name: Install uv\n"
            '        run: curl -LsSf "https://github.com/astral-sh/uv/releases/download/0.1/uv.tar.gz" -o /tmp/uv.tar.gz\n',
        )
        assert swgc.find_violations(tmp_path) == []

    def test_api_github_com_without_curl_is_not_violation(self, tmp_path: Path) -> None:
        # A python script call that happens to mention the host is fine.
        _write_wf(
            tmp_path,
            "py.yml",
            "jobs:\n  j:\n    steps:\n      - name: Fetch\n"
            "        run: python3 scripts/github_paginate.py get --path repos/o/r --field x\n",
        )
        assert swgc.find_violations(tmp_path) == []

    def test_curl_to_other_host_is_not_violation(self, tmp_path: Path) -> None:
        _write_wf(
            tmp_path,
            "other.yml",
            "jobs:\n  j:\n    steps:\n      - name: Ping\n"
            '        run: curl "https://example.com/health"\n',
        )
        assert swgc.find_violations(tmp_path) == []

    def test_curl_violation_suppressed_when_allowlisted(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            swgc,
            "_ALLOWLIST_KEYS",
            frozenset({("curl.yml", "Post comment")}),
        )
        _write_wf(
            tmp_path,
            "curl.yml",
            "jobs:\n  j:\n    steps:\n      - name: Post comment\n"
            '        run: curl -X POST "https://api.github.com/x"\n',
        )
        assert swgc.find_violations(tmp_path) == []

    def test_list_reports_curl_kind(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _write_wf(
            tmp_path,
            "curl.yml",
            "jobs:\n  j:\n    steps:\n      - name: Post\n"
            '        run: curl "https://api.github.com/x"\n',
        )
        monkeypatch.setattr(swgc, "WORKFLOW_DIR", tmp_path)
        assert swgc.main(["list"]) == 0
        assert "(curl)" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# main CLI
# ---------------------------------------------------------------------------


class TestMain:
    def test_verify_exits_0_for_clean_directory(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _write_wf(tmp_path, "ok.yml", "jobs:\n  j:\n    steps:\n      - name: x\n        run: echo hi\n")
        monkeypatch.setattr(swgc, "WORKFLOW_DIR", tmp_path)
        assert swgc.main(["verify"]) == 0

    def test_verify_exits_1_on_violation(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _write_wf(tmp_path, "bad.yml", "jobs:\n  j:\n    steps:\n      - name: x\n        run: gh pr create\n")
        monkeypatch.setattr(swgc, "WORKFLOW_DIR", tmp_path)
        assert swgc.main(["verify"]) == 1

    def test_list_exits_0(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        _write_wf(tmp_path, "x.yml", "jobs:\n  j:\n    steps:\n      - name: y\n        run: gh issue list\n")
        monkeypatch.setattr(swgc, "WORKFLOW_DIR", tmp_path)
        rc = swgc.main(["list"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "gh issue" in out

    def test_verify_on_current_repo_exits_0(self) -> None:
        assert swgc.main(["verify"]) == 0
