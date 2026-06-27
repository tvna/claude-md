"""Single source of truth for the APM-managed path prefixes.

``.agents/skills/`` and ``.claude/skills/`` are the two committed copies of the
upstream ``obra/superpowers`` APM dependency (pinned in ``apm.yml`` /
``apm.lock.yaml``). ``apm compile`` regenerates both trees, so a direct edit is
silently overwritten on the next compile. Several gates and scanners encode this
same set:

- ``gate_agents_skills_edit.py`` blocks Edit/Write/Bash writes to these prefixes.
- ``scan_repo_em_dash.py`` / ``scan_repo_double_hyphen.py`` skip these prefixes
  when scanning the tree (the generated content is not the repo's to police).

Before this module each of those carried its own literal tuple. Per CLAUDE.md
section 3 ("Establishing an invariant ... ship its drift gate in the same
change"), the prefix set lives here once and the consumers import it, so the
copies cannot diverge. ``tests/test_apm_managed_paths.py`` is the drift gate: it
asserts every consumer references this constant.

See docs/standards/apm-managed-paths.md. Refs #2066, #1892, #1891.
"""

from __future__ import annotations

# Trailing slashes are deliberate: a sibling like ``.agents/skillset/`` must not
# match. Consumers use ``str.startswith`` against this tuple.
MANAGED_PREFIXES: tuple[str, ...] = (".agents/skills/", ".claude/skills/")
