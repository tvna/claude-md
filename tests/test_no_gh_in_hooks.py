"""Static analysis: verify that hook scripts contain no direct subprocess calls
invoking ``gh`` as the executable.

Hook scripts registered in ``.claude/settings.json`` and ``.codex/hooks.json``
run in remote execution environments where the ``gh`` CLI may be absent.
This test catches regressions early -- before a broken hook surfaces at runtime.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.shard_preflight

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SCRIPTS_DIR = _REPO_ROOT / "scripts"

# Subprocess call names that can launch an executable.
_SUBPROCESS_CALL_ATTRS = frozenset({"run", "Popen", "call", "check_call", "check_output"})


def _collect_hook_scripts() -> list[Path]:
    """Return paths of Python scripts registered as hooks.

    Walks each hook config structurally and collects every ``scripts/*.py``
    token from each command. Token-based extraction is robust to the CWD
    wrapper the generator injects (``cd "$(git rev-parse --show-toplevel)" &&
    python3 scripts/foo.py``) -- the ``scripts/foo.py`` token is still present
    regardless of any prefix.
    """
    scripts: set[str] = set()

    for settings_path in [
        _REPO_ROOT / ".claude" / "settings.json",
        _REPO_ROOT / ".codex" / "hooks.json",
    ]:
        if not settings_path.exists():
            continue
        try:
            data: Any = json.loads(settings_path.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        hooks = data.get("hooks", {}) if isinstance(data, dict) else {}
        if not isinstance(hooks, dict):
            continue
        for groups in hooks.values():
            if not isinstance(groups, list):
                continue
            for group in groups:
                if not isinstance(group, dict):
                    continue
                for handler in group.get("hooks", []):
                    if not isinstance(handler, dict):
                        continue
                    command = handler.get("command", "")
                    if not isinstance(command, str):
                        continue
                    for token in command.split():
                        if token.startswith("scripts/") and token.endswith(".py"):
                            scripts.add(token)

    return [_REPO_ROOT / s for s in sorted(scripts) if (_REPO_ROOT / s).exists()]


def _gh_subprocess_violations(path: Path) -> list[str]:
    """Return lines (as strings) where *path* calls subprocess with ``gh`` as the executable."""
    try:
        source = path.read_text()
        tree = ast.parse(source, filename=str(path))
    except (OSError, SyntaxError):
        return []

    violations: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        # Match subprocess.run / subprocess.Popen / subprocess.call etc.
        is_subprocess_call = (isinstance(func, ast.Attribute) and func.attr in _SUBPROCESS_CALL_ATTRS) or (
            isinstance(func, ast.Name) and func.id in _SUBPROCESS_CALL_ATTRS
        )
        if not is_subprocess_call:
            continue
        if not node.args:
            continue
        first_arg = node.args[0]
        if not isinstance(first_arg, ast.List) or not first_arg.elts:
            continue
        first_elt = first_arg.elts[0]
        if isinstance(first_elt, ast.Constant) and first_elt.value == "gh":
            violations.append(f"{path.name}:{node.lineno}: subprocess call with 'gh' as executable")
    return violations


def test_hook_scripts_contain_no_gh_subprocess_calls() -> None:
    """All hook scripts must be free of direct ``gh`` subprocess invocations."""
    hook_scripts = _collect_hook_scripts()
    assert hook_scripts, "No hook scripts found -- check settings.json / hooks.json paths"

    all_violations: list[str] = []
    for script in hook_scripts:
        all_violations.extend(_gh_subprocess_violations(script))

    assert not all_violations, (
        "Direct 'gh' subprocess calls found in hook scripts.\n"
        "Replace with scripts/github_api.py REST wrapper or mcp__github__* tools.\n\n" + "\n".join(all_violations)
    )
