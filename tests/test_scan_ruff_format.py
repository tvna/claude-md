"""Tests for ``scripts/scan_ruff_format.py``.

The gate keeps ``ruff format`` off the repository's gate surfaces (workflow
YAML, the ``.githooks`` hooks, ``.pre-commit-config.yaml``, and the preflight
manifest); CI enforces ``ruff check`` only. Refs #2143, #2141.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import scan_ruff_format as gate

pytestmark = pytest.mark.shard_preflight


# ---------------------------------------------------------------------------
# scan_line / scan_text
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("line", "hit"),
    [
        ("        run: uv run ruff format scripts", True),
        ("ruff format --check scripts tests", True),
        ("uv run ruff   format tests/foo.py", True),  # extra spacing tolerated
        ("        run: uv run ruff check scripts tests", False),  # the real gate
        ("# do not run ruff format here", False),  # pure comment line
        ("      - name: Assert no ruff format on gate surfaces", False),  # YAML label, not a command
        ("    name: run ruff format", False),  # label without list dash
        ("run: ruff format scripts  <!-- ruff-format-ack -->", False),  # ack escape
        ("echo 'reformatting done'", False),  # 'reformat' must not match
    ],
)
def test_scan_line(line: str, hit: bool) -> None:
    assert gate.scan_line(line) is hit


def test_scan_text_returns_line_numbers() -> None:
    text = "line one\nuv run ruff format x\nruff check y\n  ruff format z\n"
    assert gate.scan_text(text) == [2, 4]


def test_scan_text_flattens_shell_continuation() -> None:
    # A `ruff format` split across a shell `\` continuation must still be
    # caught, reported at the first physical line of the command (Codex review).
    text = "noop\nuv run ruff \\\n  format scripts\ndone\n"
    assert gate.scan_text(text) == [2]


def test_scan_text_continuation_does_not_false_positive_on_ruff_check() -> None:
    # `ruff \` then `check` must NOT match: only `ruff format` is banned.
    text = "uv run ruff \\\n  check scripts tests\n"
    assert gate.scan_text(text) == []


def test_scan_text_comment_continuation_does_not_hide_following_command() -> None:
    # A `#` comment ending in `\` does not continue in real shell, so a real
    # `ruff format` on the next physical line must still be caught (it is not
    # absorbed into the comment). Regression for the code-review bypass on #2175.
    text = "# was: \\\n  uv run ruff format scripts\n"
    assert gate.scan_text(text) == [2]


def test_find_text_violations_flags_continued_invocation(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    (repo / ".githooks" / "pre-push").write_text("uv run ruff \\\n  format tests\n", encoding="utf-8")
    rels = {str(rel) for rel, _ in gate.find_text_violations(repo)}
    assert ".githooks/pre-push" in rels


# ---------------------------------------------------------------------------
# find_text_violations (filesystem boundary)
# ---------------------------------------------------------------------------


def _make_repo(tmp_path: Path) -> Path:
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / ".githooks").mkdir()
    return tmp_path


def test_find_text_violations_flags_composite_action(tmp_path: Path) -> None:
    # A composite action's run: shell executes inline in CI, so it is a gate
    # surface: a `ruff format` there must be caught (code-review follow-up).
    repo = _make_repo(tmp_path)
    action_dir = repo / ".github" / "actions" / "fmt"
    action_dir.mkdir(parents=True)
    (action_dir / "action.yml").write_text(
        "runs:\n  using: composite\n  steps:\n    - run: uv run ruff format scripts\n      shell: bash\n",
        encoding="utf-8",
    )
    rels = {str(rel) for rel, _ in gate.find_text_violations(repo)}
    assert ".github/actions/fmt/action.yml" in rels


def test_find_text_violations_clean_repo(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    (repo / ".github" / "workflows" / "verify.yml").write_text("run: uv run ruff check scripts tests\n", encoding="utf-8")
    (repo / ".pre-commit-config.yaml").write_text("repos: []\n", encoding="utf-8")
    assert gate.find_text_violations(repo) == []


def test_find_text_violations_flags_workflow_and_hook(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    (repo / ".github" / "workflows" / "verify.yml").write_text("a\nrun: uv run ruff format scripts\n", encoding="utf-8")
    (repo / ".githooks" / "pre-commit").write_text("ruff format tests\n", encoding="utf-8")
    rels = {str(rel) for rel, _ in gate.find_text_violations(repo)}
    assert rels == {".github/workflows/verify.yml", ".githooks/pre-commit"}


def test_find_text_violations_skips_absent_surfaces(tmp_path: Path) -> None:
    # An empty repo with no workflow dir and no hooks has nothing to scan.
    assert gate.find_text_violations(tmp_path) == []


# ---------------------------------------------------------------------------
# find_manifest_violations (preflight STEPS argv)
# ---------------------------------------------------------------------------


def test_find_manifest_violations_real_manifest_is_clean() -> None:
    # The live preflight manifest must never invoke 'ruff format'.
    assert gate.find_manifest_violations() == []


def test_find_manifest_violations_detects_split_argv(monkeypatch: pytest.MonkeyPatch) -> None:
    # A 'ruff format' step split across a tuple ("ruff", "format") that a text
    # regex would miss must still be detected via the argv subsequence check.
    import preflight_steps

    bad = preflight_steps.Step(name="ruff_format_injected", argv=("uv", "run", "ruff", "format", "scripts"))
    monkeypatch.setattr(preflight_steps, "STEPS", (*preflight_steps.STEPS, bad))
    assert "ruff_format_injected" in gate.find_manifest_violations()


# ---------------------------------------------------------------------------
# main / verify
# ---------------------------------------------------------------------------


def test_verify_passes_on_live_repo(capsys: pytest.CaptureFixture[str]) -> None:
    # The real repository must pass: this is the gate's own green baseline.
    assert gate.main(["verify"]) == 0
    assert "OK: no 'ruff format'" in capsys.readouterr().out


def test_verify_fails_on_dirty_repo(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = _make_repo(tmp_path)
    (repo / ".github" / "workflows" / "verify.yml").write_text("run: uv run ruff format scripts\n", encoding="utf-8")
    assert gate.main(["verify", "--repo-root", str(repo)]) == 1
    err = capsys.readouterr().err
    assert "ruff format" in err
    assert "FAIL:" in err


# ---------------------------------------------------------------------------
# annotation escaping (defence-in-depth)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "escaped"),
    [
        ("a:b,c%d", "a%3Ab%2Cc%25d"),  # % escaped first, then : and ,
        (".github/actions/x::y/action.yml", ".github/actions/x%3A%3Ay/action.yml"),
        ("plain/path.yml", "plain/path.yml"),  # nothing to escape
    ],
)
def test_escape_annotation_property(raw: str, escaped: str) -> None:
    assert gate._escape_annotation_property(raw) == escaped


def test_verify_escapes_crafted_path_in_annotation(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    # A PR-authored path containing '::' must not break out of the file=
    # property of the ::error annotation; it is percent-escaped instead.
    crafted = Path(".github/actions/x::y/action.yml")
    monkeypatch.setattr(gate, "find_text_violations", lambda _root: [(crafted, 1)])
    monkeypatch.setattr(gate, "find_manifest_violations", lambda: [])
    assert gate.main(["verify"]) == 1
    err = capsys.readouterr().err
    assert "x%3A%3Ay" in err
    assert "::error file=.github/actions/x::y" not in err  # raw '::' did not leak
