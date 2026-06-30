"""Tests for ``scripts/gate_agents_skills_edit.py``.

Verifies that:
- ``Edit`` / ``Write`` / ``MultiEdit`` / ``NotebookEdit`` calls targeting an
  APM-managed prefix (``.agents/skills/``, ``.claude/skills/``) are denied,
  across relative, ``./``-prefixed, and absolute path forms.
- Edits to any other path (including the sibling ``.agents/skillset/``) pass.
- ``Bash`` commands that WRITE to a managed path are denied; a redirection
  target, or a mutating command (cp/mv/rm/tee/sed/...) carrying a managed path.
- ``Bash`` commands that only READ a managed path, or write elsewhere, pass.
- Non-Edit/Bash tools are ignored.
- The deny reason names the blocked path and the `apm compile` change path.
- The stdin -> stdout boundary works end-to-end, and malformed stdin fails
  open (exit 0, no decision emitted).

Adversarial / property coverage (issue #2098)
---------------------------------------------
``TestAdversarialBashDetection`` and ``TestBashDetectionProperties`` add the
deterministic gate the three Codex P2 findings on PR #2092 lacked: they exercise
the Bash heuristic against every known bypass and false-positive class so a
future edit to it cannot silently regress:

- wrapper / cluster flags (``bash -lc`` / ``sh -euc`` / ``-xc``; ``sudo`` /
  ``env`` / non-shell interpreters are pinned as documented limitations),
- the managed-directory root with no trailing slash (``rm -rf .agents/skills``),
- separators inside quotes (``git commit -m 'note ; rm .agents/skills/x'``),
- redirection variants (``>`` ``>>`` ``2>`` ``>|`` and attached ``>file``), and
- the quoted-redirect false positive (``echo '> .agents/skills/x'`` and the
  no-space ``echo '>.agents/skills/x'``) the prior hand-rolled redirect regex
  mismatched, now fixed by tokenizing with ``shlex.shlex(punctuation_chars=...)``.

Tokenizer evaluation (issue #2098, "hand-rolled parse -> real tokenizer?")
--------------------------------------------------------------------------
The per-segment tokenizer was moved from ``shlex.split`` to ``shlex.shlex`` with
``punctuation_chars`` so quoting is honored when classifying redirection
operators; the root cause of the quoted-``>`` false positive. The quote-aware
SEGMENT splitter (``gase._segments``) is intentionally retained: ``shlex`` does
not treat a newline as a command separator, so a wholesale replacement would
merge ``echo hi\ncp a .agents/skills/x`` into one token stream and MISS the
write (a bypass, strictly worse than a false positive for a safety gate).
Unifying segmentation onto a single real tokenizer is a larger, separable change
tracked for a follow-up issue; these property tests are the regression guard for
that future work.
"""

from __future__ import annotations

import io
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import gate_agents_skills_edit as gase

pytestmark = pytest.mark.shard_preflight


def _deny_reason(decision: dict[str, Any]) -> str:
    return str(decision["hookSpecificOutput"]["permissionDecisionReason"])


def _is_deny(decision: dict[str, Any] | None) -> bool:
    return (
        decision is not None
        and decision.get("hookSpecificOutput", {}).get("permissionDecision") == "deny"
    )


class TestMatchedPrefix:
    @pytest.mark.parametrize(
        "path,expected",
        [
            (".agents/skills/brainstorming/SKILL.md", ".agents/skills/"),
            (".claude/skills/brainstorming/SKILL.md", ".claude/skills/"),
            ("./.agents/skills/x.md", ".agents/skills/"),
            ("././.claude/skills/x.md", ".claude/skills/"),
            ("/home/user/claude-md/.agents/skills/x.md", ".agents/skills/"),
            ("'/repo/.claude/skills/x.md'", ".claude/skills/"),
            # the directory root itself (no trailing slash) is a managed target,
            # so a whole-tree rm/mv is caught, not just edits within it.
            (".agents/skills", ".agents/skills/"),
            (".claude/skills", ".claude/skills/"),
            ("/home/user/claude-md/.agents/skills", ".agents/skills/"),
        ],
    )
    def test_managed_paths_match(self, path: str, expected: str) -> None:
        assert gase.matched_prefix(path) == expected

    @pytest.mark.parametrize(
        "path",
        [
            ".agents/skillset/x.md",  # sibling dir, not skills/
            ".claude/settings.json",
            ".agents/instructions/x.md",
            "scripts/gate_agents_skills_edit.py",
            "/repo.agents/skills/x.md",  # no slash before .agents
            "docs/standards/apm-managed-paths.md",
            "",
        ],
    )
    def test_unmanaged_paths_do_not_match(self, path: str) -> None:
        assert gase.matched_prefix(path) is None


