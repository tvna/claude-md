"""Tests for ``scripts/scan_secret_runbooks.py``."""

from __future__ import annotations

from pathlib import Path

import pytest
import scan_secret_runbooks

pytestmark = pytest.mark.shard_ci_ops


def make_repo(tmp_path: Path) -> Path:
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / "docs" / "runbooks").mkdir(parents=True)
    return tmp_path


def write_workflow(repo: Path, text: str) -> None:
    (repo / ".github" / "workflows" / "ci.yml").write_text(text, encoding="utf-8")


def write_good_runbook(repo: Path, token_name: str) -> None:
    (repo / "docs" / "runbooks" / "example.md").write_text(
        f"""# Example

One-time setup for `{token_name}`:

1. Open GitHub Settings.
2. Create a fine-grained PAT.
3. Set Repository permissions to Issues: Read and write.
4. Store it as an Environment secret named `{token_name}`.
5. Run the workflow and verify the guard step passes.

Rotation: replace the token before its expiry.
""",
        encoding="utf-8",
    )


def test_collect_secret_uses_ignores_github_token(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    write_workflow(
        repo,
        "env:\n"
        "  GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}\n"
        "  API_TOKEN: ${{ secrets.EXAMPLE_PAT }}\n",
    )

    uses = scan_secret_runbooks.collect_secret_uses(repo / ".github" / "workflows", repo)

    assert [use.name for use in uses] == ["EXAMPLE_PAT"]
    assert uses[0].line == 3


def test_verify_passes_when_secret_has_concrete_runbook(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    write_workflow(repo, "env:\n  GH_TOKEN: ${{ secrets.EXAMPLE_PAT }}\n")
    write_good_runbook(repo, "EXAMPLE_PAT")

    assert scan_secret_runbooks.verify(repo) == []


def test_verify_fails_when_no_runbook_mentions_secret(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    write_workflow(repo, "env:\n  GH_TOKEN: ${{ secrets.EXAMPLE_PAT }}\n")

    errors = scan_secret_runbooks.verify(repo)

    assert len(errors) == 1
    assert "EXAMPLE_PAT" in errors[0]
    assert "no runbook mentions the secret" in errors[0]


def test_verify_fails_when_runbook_lacks_concrete_details(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    write_workflow(repo, "env:\n  GH_TOKEN: ${{ secrets.EXAMPLE_PAT }}\n")
    (repo / "docs" / "runbooks" / "example.md").write_text(
        "The workflow uses EXAMPLE_PAT.\n",
        encoding="utf-8",
    )

    errors = scan_secret_runbooks.verify(repo)

    assert len(errors) == 1
    assert "one-time setup heading" in errors[0]
    assert "rotation cadence" in errors[0]


def test_repository_runbooks_cover_current_named_secrets() -> None:
    repo = Path(__file__).resolve().parents[1]

    assert scan_secret_runbooks.verify(repo) == []
