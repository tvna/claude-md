"""Contracts for the pinned APM dependencies (Superpowers, Clairvoyance).

Refs #728, #2185.
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
CLAIRVOYANCE_SHA = "4df075294c8e6a33b42e6703b54211f66c8a5ca3"
CLAIRVOYANCE_DEP = f"tvna/clairvoyance#{CLAIRVOYANCE_SHA}"
CLAIRVOYANCE_SKILLS = {
    "adaptive-coaching",
    "architecture-tradeoff",
    "clairvoyance",
    "decision-coaching",
    "human-harness",
    "review-verdict",
    "session-handoff",
    "using-clairvoyance",
}
ALL_APM_SKILLS = SUPERPOWERS_SKILLS | CLAIRVOYANCE_SKILLS


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


def test_clairvoyance_dependency_is_pinned_in_apm_yml() -> None:
    data = _load_yaml(ROOT / "apm.yml")
    dependencies = data["dependencies"]
    assert isinstance(dependencies, dict)
    apm_dependencies = dependencies["apm"]
    assert isinstance(apm_dependencies, list)
    assert CLAIRVOYANCE_DEP in apm_dependencies


def test_clairvoyance_lock_matches_declared_pin() -> None:
    data = _load_yaml(ROOT / "apm.lock.yaml")
    dependencies = data["dependencies"]
    assert isinstance(dependencies, list)
    matches = [
        dependency
        for dependency in dependencies
        if isinstance(dependency, dict) and dependency.get("repo_url") == "tvna/clairvoyance"
    ]
    assert len(matches) == 1
    assert matches[0]["resolved_commit"] == CLAIRVOYANCE_SHA


def test_superpowers_agent_skills_are_deployed() -> None:
    skills_root = ROOT / ".agents" / "skills"
    deployed = {
        path.parent.name
        for path in skills_root.glob("*/SKILL.md")
    }
    assert deployed == ALL_APM_SKILLS


def test_superpowers_skills_are_devin_compatible_agent_skills() -> None:
    skills_root = ROOT / ".agents" / "skills"
    for skill in ALL_APM_SKILLS:
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
    assert tracked == ALL_APM_SKILLS


def _skill_tree_snapshot(root: Path) -> dict[str, tuple[bytes, bool]]:
    """Map every file under *root* to (bytes, is-executable), keyed by rel path."""
    snapshot: dict[str, tuple[bytes, bool]] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            rel = path.relative_to(root).as_posix()
            snapshot[rel] = (path.read_bytes(), bool(path.stat().st_mode & 0o111))
    return snapshot


def test_claude_and_agent_skill_trees_are_identical() -> None:
    """The two committed skill surfaces are identical APM output, whole tree.

    apm install (target: [claude, codex]) deploys the same pinned package into
    both .agents/skills/ and .claude/skills/ (apm.lock.yaml deployed_files), so
    they must not drift apart. Compare the FULL relative tree, not just SKILL.md:
    skills carry companion assets (scripts/, references/, prompts), and Claude
    Code on the Web consumes the .claude/ copies of those helpers while
    Devin/Codex use the .agents/ copies. Comparing membership, byte content, and
    the executable bit makes this gate enforce the byte-identical invariant the
    carve-out documents (Refs #1983 review).
    """
    agent_tree = _skill_tree_snapshot(ROOT / ".agents" / "skills")
    claude_tree = _skill_tree_snapshot(ROOT / ".claude" / "skills")

    assert set(agent_tree) == set(claude_tree), (
        "skill tree membership diverged: "
        f"agents-only={sorted(set(agent_tree) - set(claude_tree))} "
        f"claude-only={sorted(set(claude_tree) - set(agent_tree))}"
    )
    for rel in agent_tree:
        agent_bytes, agent_exec = agent_tree[rel]
        claude_bytes, claude_exec = claude_tree[rel]
        assert agent_bytes == claude_bytes, f"content drift between surfaces: {rel}"
        assert agent_exec == claude_exec, f"executable-bit drift between surfaces: {rel}"
