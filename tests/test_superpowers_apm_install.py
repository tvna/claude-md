"""Contracts for the pinned Superpowers APM dependency.

Refs #728.
"""

from __future__ import annotations

import subprocess
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


def _git_tracked(pathspec: str) -> set[str]:
    out = subprocess.check_output(
        ["git", "ls-files", pathspec], cwd=ROOT, text=True, timeout=10
    )
    return {line for line in out.splitlines() if line}


def test_superpowers_claude_skills_are_committed() -> None:
    """The .claude/skills/ carve-out (#1983) must be tracked, not just on disk.

    Claude Code discovers project skills under .claude/skills/. Committing them
    (a narrow carve-out from the .claude/* prohibition, symmetric to
    .agents/skills/ #728) is what lets Claude Code on the Web load the pinned
    Superpowers skills from a fresh clone, at parity with Devin/Codex. This pins
    the carve-out so a .gitignore regression that re-hides the tree fails loudly.
    """
    tracked = {
        Path(p).parent.name
        for p in _git_tracked(".claude/skills/*/SKILL.md")
    }
    assert tracked == SUPERPOWERS_SKILLS


def test_claude_and_agent_skills_are_identical() -> None:
    """The two committed skill surfaces are byte-identical APM output.

    apm install (target: [claude, codex]) deploys the same pinned package into
    both .agents/skills/ and .claude/skills/ (apm.lock.yaml deployed_files), so
    they must not drift apart.
    """
    agent_skills = ROOT / ".agents" / "skills"
    claude_skills = ROOT / ".claude" / "skills"
    for skill in SUPERPOWERS_SKILLS:
        agent_doc = (agent_skills / skill / "SKILL.md").read_bytes()
        claude_doc = (claude_skills / skill / "SKILL.md").read_bytes()
        assert agent_doc == claude_doc, f"{skill}/SKILL.md drifted between surfaces"