class TestDecideEditDenied:
    @pytest.mark.parametrize(
        "tool,key,path",
        [
            ("Edit", "file_path", ".agents/skills/brainstorming/SKILL.md"),
            ("Write", "file_path", ".claude/skills/brainstorming/SKILL.md"),
            ("MultiEdit", "file_path", "./.agents/skills/x.md"),
            ("Write", "file_path", "/home/user/claude-md/.claude/skills/x.md"),
            ("NotebookEdit", "notebook_path", ".agents/skills/x.ipynb"),
        ],
    )
    def test_edit_on_managed_path_denied(self, tool: str, key: str, path: str) -> None:
        decision = gase.decide(tool, {key: path})
        assert _is_deny(decision)
        assert decision is not None
        reason = _deny_reason(decision)
        assert path in reason
        assert "apm compile" in reason


class TestDecideEditAllowed:
    @pytest.mark.parametrize(
        "path",
        [
            "scripts/foo.py",
            ".claude/settings.json",
            ".agents/skillset/x.md",
            "docs/standards/apm-managed-paths.md",
            "/tmp/claude-plans/plan.md",
        ],
    )
    def test_edit_on_other_path_passes(self, path: str) -> None:
        assert gase.decide("Edit", {"file_path": path}) is None

    def test_edit_without_path_passes(self) -> None:
        assert gase.decide("Edit", {}) is None


class TestDecideBashDenied:
    @pytest.mark.parametrize(
        "command",
        [
            # redirection targets
            "echo x > .agents/skills/brainstorming/SKILL.md",
            "cat tmpl >> .claude/skills/x.md",
            "printf '%s' y >.agents/skills/x.md",
            # mutating commands carrying a managed path argument
            "cp /tmp/x .agents/skills/x.md",
            "mv old.md .claude/skills/new.md",
            "rm .agents/skills/brainstorming/SKILL.md",
            "sed -i 's/a/b/' .claude/skills/x.md",
            "tee .agents/skills/x.md",
            "touch .claude/skills/new.md",
            "install -m644 src .agents/skills/x.md",
            # command-position aware: write in a later segment / piped to tee
            "ls && cp a .agents/skills/x.md",
            "cat tmpl | tee .claude/skills/x.md",
            # absolute path argument
            "rm /home/user/claude-md/.agents/skills/x.md",
            # dd writes via the of= keyword argument
            "dd if=/dev/zero of=.agents/skills/x.md",
            "dd of=.claude/skills/x.md bs=1M",
            # noclobber-override redirection >|
            "echo evil >| .agents/skills/x.md",
            ">|.claude/skills/x.md echo hi",
            # mutator hidden in a shell -c script (recursed into)
            "bash -c 'cp a .agents/skills/x.md'",
            "sh -c 'echo y > .claude/skills/x.md'",
            # combined short-flag clusters ending in c (-lc, -euc) carry a script
            "bash -lc 'cp a .agents/skills/x.md'",
            "sh -euc 'rm .claude/skills/x.md'",
            # whole-tree delete/rename targets the directory root (no trailing /)
            "rm -rf .agents/skills",
            "mv .claude/skills /tmp/skills",
            "rm -rf /home/user/claude-md/.agents/skills",
        ],
    )
    def test_bash_write_to_managed_path_denied(self, command: str) -> None:
        decision = gase.decide("Bash", {"command": command})
        assert _is_deny(decision)
        assert decision is not None
        reason = _deny_reason(decision)
        assert "apm compile" in reason


class TestDecideBashAllowed:
    @pytest.mark.parametrize(
        "command",
        [
            # reads of a managed path are allowed
            "cat .agents/skills/brainstorming/SKILL.md",
            "grep -r foo .claude/skills/",
            "ls -la .agents/skills/",
            "head .claude/skills/x.md",
            # writes elsewhere
            "echo x > scripts/out.py",
            "cp a b",
            "rm -rf build",
            # mention only; managed path is not a write target of a mutator
            "echo '.agents/skills/x.md is generated'",
            # false-positive guard: a '>' inside a quoted string is not a real
            # redirection (regression test for the raw-scan false positive)
            "echo 'edit > .agents/skills/x.md to regenerate'",
            'git commit -m "note: writes > .claude/skills/x.md on compile"',
            # quote-aware segment split: a separator inside a quoted string must
            # not start a phantom mutator segment (Codex false-positive report)
            "git commit -m 'note ; rm .agents/skills/x.md'",
            "echo 'x | tee .claude/skills/y'",
            "echo 'a && cp z .agents/skills/x.md'",
            # sibling directory (root and within)
            "cp a .agents/skillset/x.md",
            "rm -rf .agents/skillset",
            # empty
            "",
            "   ",
        ],
    )
    def test_bash_safe_commands_pass(self, command: str) -> None:
        assert gase.decide("Bash", {"command": command}) is None


