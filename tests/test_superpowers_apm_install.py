"""Contracts for the pinned Superpowers APM dependency.

Refs #728.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.shard_policy

ROOT = Path(__file__).resolve().parents[1]
SUPERPOWERS_SHA = "f2cbfbefebbfef77321e4c9abc9e949826bea9d7"
SUPERPOWERS_DEP = f"obra/superpowers#{SUPERPOWERS_SHA}"
SUPERPOWERS_SKILLS = {
    "brainstorming",
    "dispatching-parallel-agents",
    "executing-plans",
    "finishing-a-development-branch",
    "receiving-code-review",
    "requesting-code-review",
    "subagent-driven-development",
    "systematic-debugging",
    "test-driven-development",
    "using-git-worktrees",
    "using-superpowers",
    "verification-before-completion",
    "writing-plans",
    "writing-skills",
}


def _load_yaml(path: Path) -> dict[str, object]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def test_superpowers_dependency_is_pinned_in_apm_yml() -> None:
    data = _load_yaml(ROOT / "apm.yml")
    dependencies = data["dependencies"]
    assert isinstance(dependencies, dict)
    apm_dependencies = dependencies["apm"]
    assert isinstance(apm_dependencies, list)
    assert SUPERPOWERS_DEP in apm_dependencies


def test_superpowers_lock_matches_declared_pin() -> None:
    data = _load_yaml(ROOT / "apm.lock.yaml")
    dependencies = data["dependencies"]
    assert isinstance(dependencies, list)
    matches = [
        dependency
        for dependency in dependencies
        if isinstance(dependency, dict) and dependency.get("repo_url") == "obra/superpowers"
    ]
    assert len(matches) == 1
    assert matches[0]["resolved_commit"] == SUPERPOWERS_SHA


def test_superpowers_agent_skills_are_deployed() -> None:
    skills_root = ROOT / ".agents" / "skills"
    deployed = {
        path.parent.name
        for path in skills_root.glob("*/SKILL.md")
    }
    assert deployed == SUPERPOWERS_SKILLS


def test_superpowers_skills_are_devin_compatible_agent_skills() -> None:
    skills_root = ROOT / ".agents" / "skills"
    for skill in SUPERPOWERS_SKILLS:
        skill_file = skills_root / skill / "SKILL.md"
        assert skill_file.exists()
        text = skill_file.read_text(encoding="utf-8")
        assert text.startswith("---\n")
        assert "\nname:" in text
        assert "\ndescription:" in text
