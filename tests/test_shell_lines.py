"""Tests for ``scripts/_shell_lines.py``.

The shared flattener joins POSIX shell backslash continuations into logical
lines so the shell/YAML-scanning gates cannot be bypassed by splitting a
two-token command across a ``\\`` continuation. Refs #2164, #2163, #2143.
"""

from __future__ import annotations

import pytest
from _shell_lines import flatten_shell_continuations

pytestmark = pytest.mark.shard_preflight


def test_plain_lines_pass_through_with_line_numbers() -> None:
    text = "alpha\nbeta\ngamma\n"
    assert flatten_shell_continuations(text) == [
        (1, "alpha"),
        (2, "beta"),
        (3, "gamma"),
    ]


def test_single_continuation_joins_and_reports_first_line() -> None:
    # ``uv run ruff \`` then ``format scripts`` -> one logical line, numbered
    # at the first physical line of the command.
    text = "noop\nuv run ruff \\\n  format scripts\ndone\n"
    assert flatten_shell_continuations(text) == [
        (1, "noop"),
        (2, "uv run ruff format scripts"),
        (4, "done"),
    ]


def test_multi_line_continuation_chain_joins_all_parts() -> None:
    text = "git \\\n  push \\\n  --force origin main\n"
    assert flatten_shell_continuations(text) == [(1, "git push --force origin main")]


def test_doubled_backslash_is_not_a_continuation() -> None:
    # A trailing escaped ``\\`` ends the logical line; the next line is separate.
    text = "echo done\\\\\nnext line\n"
    assert flatten_shell_continuations(text) == [
        (1, "echo done\\\\"),
        (2, "next line"),
    ]


def test_trailing_continuation_with_no_successor_is_flushed() -> None:
    # A dangling continuation at EOF still emits its accumulated logical line.
    text = "pip \\\n  install requests \\"
    assert flatten_shell_continuations(text) == [(1, "pip install requests")]


def test_parts_are_whitespace_normalised_at_join() -> None:
    text = "a    \\\n      b\n"
    assert flatten_shell_continuations(text) == [(1, "a b")]


def test_empty_text_returns_empty_list() -> None:
    assert flatten_shell_continuations("") == []


def test_comment_line_does_not_continue() -> None:
    # A `#` comment does not continue across a trailing backslash (verified in
    # sh/bash): the next physical line is a separate command, so it must NOT be
    # absorbed into the comment, else a gate's comment-skip swallows a real
    # violation (issue #2164, code-review on PR #2175).
    text = "# note \\\n  pip install requests\ndone\n"
    assert flatten_shell_continuations(text) == [
        (1, "# note \\"),
        (2, "  pip install requests"),
        (3, "done"),
    ]


def test_odd_run_of_three_backslashes_continues() -> None:
    # Real shell continues iff the trailing backslash run is odd. Three trailing
    # backslashes (escaped backslash + escaping newline) continues.
    text = "gh \\\\\\\n  api repos/o/r\n"
    assert flatten_shell_continuations(text) == [(1, "gh \\\\ api repos/o/r")]


def test_even_run_of_two_backslashes_does_not_continue() -> None:
    text = "echo done\\\\\nnext\n"
    assert flatten_shell_continuations(text) == [(1, "echo done\\\\"), (2, "next")]


def test_backslash_then_trailing_whitespace_does_not_continue() -> None:
    # `\` followed by a space escapes the space, not the newline; no continuation.
    text = "pip \\ \n  install requests\n"
    assert flatten_shell_continuations(text) == [
        (1, "pip \\ "),
        (2, "  install requests"),
    ]