class TestDecideOtherTools:
    @pytest.mark.parametrize("tool_name", ["Read", "Glob", "Grep", "mcp__github__issue_write"])
    def test_other_tools_ignored(self, tool_name: str) -> None:
        assert gase.decide(tool_name, {"file_path": ".agents/skills/x.md"}) is None


class TestManagedWriteTargets:
    def test_dedupes_targets_in_order(self) -> None:
        command = "cp a .agents/skills/x.md && rm .agents/skills/x.md"
        assert gase.managed_write_targets(command) == [".agents/skills/x.md"]

    def test_no_targets_for_read(self) -> None:
        assert gase.managed_write_targets("cat .claude/skills/x.md") == []


class TestMainBoundary:
    def test_main_denies_managed_edit(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        event = {
            "tool_name": "Write",
            "tool_input": {"file_path": ".agents/skills/x.md"},
        }
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(event)))
        rc = gase.main([])
        assert rc == 0
        decision = json.loads(capsys.readouterr().out)
        assert _is_deny(decision)

    def test_main_denies_managed_bash_write(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        event = {
            "tool_name": "Bash",
            "tool_input": {"command": "cp a .claude/skills/x.md"},
        }
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(event)))
        rc = gase.main([])
        assert rc == 0
        decision = json.loads(capsys.readouterr().out)
        assert _is_deny(decision)

    def test_main_passes_through_safe_edit(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        event = {"tool_name": "Edit", "tool_input": {"file_path": "scripts/foo.py"}}
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(event)))
        rc = gase.main([])
        assert rc == 0
        assert capsys.readouterr().out == ""

    def test_main_fails_open_on_malformed_stdin(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(sys, "stdin", io.StringIO("{not json"))
        rc = gase.main([])
        assert rc == 0
        assert capsys.readouterr().out == ""

    def test_main_ignores_missing_tool_name(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"foo": "bar"})))
        assert gase.main([]) == 0


class TestQuotedRedirectFalsePositive:
    """A ``>`` inside quotes is a mention, never a redirection (issue #2098).

    The pre-#2098 gate tokenized with ``shlex.split``, which strips quotes before
    the redirect regex runs, so a quoted token whose content begins with ``>``
    (``echo '> .agents/skills/x'``, or the no-space ``echo '>.agents/skills/x'``)
    was misread as a real redirection and denied; a false positive that wedges
    ordinary Bash. Tokenizing with ``shlex.shlex(punctuation_chars=...)`` keeps
    the quoted ``>`` inside its word token, so these now pass.
    """

    @pytest.mark.parametrize(
        "command",
        [
            "echo '> .agents/skills/x.md'",
            "echo '>.agents/skills/x.md'",
            "echo '>> .claude/skills/x.md'",
            "echo '>>.claude/skills/x.md'",
            "printf '%s' '> .agents/skills/x.md now'",
            'git commit -m "writes >.claude/skills/x.md on compile"',
            "echo \"redirect 2> .agents/skills/x.md is the syntax\"",
        ],
    )
    def test_quoted_redirect_mention_passes(self, command: str) -> None:
        assert gase.decide("Bash", {"command": command}) is None

    @pytest.mark.parametrize(
        "command",
        [
            "echo x >.agents/skills/x.md",
            "echo x > .agents/skills/x.md",
            "echo x 2>.agents/skills/x.md",
            "echo x 2> .agents/skills/x.md",
            "echo x >>.claude/skills/x.md",
            "echo x >| .agents/skills/x.md",
            "echo x >|.agents/skills/x.md",
            "echo x 1>> .agents/skills/x.md",
        ],
    )
    def test_real_redirect_variants_still_denied(self, command: str) -> None:
        """Regression guard: the fix must not blind the gate to real redirects."""
        assert _is_deny(gase.decide("Bash", {"command": command}))


