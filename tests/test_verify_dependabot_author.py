"""Tests for ``scripts/verify_dependabot_author.py``.

Refs #1014 (parent #273).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import verify_dependabot_author as gate

pytestmark = pytest.mark.shard_policy


class TestIsViolation:
    def test_trusted_bot_on_dependabot_branch_passes(self) -> None:
        assert gate.is_violation("dependabot/uv/foo-1.2.3", "dependabot[bot]") is False

    def test_non_bot_author_on_dependabot_branch_is_violation(self) -> None:
        assert gate.is_violation("dependabot/uv/foo-1.2.3", "mallory") is True

    def test_non_dependabot_branch_never_violates(self) -> None:
        # Even an untrusted author is out of scope off the dependabot/* namespace.
        assert gate.is_violation("feature/x", "mallory") is False
        assert gate.is_violation("claude/bold-volta", "mallory") is False

    def test_missing_author_on_dependabot_branch_is_violation(self) -> None:
        assert gate.is_violation("dependabot/npm/x", "") is True

    def test_exact_prefix_required(self) -> None:
        # A branch that merely contains the token but does not start with it
        # is out of scope.
        assert gate.is_violation("feature/dependabot/x", "mallory") is False


class TestVerifyCli:
    def test_verify_passes_for_trusted_bot(self) -> None:
        assert (
            gate.main(
                [
                    "verify",
                    "--head-ref",
                    "dependabot/github_actions/actions/checkout-6",
                    "--author",
                    "dependabot[bot]",
                ]
            )
            == 0
        )

    def test_verify_fails_for_non_bot(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert (
            gate.main(
                [
                    "verify",
                    "--head-ref",
                    "dependabot/github_actions/actions/checkout-6",
                    "--author",
                    "mallory",
                ]
            )
            == 1
        )
        err = capsys.readouterr().err
        assert "::error::" in err
        assert "mallory" in err
        assert "dependabot/*" in err

    def test_verify_passes_for_unrelated_branch(self) -> None:
        assert (
            gate.main(
                [
                    "verify",
                    "--head-ref",
                    "claude/some-branch",
                    "--author",
                    "mallory",
                ]
            )
            == 0
        )
