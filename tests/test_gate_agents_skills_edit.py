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

    A PR may edit a managed tree only alongside a pin change (apm.yml /
    apm.lock.yaml); a managed diff with no pin diff is a hand edit and fails.
    """

    @pytest.mark.parametrize(
        "changed,expected_code",
        [
            (frozenset(), 0),
            (frozenset({"scripts/foo.py", "docs/x.md"}), 0),
            (frozenset({".agents/skillset/x.md"}), 0),  # sibling, not managed
            (frozenset({".agents/skills/b/SKILL.md"}), 1),  # hand edit
            (frozenset({".claude/skills/b/SKILL.md"}), 1),  # hand edit
            # managed change WITH a pin bump is a legitimate regeneration
            (frozenset({".agents/skills/b/SKILL.md", "apm.yml"}), 0),
            (frozenset({".claude/skills/b/SKILL.md", "apm.lock.yaml"}), 0),
            (frozenset({".agents/skills/b", "apm.yml", "scripts/z.py"}), 0),
        ],
    )
    def test_evaluate_pr(self, changed: frozenset[str], expected_code: int) -> None:
        code, errors = gase.evaluate_pr(changed)
        assert code == expected_code
        assert (errors == []) is (expected_code == 0)

    def test_managed_changes_filters_to_prefixes(self) -> None:
        changed = frozenset(
            {".agents/skills/a", ".claude/skills/b", ".agents/skillset/c", "scripts/d.py"}
        )
        assert gase.managed_changes(changed) == frozenset(
            {".agents/skills/a", ".claude/skills/b"}
        )

    def test_verify_cli_passes_when_no_managed_change(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(gase, "_changed_files", lambda *a, **k: frozenset({"scripts/x.py"}))
        assert gase.main(["verify", "--base-ref", "origin/main"]) == 0
        assert "OK" in capsys.readouterr().out

    def test_verify_cli_fails_on_hand_edit(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(
            gase, "_changed_files", lambda *a, **k: frozenset({".agents/skills/x/SKILL.md"})
        )
        assert gase.main(["verify", "--base-ref", "origin/main"]) == 1
        err = capsys.readouterr().err
        assert ".agents/skills/x/SKILL.md" in err
        assert "apm compile" in err

    def test_verify_cli_passes_on_pin_bump(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            gase,
            "_changed_files",
            lambda *a, **k: frozenset({".claude/skills/x/SKILL.md", "apm.lock.yaml"}),
        )
        assert gase.main(["verify", "--base-ref", "origin/main"]) == 0

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