class TestFallbackRedirectDetection:
    """When shlex cannot tokenize (unbalanced quote), the gate falls back to a
    plain split and must STILL catch an attached redirect to a managed path.

    Regression guard for the /code-review #2123 finding: the shlex refactor
    classified redirects only as standalone operator tokens, but on the
    ``.split()`` fallback path the operator and its target are not separated, so
    an attached form like ``>.agents/skills/x`` was missed (a write bypass the
    pre-#2098 regex caught). The fallback matcher restores it.
    """

    # ``'unbalanced`` leaves an open quote, forcing the shlex ValueError fallback.
    _UNBAL = " 'unbalanced"

    @pytest.mark.parametrize(
        "command",
        [
            "echo x >.agents/skills/x.md" + _UNBAL,
            "echo x 2>.agents/skills/x.md" + _UNBAL,
            "echo x >>.claude/skills/x.md" + _UNBAL,
            "echo x >| .agents/skills/x.md" + _UNBAL,
            "echo x 2> .agents/skills/x.md" + _UNBAL,
        ],
    )
    def test_fallback_attached_redirect_denied(self, command: str) -> None:
        assert _is_deny(gase.decide("Bash", {"command": command}))

    def test_fallback_quoted_mention_still_passes(self) -> None:
        # On the fallback path the token keeps its literal quote char, so a
        # quoted mention does not match the fallback redirect regex.
        command = "echo '>.agents/skills/x.md' 'unbalanced"
        assert gase.decide("Bash", {"command": command}) is None


class TestAdversarialBashDetection:
    """Each known bypass / false-positive class from the PR #2092 Codex review.

    Pinned so a future change to the Bash heuristic cannot silently reopen one.
    """

    @pytest.mark.parametrize(
        "command",
        [
            # wrapper / cluster short-flag forms that carry an inline -c script
            "bash -lc 'cp a .agents/skills/x.md'",
            "sh -euc 'rm .claude/skills/x.md'",
            "bash -xc 'rm .agents/skills/x.md'",
            "zsh -c 'rm .claude/skills/x.md'",
            "dash -c 'cp a .agents/skills/x.md'",
            # nested shell recursion
            'bash -c \'bash -c "rm .agents/skills/x.md"\'',
        ],
    )
    def test_wrapper_cluster_flags_denied(self, command: str) -> None:
        assert _is_deny(gase.decide("Bash", {"command": command}))

    @pytest.mark.parametrize(
        "command",
        [
            # Documented defense-in-depth limitations: a wrapper with its own
            # option grammar (sudo/env) or a non-shell interpreter is not parsed.
            # Pinned so the boundary is explicit, not an accidental silent gap;
            # the Edit/Write matcher covers the primary edit path.
            "sudo rm .agents/skills/x.md",
            "env rm .claude/skills/x.md",
            "env FOO=bar cp a .agents/skills/x.md",
            "python3 -c \"open('.agents/skills/x.md','w')\"",
        ],
    )
    def test_documented_limitations_not_detected(self, command: str) -> None:
        assert gase.decide("Bash", {"command": command}) is None

    @pytest.mark.parametrize(
        "command",
        [
            # leading NAME=value assignments are skipped, so the real mutator is
            # still classified (distinct from the env-wrapper limitation above)
            "FOO=bar cp a .agents/skills/x.md",
            "A=1 B=2 rm .claude/skills/x.md",
        ],
    )
    def test_assignment_prefix_skipped_then_detected(self, command: str) -> None:
        assert _is_deny(gase.decide("Bash", {"command": command}))

    @pytest.mark.parametrize(
        "command",
        [
            # managed-directory root with no trailing slash (whole-tree ops)
            "rm -rf .agents/skills",
            "rm -rf .claude/skills",
            "mv .claude/skills /tmp/skills",
            "rm -rf /home/user/claude-md/.agents/skills",
        ],
    )
    def test_directory_root_denied(self, command: str) -> None:
        assert _is_deny(gase.decide("Bash", {"command": command}))

    @pytest.mark.parametrize(
        "command",
        [
            # separators inside a single-quoted argument are not command
            # boundaries, so the quoted 'rm'/'cp' is not a phantom mutator
            "git commit -m 'note ; rm .agents/skills/x.md'",
            "git commit -m 'a && cp z .claude/skills/x.md'",
            "git commit -m 'a || rm .agents/skills/x.md'",
            "git commit -m 'x | tee .claude/skills/y.md'",
            "git commit -m 'bg & rm .agents/skills/x.md'",
        ],
    )
    def test_quoted_separators_pass(self, command: str) -> None:
        assert gase.decide("Bash", {"command": command}) is None

    @pytest.mark.parametrize(
        "command",
        [
            # a real separator DOES start a new command, so a later-segment write
            # is still caught (the flip side of the quoted-separator guard)
            "ls ; rm .agents/skills/x.md",
            "ls && cp a .agents/skills/x.md",
            "false || rm .claude/skills/x.md",
            "cat tmpl | tee .agents/skills/x.md",
        ],
    )
    def test_real_separators_still_split(self, command: str) -> None:
        assert _is_deny(gase.decide("Bash", {"command": command}))


