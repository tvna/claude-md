"""Tests for ``scripts/verify_control_inventory_currency.py``.

The ``scripts/`` directory is added to ``sys.path`` via the ``pythonpath``
key under ``[tool.pytest.ini_options]`` in ``pyproject.toml``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import verify_control_inventory_currency as currency

pytestmark = pytest.mark.shard_ci_ops

REPO_ROOT = Path(__file__).resolve().parents[1]

# A minimal privileged workflow (declares an environment) and a benign one.
PRIVILEGED_WORKFLOW = "name: x\non:\n  workflow_dispatch:\njobs:\n  j:\n    environment:\n      name: prod\n    steps: []\n"
PAT_WORKFLOW = "name: x\njobs:\n  j:\n    steps:\n      - run: echo ${{ secrets.SOME_PAT }}\n"
BENIGN_WORKFLOW = "name: x\njobs:\n  j:\n    steps:\n      - run: echo ${{ secrets.GITHUB_TOKEN }}\n"
SECRET_SCRIPT = "from _secret_patterns import scan_text\n"
BENIGN_SCRIPT = "import os\n"


def scaffold(
    tmp_path: Path,
    *,
    workflows: dict[str, str] | None = None,
    scripts: dict[str, str] | None = None,
    inventory: str,
    manifest: str,
) -> Path:
    """Write a synthetic repo tree and return its root."""
    (tmp_path / "docs" / "prd").mkdir(parents=True, exist_ok=True)
    (tmp_path / "docs" / "prd" / "security-control-inventory.md").write_text(
        inventory, encoding="utf-8"
    )
    wf_dir = tmp_path / ".github" / "workflows"
    wf_dir.mkdir(parents=True, exist_ok=True)
    for name, body in (workflows or {}).items():
        (wf_dir / name).write_text(body, encoding="utf-8")
    sc_dir = tmp_path / "scripts"
    sc_dir.mkdir(parents=True, exist_ok=True)
    for name, body in (scripts or {}).items():
        (sc_dir / name).write_text(body, encoding="utf-8")
    (tmp_path / ".github" / "security-surface-inventory.toml").write_text(
        manifest, encoding="utf-8"
    )
    return tmp_path


# ---------------------------------------------------------------------------
# detection (pure-ish, reads the tree)
# ---------------------------------------------------------------------------


class TestDetectPrivilegedSurfaces:
    def test_environment_and_pat_workflows_detected(self, tmp_path: Path) -> None:
        root = scaffold(
            tmp_path,
            workflows={
                "env.yml": PRIVILEGED_WORKFLOW,
                "pat.yml": PAT_WORKFLOW,
                "benign.yml": BENIGN_WORKFLOW,
            },
            inventory="# inv\n",
            manifest="schema_version = 1\n",
        )
        detected = currency.detect_privileged_surfaces(root)
        assert ".github/workflows/env.yml" in detected
        assert ".github/workflows/pat.yml" in detected
        # GITHUB_TOKEN-only, no environment -> not privileged.
        assert ".github/workflows/benign.yml" not in detected

    def test_secret_pattern_importer_detected(self, tmp_path: Path) -> None:
        root = scaffold(
            tmp_path,
            scripts={"handler.py": SECRET_SCRIPT, "plain.py": BENIGN_SCRIPT},
            inventory="# inv\n",
            manifest="schema_version = 1\n",
        )
        detected = currency.detect_privileged_surfaces(root)
        assert "scripts/handler.py" in detected
        assert "scripts/plain.py" not in detected


# ---------------------------------------------------------------------------
# verify (#1387 acceptance: unregistered surface fails, registered passes)
# ---------------------------------------------------------------------------


class TestVerify:
    def test_registered_surface_with_row_passes(self, tmp_path: Path) -> None:
        root = scaffold(
            tmp_path,
            workflows={"env.yml": PRIVILEGED_WORKFLOW},
            inventory="# inv\n\n| `env.yml` | row exists |\n",
            manifest=(
                "schema_version = 1\n"
                '[[surfaces]]\npath = ".github/workflows/env.yml"\n'
                'status = "inventory"\n'
            ),
        )
        assert currency.verify(root) == []

    def test_unregistered_privileged_surface_fails_then_registered_passes(
        self, tmp_path: Path
    ) -> None:
        # Deliberately unregistered sample surface: the gate must fail.
        inventory = "# inv\n\n| `env.yml` | row exists |\n"
        root = scaffold(
            tmp_path,
            workflows={"env.yml": PRIVILEGED_WORKFLOW},
            inventory=inventory,
            manifest="schema_version = 1\n",
        )
        errors = currency.verify(root)
        assert len(errors) == 1
        assert ".github/workflows/env.yml" in errors[0]
        assert "not listed" in errors[0]

        # Register it; the gate now passes.
        (root / ".github" / "security-surface-inventory.toml").write_text(
            "schema_version = 1\n"
            '[[surfaces]]\npath = ".github/workflows/env.yml"\n'
            'status = "inventory"\n',
            encoding="utf-8",
        )
        assert currency.verify(root) == []

    def test_inventory_status_without_row_fails(self, tmp_path: Path) -> None:
        root = scaffold(
            tmp_path,
            workflows={"env.yml": PRIVILEGED_WORKFLOW},
            inventory="# inv\n(no row for the workflow)\n",
            manifest=(
                "schema_version = 1\n"
                '[[surfaces]]\npath = ".github/workflows/env.yml"\n'
                'status = "inventory"\n'
            ),
        )
        errors = currency.verify(root)
        assert any("not represented" in e for e in errors)

    def test_exempt_without_reason_fails(self, tmp_path: Path) -> None:
        root = scaffold(
            tmp_path,
            workflows={"env.yml": PRIVILEGED_WORKFLOW},
            inventory="# inv\n",
            manifest=(
                "schema_version = 1\n"
                '[[surfaces]]\npath = ".github/workflows/env.yml"\n'
                'status = "exempt"\nreason = ""\n'
            ),
        )
        errors = currency.verify(root)
        assert any("empty" in e and "reason" in e for e in errors)

    def test_exempt_with_reason_passes(self, tmp_path: Path) -> None:
        root = scaffold(
            tmp_path,
            workflows={"env.yml": PRIVILEGED_WORKFLOW},
            inventory="# inv\n",
            manifest=(
                "schema_version = 1\n"
                '[[surfaces]]\npath = ".github/workflows/env.yml"\n'
                'status = "exempt"\nreason = "deployment env, not a control row"\n'
            ),
        )
        assert currency.verify(root) == []

    def test_stale_manifest_path_fails(self, tmp_path: Path) -> None:
        root = scaffold(
            tmp_path,
            inventory="# inv\n",
            manifest=(
                "schema_version = 1\n"
                '[[surfaces]]\npath = ".github/workflows/gone.yml"\n'
                'status = "inventory"\n'
            ),
        )
        errors = currency.verify(root)
        assert any("does not exist on disk" in e for e in errors)

    def test_dangling_script_reference_fails(self, tmp_path: Path) -> None:
        root = scaffold(
            tmp_path,
            inventory="# inv\n\nEvidence: `scripts/ghost.py` is cited.\n",
            manifest="schema_version = 1\n",
        )
        errors = currency.verify(root)
        assert any("scripts/ghost.py" in e and "does not exist" in e for e in errors)

    def test_invalid_status_fails(self, tmp_path: Path) -> None:
        root = scaffold(
            tmp_path,
            workflows={"env.yml": PRIVILEGED_WORKFLOW},
            inventory="# inv\n\n| `env.yml` |\n",
            manifest=(
                "schema_version = 1\n"
                '[[surfaces]]\npath = ".github/workflows/env.yml"\n'
                'status = "bogus"\n'
            ),
        )
        errors = currency.verify(root)
        assert any("invalid status" in e for e in errors)


# ---------------------------------------------------------------------------
# regression guard: the shipped tree is current
# ---------------------------------------------------------------------------


class TestRealTree:
    def test_repo_inventory_is_current(self) -> None:
        assert currency.verify(REPO_ROOT) == []
