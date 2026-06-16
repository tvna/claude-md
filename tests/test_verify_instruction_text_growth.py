"""Tests for ``scripts/verify_instruction_text_growth.py``.

Table-driven style: pure functions get parametrize cases, the
subprocess boundary is exercised via a fake ``runner`` injected through
the kwarg the production code already exposes.

The ``scripts/`` directory is on ``sys.path`` via ``pythonpath`` under
``[tool.pytest.ini_options]`` in ``pyproject.toml``.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest
import verify_instruction_text_growth as gate

pytestmark = pytest.mark.shard_ci_ops


def _fake_runner(stdout: str = "", returncode: int = 0):
    """Return a callable mimicking ``subprocess.run(..., check=True)``."""

    def runner(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if kwargs.get("check") and returncode != 0:
            raise subprocess.CalledProcessError(
                returncode, cmd, output=stdout, stderr=""
            )
        return subprocess.CompletedProcess[str](
            args=cmd, returncode=returncode, stdout=stdout, stderr=""
        )

    return runner


# A unified diff that expands a single bullet: one line removed (8 chars
# of content), one longer line added (22 chars of content) -> net +14.
_GROWTH_DIFF = (
    "diff --git a/.apm/instructions/master.instructions.md "
    "b/.apm/instructions/master.instructions.md\n"
    "index 1111111..2222222 100644\n"
    "--- a/.apm/instructions/master.instructions.md\n"
    "+++ b/.apm/instructions/master.instructions.md\n"
    "@@ -10 +10 @@\n"
    "-old text\n"
    "+old text expanded more\n"
)

# The inverse: a trim. Long line removed, short line added -> net -14.
_TRIM_DIFF = (
    "--- a/.apm/instructions/master.instructions.md\n"
    "+++ b/.apm/instructions/master.instructions.md\n"
    "@@ -10 +10 @@\n"
    "-old text expanded more\n"
    "+old text\n"
)


# ---------------------------------------------------------------------------
# resolve_base
# ---------------------------------------------------------------------------


class TestResolveBase:
    def test_explicit_base_ref_wins(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("BASE_REF", "origin/feature")
        monkeypatch.setenv("GITHUB_BASE_REF", "main")
        assert gate.resolve_base() == "origin/feature"

    def test_github_base_ref_prefixed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("BASE_REF", raising=False)
        monkeypatch.setenv("GITHUB_BASE_REF", "release")
        assert gate.resolve_base() == "origin/release"

    def test_local_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("BASE_REF", raising=False)
        monkeypatch.delenv("GITHUB_BASE_REF", raising=False)
        assert gate.resolve_base() == "origin/main"


# ---------------------------------------------------------------------------
# net_char_delta
# ---------------------------------------------------------------------------


class TestNetCharDelta:
    def test_empty_diff_is_zero(self) -> None:
        assert gate.net_char_delta("") == 0

    def test_growth_counts_positive(self) -> None:
        assert gate.net_char_delta(_GROWTH_DIFF) == 14

    def test_trim_counts_negative(self) -> None:
        assert gate.net_char_delta(_TRIM_DIFF) == -14

    def test_pure_addition(self) -> None:
        diff = (
            "--- a/.apm/instructions/master.instructions.md\n"
            "+++ b/.apm/instructions/master.instructions.md\n"
            "@@ -0,0 +1 @@\n"
            "+abcde\n"
        )
        assert gate.net_char_delta(diff) == 5

    def test_pure_deletion(self) -> None:
        diff = (
            "--- a/.apm/instructions/master.instructions.md\n"
            "+++ b/.apm/instructions/master.instructions.md\n"
            "@@ -1 +0,0 @@\n"
            "-abcde\n"
        )
        assert gate.net_char_delta(diff) == -5

    def test_headers_and_no_newline_marker_ignored(self) -> None:
        # ``+++``/``---`` headers and the ``\\ No newline`` marker must not
        # be counted as content even though they begin with +/-/\\.
        diff = (
            "diff --git a/x b/x\n"
            "index aaa..bbb 100644\n"
            "--- a/.apm/instructions/master.instructions.md\n"
            "+++ b/.apm/instructions/master.instructions.md\n"
            "@@ -1 +1 @@\n"
            "-ab\n"
            "+abcd\n"
            "\\ No newline at end of file\n"
        )
        assert gate.net_char_delta(diff) == 2


# ---------------------------------------------------------------------------
# has_growth_ack
# ---------------------------------------------------------------------------


class TestHasGrowthAck:
    @pytest.mark.parametrize(
        "body",
        [
            "text-growth-ack: clarifies #1662 ambiguity",
            "  text-growth-ack: indented reason",
            "## Summary\n\nfoo\n\nTEXT-GROWTH-ACK: case-insensitive\n",
            "intro\ntext-growth-ack:\twith a tab-led reason\n",
        ],
    )
    def test_present(self, body: str) -> None:
        assert gate.has_growth_ack(body) is True

    @pytest.mark.parametrize(
        "body",
        [
            "",
            "no marker here",
            # Bare marker with no reason is malformed -> not a valid ack.
            "text-growth-ack:",
            "text-growth-ack:   ",
            # Not anchored at line start after optional indent.
            "see text-growth-ack: inline",
        ],
    )
    def test_absent_or_malformed(self, body: str) -> None:
        assert gate.has_growth_ack(body) is False


# ---------------------------------------------------------------------------
# evaluate
# ---------------------------------------------------------------------------


class TestEvaluate:
    def test_net_zero_passes(self) -> None:
        code, errors = gate.evaluate(0, "no ack at all")
        assert code == 0
        assert errors == []

    def test_net_negative_passes(self) -> None:
        code, errors = gate.evaluate(-14, "no ack at all")
        assert code == 0
        assert errors == []

    def test_net_positive_without_ack_fails(self) -> None:
        code, errors = gate.evaluate(14, "## Summary\n\nno justification\n")
        assert code == 1
        assert len(errors) == 1
        assert "+14 chars" in errors[0]
        assert "text-growth-ack:" in errors[0]

    def test_net_positive_with_ack_passes(self) -> None:
        body = "## Summary\n\ntext-growth-ack: warranted clarification\n"
        code, errors = gate.evaluate(14, body)
        assert code == 0
        assert errors == []


# ---------------------------------------------------------------------------
# instruction_diff (subprocess boundary)
# ---------------------------------------------------------------------------


class TestInstructionDiff:
    def test_returns_runner_stdout(self) -> None:
        assert (
            gate.instruction_diff(
                "origin/main", runner=_fake_runner(_GROWTH_DIFF)
            )
            == _GROWTH_DIFF
        )

    def test_restricts_to_instruction_pathspec(self) -> None:
        captured: dict[str, list[str]] = {}

        def runner(cmd: list[str], **kwargs: Any):
            captured["cmd"] = cmd
            return subprocess.CompletedProcess[str](cmd, 0, stdout="", stderr="")

        gate.instruction_diff("origin/main", runner=runner)
        assert "--unified=0" in captured["cmd"]
        assert captured["cmd"][-1] == ".apm/instructions/"
        assert captured["cmd"][-2] == "--"

    def test_git_failure_raises(self) -> None:
        with pytest.raises(subprocess.CalledProcessError):
            gate.instruction_diff(
                "origin/main", runner=_fake_runner("", returncode=128)
            )


# ---------------------------------------------------------------------------
# CLI contract (main)
# ---------------------------------------------------------------------------


class TestMainCLI:
    def test_growth_without_ack_fails(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            gate,
            "instruction_diff",
            lambda base, head="HEAD", **kw: _GROWTH_DIFF,
        )
        monkeypatch.delenv("BODY_POLICY_CUTOFF", raising=False)
        monkeypatch.setenv("PR_BODY", "## Summary\n\nno justification\n")
        assert gate.main(["verify", "--base-ref", "origin/main"]) == 1

    def test_growth_with_ack_passes(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setattr(
            gate,
            "instruction_diff",
            lambda base, head="HEAD", **kw: _GROWTH_DIFF,
        )
        body_file = tmp_path / "body.md"
        body_file.write_text(
            "## Summary\n\ntext-growth-ack: warranted clarification\n",
            encoding="utf-8",
        )
        assert (
            gate.main(
                [
                    "verify",
                    "--base-ref",
                    "origin/main",
                    "--body-file",
                    str(body_file),
                ]
            )
            == 0
        )

    def test_trim_passes_without_ack(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            gate,
            "instruction_diff",
            lambda base, head="HEAD", **kw: _TRIM_DIFF,
        )
        monkeypatch.delenv("BODY_POLICY_CUTOFF", raising=False)
        monkeypatch.setenv("PR_BODY", "## Summary\n\nnet-negative edit\n")
        assert gate.main(["verify", "--base-ref", "origin/main"]) == 0

    def test_no_instruction_change_passes(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Empty diff (no .apm/instructions/** file touched) -> net 0 -> pass.
        monkeypatch.setattr(
            gate, "instruction_diff", lambda base, head="HEAD", **kw: ""
        )
        monkeypatch.setenv("PR_BODY", "## Summary\n\nscript-only change\n")
        assert gate.main(["verify", "--base-ref", "origin/main"]) == 0

    def test_cutoff_skips_back_catalog(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # created_at strictly before cutoff -> skip even though the diff
        # would grow and the body has no ack.
        called = False

        def _should_not_run(*args: Any, **kwargs: Any) -> str:
            nonlocal called
            called = True
            return _GROWTH_DIFF

        monkeypatch.setattr(gate, "instruction_diff", _should_not_run)
        monkeypatch.setenv("PR_BODY", "no ack")
        code = gate.main(
            [
                "verify",
                "--created-at",
                "2026-05-01T00:00:00Z",
                "--cutoff",
                "2026-05-26T00:00:00Z",
            ]
        )
        assert code == 0
        assert called is False

    def test_body_file_not_found_fails_loud(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("BODY_POLICY_CUTOFF", raising=False)
        code = gate.main(
            [
                "verify",
                "--base-ref",
                "origin/main",
                "--body-file",
                "/nonexistent/body.md",
            ]
        )
        assert code == 1