# Strategy: a clean path component (no shell metacharacters, no spaces) so the
# generated command's structure is exactly what the property asserts.
_NAME = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-",
    min_size=1,
    max_size=10,
)
_MANAGED_PREFIX = st.sampled_from(list(gase.MANAGED_PREFIXES))
# A short safe phrase (letters/digits/spaces only) to sit inside a quoted arg.
_PHRASE = st.text(alphabet="abcdefghijklmnopqrstuvwxyz ", min_size=0, max_size=20)


@st.composite
def _managed_path(draw: st.DrawFn) -> str:
    """A path under a managed prefix, e.g. ``.agents/skills/foo/bar.md``."""
    prefix = draw(_MANAGED_PREFIX)
    parts = draw(st.lists(_NAME, min_size=1, max_size=3))
    return prefix + "/".join(parts) + ".md"


class TestBashDetectionProperties:
    """Property tests over the Bash heuristic (issue #2098).

    Each property names the invariant it pins so a failure points at the spec.
    """

    @given(
        managed=_managed_path(),
        mutator=st.sampled_from(sorted(gase._WRITE_COMMANDS)),
    )
    def test_mutator_writing_managed_path_is_denied(
        self, managed: str, mutator: str
    ) -> None:
        # A mutating command carrying a managed path as a positional argument is
        # always a detected write target.
        assert gase.managed_write_targets(f"{mutator} src {managed}")

    @given(
        managed=_managed_path(),
        op=st.sampled_from([">", ">>", "2>", ">|", "1>"]),
        space=st.sampled_from(["", " "]),
    )
    def test_redirect_to_managed_path_is_denied(
        self, managed: str, op: str, space: str
    ) -> None:
        # Every output-redirection variant, attached or spaced, is detected.
        assert gase.managed_write_targets(f"echo x {op}{space}{managed}")

    @given(managed=_managed_path(), phrase=_PHRASE, sep=st.sampled_from([";", "&&", "||", "|", "&", ">", ">>"]))
    def test_quoted_mention_is_never_a_target(
        self, managed: str, phrase: str, sep: str
    ) -> None:
        # A separator or redirect inside a single-quoted argument is data, not a
        # command/redirection, so no managed write target is produced.
        command = f"git commit -m '{phrase}{sep} rm {managed}'"
        assert gase.managed_write_targets(command) == []

    @given(
        managed=_managed_path(),
        shell=st.sampled_from(sorted(gase._SHELL_COMMANDS)),
        cluster=st.sampled_from(["-c", "-lc", "-euc", "-xc"]),
    )
    def test_wrapper_cluster_flag_recurses(
        self, managed: str, shell: str, cluster: str
    ) -> None:
        # A mutator hidden in a `<shell> <cluster> '<script>'` wrapper is seen.
        assert gase.managed_write_targets(f"{shell} {cluster} 'rm {managed}'")

    @given(reader=st.sampled_from(["cat", "grep", "ls", "head", "tail", "wc"]), managed=_managed_path())
    def test_read_commands_are_allowed(self, reader: str, managed: str) -> None:
        # Reading a managed path is never blocked; only writes are.
        assert gase.managed_write_targets(f"{reader} {managed}") == []

    @given(prefix=_MANAGED_PREFIX, parts=st.lists(_NAME, min_size=1, max_size=2))
    def test_sibling_directory_never_matches(
        self, prefix: str, parts: list[str]
    ) -> None:
        # `.agents/skillset/...` is a sibling of `.agents/skills/...`; a mutator
        # targeting it must pass (the trailing-slash prefix guards the boundary).
        sibling = prefix.rstrip("/") + "et/" + "/".join(parts) + ".md"
        assert gase.managed_write_targets(f"rm -rf {sibling}") == []


