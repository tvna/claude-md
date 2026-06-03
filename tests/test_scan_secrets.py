"""Tests for ``scripts/scan_secrets.py``.

The ``scripts/`` directory is added to ``sys.path`` via the ``pythonpath``
key under ``[tool.pytest.ini_options]`` in ``pyproject.toml``.

Synthetic tokens below are deliberately fake and live in this ``*.py``
test, which the scanner excludes, so they never self-trip the gate.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import scan_secrets

pytestmark = pytest.mark.shard_ci_ops
REPO_ROOT = Path(__file__).resolve().parents[1]

# Fake, structurally-valid tokens assembled at runtime so neither this gate
# nor ruff's S family treats them as real assignments.
_FAKE_GHP = "ghp_" + "a1b2c3d4" * 4 + "wxyz"  # ghp_ + 36 chars
_FAKE_AKIA = "AKIA" + "ABCD1234EFGH5678"
_FAKE_AIZA = "AIza" + "B" * 35
_FAKE_XOXB = "xoxb-" + "1234567890" + "-abcdef"


# ---------------------------------------------------------------------------
# scan_line: vendor-prefixed rules
# ---------------------------------------------------------------------------


class TestVendorRules:
    def test_github_token(self) -> None:
        assert scan_secrets.scan_line(f"key = {_FAKE_GHP}") == "github-token"

    def test_github_fine_grained_pat(self) -> None:
        token = "github_pat_" + "A1b2" * 10
        assert scan_secrets.scan_line(token) == "github-fine-grained-pat"

    def test_aws_access_key(self) -> None:
        assert scan_secrets.scan_line(_FAKE_AKIA) == "aws-access-key-id"

    def test_google_api_key(self) -> None:
        assert scan_secrets.scan_line(_FAKE_AIZA) == "google-api-key"

    def test_slack_token(self) -> None:
        assert scan_secrets.scan_line(_FAKE_XOXB) == "slack-token"

    def test_private_key_header(self) -> None:
        assert (
            scan_secrets.scan_line("-----BEGIN OPENSSH PRIVATE KEY-----")
            == "private-key"
        )
        assert (
            scan_secrets.scan_line("-----BEGIN PRIVATE KEY-----")
            == "private-key"
        )


# ---------------------------------------------------------------------------
# scan_line: generic assignment rule + guards
# ---------------------------------------------------------------------------


class TestGenericRule:
    def test_flags_high_entropy_literal(self) -> None:
        line = 'api_key = "a1b2c3d4e5f6g7h8x9"'
        assert scan_secrets.scan_line(line) == "generic-assignment"

    def test_yaml_colon_form(self) -> None:
        line = 'password: "s3cr3tValue01234567"'
        assert scan_secrets.scan_line(line) == "generic-assignment"

    @pytest.mark.parametrize(
        "line",
        [
            # interpolation, not a literal
            'token: "${{ secrets.GITHUB_TOKEN }}"',
            'password = "$ENV_PASSWORD"',
            'api_key: "{{ vault_api_key }}"',
            # placeholder words
            'secret = "your_secret_here"',
            'token = "example-token-value-123"',
            'password = "changeme-now-123456"',
            # too short
            'token = "abc123"',
            # no digit/letter mix (all letters)
            'secret = "loremipsumdolorsit"',
            # key present but value is an env-var reference style
            'access_key = "<set-in-ci>"',
        ],
    )
    def test_ignores_non_secret_values(self, line: str) -> None:
        assert scan_secrets.scan_line(line) is None

    def test_unrelated_assignment_not_flagged(self) -> None:
        assert scan_secrets.scan_line('name = "build-and-test-123"') is None


# ---------------------------------------------------------------------------
# pragma + _looks_like_secret_value
# ---------------------------------------------------------------------------


class TestPragmaAndGuards:
    def test_pragma_allowlist_skips_line(self) -> None:
        line = f"key = {_FAKE_GHP}  # pragma: allowlist secret"
        assert scan_secrets.scan_line(line) is None

    def test_looks_like_secret_value_true(self) -> None:
        assert scan_secrets._looks_like_secret_value("a1b2c3d4e5f6g7h8")

    @pytest.mark.parametrize(
        "value",
        ["short1", "alllowercaseletters", "1234567890123456", "${VAR}"],
    )
    def test_looks_like_secret_value_false(self, value: str) -> None:
        assert not scan_secrets._looks_like_secret_value(value)


# ---------------------------------------------------------------------------
# scan_text
# ---------------------------------------------------------------------------


class TestScanText:
    def test_returns_empty_when_clean(self) -> None:
        assert scan_secrets.scan_text("name: ci\njobs: {}\n") == []

    def test_reports_1_based_line_numbers(self) -> None:
        text = "clean line\n" f"key = {_FAKE_GHP}\n" "another clean line\n"
        assert scan_secrets.scan_text(text) == [(2, "github-token")]


# ---------------------------------------------------------------------------
# _is_skipped
# ---------------------------------------------------------------------------


class TestIsSkipped:
    @pytest.mark.parametrize(
        "rel",
        [
            "scripts/foo.py",
            "uv.lock",
            "flake.lock",
            "apm.lock.yaml",
            ".apm/CHECKSUMS",
            "docs/diagram.png",
            "assets/logo.SVG",
        ],
    )
    def test_skipped(self, rel: str) -> None:
        assert scan_secrets._is_skipped(rel) is True

    @pytest.mark.parametrize(
        "rel",
        [
            "config.yml",
            ".claude/settings.json",
            "scripts/install.sh",
            "pyproject.toml",
            "README.md",
        ],
    )
    def test_not_skipped(self, rel: str) -> None:
        assert scan_secrets._is_skipped(rel) is False

    def test_allowlist_path_skipped(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            scan_secrets, "ALLOWLIST_PATHS", frozenset({"tests/fixture.yml"})
        )
        assert scan_secrets._is_skipped("tests/fixture.yml") is True


# ---------------------------------------------------------------------------
# find_violations (explicit paths) + _read_text
# ---------------------------------------------------------------------------


class TestFindViolations:
    def test_detects_secret_in_yaml(self, tmp_path: Path) -> None:
        bad = tmp_path / "config.yml"
        bad.write_text(f"token: {_FAKE_GHP}\n")
        findings = scan_secrets.find_violations(tmp_path, paths=[bad])
        assert findings == [
            scan_secrets.Finding(Path("config.yml"), 1, "github-token")
        ]

    def test_clean_file_yields_nothing(self, tmp_path: Path) -> None:
        good = tmp_path / "config.yml"
        good.write_text("token: ${{ secrets.X }}\n")
        assert scan_secrets.find_violations(tmp_path, paths=[good]) == []

    def test_binary_file_is_skipped(self, tmp_path: Path) -> None:
        blob = tmp_path / "data.txt"
        blob.write_bytes(b"\xff\xfe\x00secret\x00")
        assert scan_secrets.find_violations(tmp_path, paths=[blob]) == []

    def test_real_repo_has_no_secrets(self) -> None:
        """The checked-in repo must pass the gate end-to-end."""
        findings = scan_secrets.find_violations(REPO_ROOT)
        assert findings == [], "\n".join(
            f"{f.path.as_posix()}:{f.line} ({f.rule_id})" for f in findings
        )

    def test_iter_tracked_files_excludes_python(self) -> None:
        files = list(scan_secrets.iter_tracked_files(REPO_ROOT))
        assert files, "expected some tracked non-Python files"
        assert all(p.suffix != ".py" for p in files)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


class TestCLI:
    def test_verify_clean_real_repo(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert scan_secrets.main(["verify"]) == 0
        assert "OK" in capsys.readouterr().out

    def test_verify_dirty(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        bad = tmp_path / "config.yml"
        bad.write_text(f"token: {_FAKE_GHP}\n")
        monkeypatch.setattr(scan_secrets, "REPO_ROOT", tmp_path)
        monkeypatch.setattr(
            scan_secrets, "iter_tracked_files", lambda root: [bad]
        )
        assert scan_secrets.main(["verify"]) == 1
        captured = capsys.readouterr()
        assert "::error file=config.yml" in captured.err
        assert "github-token" in captured.err
        # the secret value itself must never be echoed
        assert _FAKE_GHP not in captured.err
        assert "FAIL" in captured.err

    def test_list_prints_rule_without_value(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        bad = tmp_path / "config.yml"
        bad.write_text(f"token: {_FAKE_GHP}\n")
        monkeypatch.setattr(scan_secrets, "REPO_ROOT", tmp_path)
        monkeypatch.setattr(
            scan_secrets, "iter_tracked_files", lambda root: [bad]
        )
        assert scan_secrets.main(["list"]) == 0
        out = capsys.readouterr().out
        assert "config.yml:1 (github-token)" in out
        assert _FAKE_GHP not in out

    def test_no_subcommand_exits_nonzero(self) -> None:
        with pytest.raises(SystemExit) as exc:
            scan_secrets.main([])
        assert exc.value.code == 2