class TestVerifyMode:
    """CI ``verify`` mode: the post-merge-tree counterpart to the hook (#2098).

    A PR may edit a managed tree path only when the SPECIFIC apm dependency
    that owns that path (per apm.lock.yaml's deployed_files) actually moved
    its pin; a different dependency's pin bump does not excuse it (Codex
    review on #2186/#2185). A managed diff with no owning-pin change is a
    hand edit and fails.
    """

    @pytest.mark.parametrize(
        "managed,offending,expected_code",
        [
            (frozenset(), frozenset(), 0),  # nothing managed -> trivially passes
            (frozenset({".agents/skills/b/SKILL.md"}), frozenset(), 0),  # excused
            (
                frozenset({".agents/skills/b/SKILL.md"}),
                frozenset({".agents/skills/b/SKILL.md"}),
                1,
            ),  # hand edit
        ],
    )
    def test_evaluate_pr(
        self, managed: frozenset[str], offending: frozenset[str], expected_code: int
    ) -> None:
        code, errors = gase.evaluate_pr(managed, offending)
        assert code == expected_code
        assert (errors == []) is (expected_code == 0)

    def test_managed_changes_filters_to_prefixes(self) -> None:
        changed = frozenset(
            {".agents/skills/a", ".claude/skills/b", ".agents/skillset/c", "scripts/d.py"}
        )
        assert gase.managed_changes(changed) == frozenset(
            {".agents/skills/a", ".claude/skills/b"}
        )

    def test_apm_pins_extracts_ref(self) -> None:
        apm_yml = "dependencies:\n  apm:\n  - obra/superpowers#abc123def\n"
        completed = SimpleNamespace(stdout=apm_yml)
        assert gase._apm_pins("HEAD", runner=lambda *a, **k: completed) == {
            "obra/superpowers": "abc123def"
        }

    def test_apm_pins_extracts_multiple_deps(self) -> None:
        apm_yml = (
            "dependencies:\n  apm:\n  - obra/superpowers#abc123def\n"
            "  - tvna/clairvoyance#deadbeef\n"
        )
        completed = SimpleNamespace(stdout=apm_yml)
        assert gase._apm_pins("HEAD", runner=lambda *a, **k: completed) == {
            "obra/superpowers": "abc123def",
            "tvna/clairvoyance": "deadbeef",
        }

    def test_apm_pins_empty_when_token_absent(self) -> None:
        completed = SimpleNamespace(stdout="dependencies:\n  apm: []\n")
        assert gase._apm_pins("HEAD", runner=lambda *a, **k: completed) == {}

    def test_apm_pins_none_on_git_error(self) -> None:
        def _boom(*_a: Any, **_k: Any) -> Any:
            raise subprocess.CalledProcessError(128, ["git", "show"])

        assert gase._apm_pins("nope", runner=_boom) is None

    @pytest.mark.parametrize(
        "apm_yml,expected",
        [
            # /code-review #2123: a YAML-quoted pin must not capture the trailing
            # quote, or a quoting difference base vs head would falsely compare
            # unequal and let a hand edit pass.
            ('  - "obra/superpowers#abc123"\n', "abc123"),
            ("  - obra/superpowers#abc123  # pinned\n", "abc123"),
            # a commented-out dependency line must not shadow the active pin
            # (else a legitimate regen would falsely compare unchanged and fail).
            ("#  - obra/superpowers#OLDREF\n  - obra/superpowers#abc123\n", "abc123"),
        ],
    )
    def test_apm_pins_ignores_quotes_and_comments(self, apm_yml: str, expected: str) -> None:
        completed = SimpleNamespace(stdout=apm_yml)
        assert gase._apm_pins("HEAD", runner=lambda *a, **k: completed) == {
            "obra/superpowers": expected
        }

    def test_lock_deployed_files_extracts_per_repo(self) -> None:
        lock_yaml = (
            "dependencies:\n"
            "- repo_url: obra/superpowers\n"
            "  deployed_files:\n"
            "  - .agents/skills/a/SKILL.md\n"
            "- repo_url: tvna/clairvoyance\n"
            "  deployed_files:\n"
            "  - .agents/skills/b/SKILL.md\n"
        )
        completed = SimpleNamespace(stdout=lock_yaml)
        assert gase._lock_deployed_files("HEAD", runner=lambda *a, **k: completed) == {
            "obra/superpowers": frozenset({".agents/skills/a/SKILL.md"}),
            "tvna/clairvoyance": frozenset({".agents/skills/b/SKILL.md"}),
        }

    def test_lock_deployed_files_none_on_git_error(self) -> None:
        def _boom(*_a: Any, **_k: Any) -> Any:
            raise subprocess.CalledProcessError(128, ["git", "show"])

        assert gase._lock_deployed_files("nope", runner=_boom) is None

    def test_owning_repo_by_path_inverts_mapping(self) -> None:
        deployed_by_repo = {
            "obra/superpowers": frozenset({"a", "b"}),
            "tvna/clairvoyance": frozenset({"c"}),
        }
        assert gase._owning_repo_by_path(deployed_by_repo) == {
            "a": "obra/superpowers",
            "b": "obra/superpowers",
            "c": "tvna/clairvoyance",
        }

    def test_offending_paths_excuses_only_the_owning_dependency(self) -> None:
        # Codex review on #2186/#2185: bumping tvna/clairvoyance must not
        # excuse a hand edit under an obra/superpowers-owned path.
        managed = frozenset({".agents/skills/brainstorming/SKILL.md", ".agents/skills/clairvoyance/SKILL.md"})
        owning_repo = {
            ".agents/skills/brainstorming/SKILL.md": "obra/superpowers",
            ".agents/skills/clairvoyance/SKILL.md": "tvna/clairvoyance",
        }
        base_pins = {"obra/superpowers": "old", "tvna/clairvoyance": "old"}
        head_pins = {"obra/superpowers": "old", "tvna/clairvoyance": "new"}
        assert gase.offending_paths(managed, owning_repo, base_pins, head_pins) == frozenset(
            {".agents/skills/brainstorming/SKILL.md"}
        )

    def test_offending_paths_passes_when_owning_pin_moves(self) -> None:
        managed = frozenset({".agents/skills/brainstorming/SKILL.md"})
        owning_repo = {".agents/skills/brainstorming/SKILL.md": "obra/superpowers"}
        base_pins = {"obra/superpowers": "old"}
        head_pins = {"obra/superpowers": "new"}
        assert gase.offending_paths(managed, owning_repo, base_pins, head_pins) == frozenset()

    def test_offending_paths_unattributable_path_falls_back_to_any_pin_changed(self) -> None:
        managed = frozenset({"some/legacy/path"})
        base_pins = {"obra/superpowers": "old"}
        head_pins = {"obra/superpowers": "new"}
        assert gase.offending_paths(managed, {}, base_pins, head_pins) == frozenset()
        assert gase.offending_paths(managed, {}, base_pins, base_pins) == frozenset(
            {"some/legacy/path"}
        )

    def test_offending_paths_fails_closed_when_pins_unresolvable(self) -> None:
        managed = frozenset({".agents/skills/x/SKILL.md"})
        assert gase.offending_paths(managed, {}, None, {"a": "b"}) == managed
        assert gase.offending_paths(managed, {}, {"a": "b"}, None) == managed

    def test_verify_cli_passes_when_no_managed_change(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(gase, "_changed_files", lambda *a, **k: frozenset({"scripts/x.py"}))
        assert gase.main(["verify", "--base-ref", "origin/main"]) == 0
        assert "OK" in capsys.readouterr().out

    def test_verify_cli_fails_on_hand_edit(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Managed tree changed but the owning pin is identical at base and head,
        # and there is no lockfile attribution (falls back to any-pin-changed).
        monkeypatch.setattr(
            gase, "_changed_files", lambda *a, **k: frozenset({".agents/skills/x/SKILL.md"})
        )
        monkeypatch.setattr(gase, "_apm_pins", lambda *a, **k: {"obra/superpowers": "samepin"})
        monkeypatch.setattr(gase, "_lock_deployed_files", lambda *a, **k: None)
        assert gase.main(["verify", "--base-ref", "origin/main"]) == 1
        err = capsys.readouterr().err
        assert ".agents/skills/x/SKILL.md" in err
        assert "apm compile" in err

    def test_verify_cli_passes_on_pin_bump(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Managed tree changed AND the resolved pin actually moved base -> head.
        monkeypatch.setattr(
            gase,
            "_changed_files",
            lambda *a, **k: frozenset({".claude/skills/x/SKILL.md", "apm.lock.yaml"}),
        )
        monkeypatch.setattr(
            gase,
            "_apm_pins",
            lambda ref, **k: {"obra/superpowers": "oldpin"}
            if ref == "origin/main"
            else {"obra/superpowers": "newpin"},
        )
        monkeypatch.setattr(gase, "_lock_deployed_files", lambda *a, **k: None)
        assert gase.main(["verify", "--base-ref", "origin/main"]) == 0

    def test_verify_cli_passes_on_new_dependency_added_for_its_own_paths(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # A wholly new apm dependency (e.g. tvna/clairvoyance) appearing in the
        # pin set is a legitimate pin change for the paths IT owns (#2185).
        monkeypatch.setattr(
            gase,
            "_changed_files",
            lambda *a, **k: frozenset({".claude/skills/clairvoyance/SKILL.md", "apm.yml"}),
        )
        monkeypatch.setattr(
            gase,
            "_apm_pins",
            lambda ref, **k: {"obra/superpowers": "pin"}
            if ref == "origin/main"
            else {"obra/superpowers": "pin", "tvna/clairvoyance": "newpin"},
        )
        monkeypatch.setattr(
            gase,
            "_lock_deployed_files",
            lambda *a, **k: {
                "tvna/clairvoyance": frozenset({".claude/skills/clairvoyance/SKILL.md"})
            },
        )
        assert gase.main(["verify", "--base-ref", "origin/main"]) == 0

    def test_verify_cli_fails_when_unrelated_dependency_pin_bumped(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Codex review on #2186/#2185: bumping tvna/clairvoyance must not excuse
        # a hand edit under an obra/superpowers-owned path.
        monkeypatch.setattr(
            gase,
            "_changed_files",
            lambda *a, **k: frozenset({".agents/skills/brainstorming/SKILL.md"}),
        )
        monkeypatch.setattr(
            gase,
            "_apm_pins",
            lambda ref, **k: {"obra/superpowers": "pin", "tvna/clairvoyance": "old"}
            if ref == "origin/main"
            else {"obra/superpowers": "pin", "tvna/clairvoyance": "new"},
        )
        monkeypatch.setattr(
            gase,
            "_lock_deployed_files",
            lambda *a, **k: {
                "obra/superpowers": frozenset({".agents/skills/brainstorming/SKILL.md"}),
                "tvna/clairvoyance": frozenset({".agents/skills/clairvoyance/SKILL.md"}),
            },
        )
        assert gase.main(["verify", "--base-ref", "origin/main"]) == 1
        err = capsys.readouterr().err
        assert ".agents/skills/brainstorming/SKILL.md" in err

    def test_verify_cli_fails_when_apm_yml_touched_but_pin_unchanged(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Codex review on #2098: an incidental apm.yml edit (version / MCP config)
        # with an unchanged pin must NOT excuse a managed-tree edit.
        monkeypatch.setattr(
            gase,
            "_changed_files",
            lambda *a, **k: frozenset({".agents/skills/x/SKILL.md", "apm.yml"}),
        )
        monkeypatch.setattr(gase, "_apm_pins", lambda *a, **k: {"obra/superpowers": "samepin"})
        monkeypatch.setattr(gase, "_lock_deployed_files", lambda *a, **k: None)
        assert gase.main(["verify", "--base-ref", "origin/main"]) == 1
        assert "without their owning apm dependency's pin changing" in capsys.readouterr().err

    def test_verify_cli_fails_loud_on_git_error(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        def _boom(*_a: Any, **_k: Any) -> frozenset[str]:
            raise subprocess.CalledProcessError(1, ["git", "diff"])

        monkeypatch.setattr(gase, "_changed_files", _boom)
        assert gase.main(["verify", "--base-ref", "origin/main"]) == 1
        assert "git diff" in capsys.readouterr().err

    def test_main_without_verify_arg_runs_hook(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """No leading ``verify`` -> the PreToolUse hook path (stdin), not the CLI."""
        event = {"tool_name": "Write", "tool_input": {"file_path": ".agents/skills/x.md"}}
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(event)))
        assert gase.main([]) == 0
        assert _is_deny(json.loads(capsys.readouterr().out))

    def test_resolve_base_precedence(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("BASE_REF", raising=False)
        monkeypatch.delenv("GITHUB_BASE_REF", raising=False)
        assert gase._resolve_base() == "origin/main"
        monkeypatch.setenv("GITHUB_BASE_REF", "release")
        assert gase._resolve_base() == "origin/release"
        monkeypatch.setenv("BASE_REF", "deadbeef")
        assert gase._resolve_base() == "deadbeef"

    def test_changed_files_parses_runner_output(self) -> None:
        """_changed_files splits and strips the runner's stdout (no real git)."""
        completed = SimpleNamespace(stdout=".agents/skills/a\n\n  scripts/b.py  \n")
        changed = gase._changed_files("origin/main", runner=lambda *a, **k: completed)
        assert changed == frozenset({".agents/skills/a", "scripts/b.py"})
