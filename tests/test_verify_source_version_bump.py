"""Tests for ``scripts/verify_source_version_bump.py``.

Table-driven style: the pure functions get parametrize cases; the
subprocess boundary is exercised via a fake ``runner`` injected through
the ``runner`` kwarg the production code already exposes.

The ``scripts/`` directory is on ``sys.path`` via ``pythonpath`` under
``[tool.pytest.ini_options]`` in ``pyproject.toml``. Refs #89.
"""

from __future__ import annotations

import subprocess
from typing import Any

import pytest
import verify_source_version_bump as gate

pytestmark = pytest.mark.shard_ci_ops


# --------------------------------------------------------------------------
# parse_version / format_version
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("version: 1.0.0\n", (1, 0, 0)),
        ("name: x\nversion: 2.13.4\ntarget:\n- claude\n", (2, 13, 4)),
        ("version:   0.0.1   \n", (0, 0, 1)),
    ],
)
def test_parse_version_ok(text: str, expected: gate.Version) -> None:
    assert gate.parse_version(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "name: x\n",
        "version: 1.0\n",
        "version: v1.0.0\n",
        "version: 1.0.0-rc1\n",
        "",
    ],
)
def test_parse_version_raises_on_malformed(text: str) -> None:
    with pytest.raises(ValueError):
        gate.parse_version(text)


def test_format_version_roundtrip() -> None:
    assert gate.format_version((1, 2, 3)) == "1.2.3"


# --------------------------------------------------------------------------
# universal-text detection (R3)
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("CLAUDE.md", True),
        ("AGENTS.md", True),
        (".apm/instructions/master.instructions.md", True),
        ("  CLAUDE.md  ", True),
        ("apm.yml", False),
        (".apm/instructions/other.md", False),
        ("docs/CLAUDE.md", False),
        ("README.md", False),
    ],
)
def test_is_universal_text_path(path: str, expected: bool) -> None:
    assert gate.is_universal_text_path(path) is expected


def test_touches_universal_text_true_and_false() -> None:
    assert gate.touches_universal_text(frozenset({"apm.yml", "CLAUDE.md"}))
    assert not gate.touches_universal_text(frozenset({"apm.yml", "README.md"}))
    assert not gate.touches_universal_text(frozenset())


# --------------------------------------------------------------------------
# bump_component
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("base", "head", "expected"),
    [
        ((1, 2, 3), (2, 0, 0), "major"),
        ((1, 2, 3), (1, 3, 0), "minor"),
        ((1, 2, 3), (1, 2, 4), "patch"),
        ((1, 2, 3), (1, 2, 10), "patch"),
        ((0, 0, 0), (1, 0, 0), "major"),
        # invalid transitions
        ((1, 2, 3), (1, 2, 3), None),  # no change
        ((1, 2, 3), (1, 2, 2), None),  # decrease
        ((1, 2, 3), (2, 1, 0), None),  # major bumped, minor not reset
        ((1, 2, 3), (1, 3, 5), None),  # minor bumped, patch not reset
        ((2, 0, 0), (1, 0, 0), None),  # major decrease
        ((1, 2, 3), (2, 0, 1), None),  # major bumped, patch not reset
    ],
)
def test_bump_component(
    base: gate.Version, head: gate.Version, expected: str | None
) -> None:
    assert gate.bump_component(base, head) == expected


# --------------------------------------------------------------------------
# extract_semver_labels
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("labels", "expected"),
    [
        (["semver:minor"], ["minor"]),
        (["type:feat", "semver:major", "area:apm"], ["major"]),
        ([], []),
        (["type:feat"], []),
        (["semver:minor", "semver:patch"], ["minor", "patch"]),
        (["semver:bogus"], []),
        (["  semver:patch  "], ["patch"]),
    ],
)
def test_extract_semver_labels(
    labels: list[str], expected: list[str]
) -> None:
    assert gate.extract_semver_labels(labels) == expected


# --------------------------------------------------------------------------
# evaluate; the decision core
# --------------------------------------------------------------------------


def test_evaluate_noop_passes() -> None:
    code, errors = gate.evaluate(False, (1, 0, 0), (1, 0, 0), [])
    assert code == 0
    assert errors == []


def test_evaluate_text_without_bump_fails() -> None:
    code, errors = gate.evaluate(True, (1, 0, 0), (1, 0, 0), ["semver:minor"])
    assert code == 1
    assert len(errors) == 1
    assert "does not bump 'version'" in errors[0]
    assert errors[0].startswith("::error file=apm.yml::")


def test_evaluate_bump_without_text_fails() -> None:
    code, errors = gate.evaluate(False, (1, 0, 0), (1, 1, 0), [])
    assert code == 1
    assert len(errors) == 1
    assert "changes none of the universal-text files" in errors[0]
    assert errors[0].startswith("::error file=apm.yml::")


def test_evaluate_both_changed_happy_path() -> None:
    code, errors = gate.evaluate(True, (1, 0, 0), (1, 1, 0), ["semver:minor"])
    assert code == 0
    assert errors == []


@pytest.mark.parametrize(
    ("base", "head", "labels"),
    [
        ((1, 0, 0), (2, 0, 0), ["semver:major"]),
        ((1, 2, 3), (1, 2, 4), ["semver:patch"]),
    ],
)
def test_evaluate_both_changed_each_component(
    base: gate.Version, head: gate.Version, labels: list[str]
) -> None:
    code, errors = gate.evaluate(True, base, head, labels)
    assert code == 0
    assert errors == []


def test_evaluate_unclean_bump_fails() -> None:
    code, errors = gate.evaluate(True, (1, 2, 3), (2, 1, 0), ["semver:major"])
    assert code == 1
    assert "not a clean single-component bump" in errors[0]


def test_evaluate_no_label_fails() -> None:
    code, errors = gate.evaluate(True, (1, 0, 0), (1, 1, 0), [])
    assert code == 1
    assert "exactly one semver" in errors[0]
    assert "found 0" in errors[0]


def test_evaluate_multiple_labels_fail() -> None:
    code, errors = gate.evaluate(
        True, (1, 0, 0), (1, 1, 0), ["semver:minor", "semver:patch"]
    )
    assert code == 1
    assert "found 2" in errors[0]


def test_evaluate_label_mismatch_fails() -> None:
    code, errors = gate.evaluate(True, (1, 0, 0), (1, 1, 0), ["semver:major"])
    assert code == 1
    assert "declares 'major'" in errors[0]
    assert "bumps the 'minor'" in errors[0]


# labels=None (pre-push): label-match skipped, iff and clean-bump kept.


def test_evaluate_labels_none_skips_label_match() -> None:
    code, errors = gate.evaluate(True, (1, 0, 0), (1, 1, 0), None)
    assert code == 0
    assert errors == []


def test_evaluate_labels_none_still_enforces_iff() -> None:
    code, errors = gate.evaluate(True, (1, 0, 0), (1, 0, 0), None)
    assert code == 1
    assert "does not bump 'version'" in errors[0]


def test_evaluate_labels_none_still_enforces_clean_bump() -> None:
    code, errors = gate.evaluate(True, (1, 2, 3), (2, 1, 0), None)
    assert code == 1
    assert "not a clean single-component bump" in errors[0]


# --------------------------------------------------------------------------
# git boundary; fake runner
# --------------------------------------------------------------------------


def _fake_runner(responses: dict[str, str]):
    """Return a runner keyed by a substring of the git command."""

    def runner(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        joined = " ".join(cmd)
        for needle, stdout in responses.items():
            if needle in joined:
                return subprocess.CompletedProcess(cmd, 0, stdout=stdout, stderr="")
        raise AssertionError(f"unexpected command: {joined}")

    return runner


def test_changed_files_parses_diff() -> None:
    runner = _fake_runner({"diff": "CLAUDE.md\napm.yml\n\n"})
    assert gate.changed_files("origin/main", runner=runner) == frozenset(
        {"CLAUDE.md", "apm.yml"}
    )


def test_read_version_at_reads_apm() -> None:
    runner = _fake_runner({"show": "name: x\nversion: 3.4.5\n"})
    assert gate.read_version_at("HEAD", runner=runner) == (3, 4, 5)


def test_resolve_labels_from_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PR_LABELS", raising=False)
    args = gate.argparse.Namespace(labels="semver:minor, type:feat")
    assert gate._resolve_labels(args) == ["semver:minor", "type:feat"]


def test_resolve_labels_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PR_LABELS", "semver:patch,area:apm")
    args = gate.argparse.Namespace(labels=None)
    assert gate._resolve_labels(args) == ["semver:patch", "area:apm"]


def test_resolve_labels_env_present_but_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PR_LABELS", "")
    args = gate.argparse.Namespace(labels=None)
    assert gate._resolve_labels(args) == []


def test_resolve_labels_absent_is_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PR_LABELS", raising=False)
    args = gate.argparse.Namespace(labels=None)
    assert gate._resolve_labels(args) is None


# --------------------------------------------------------------------------
# verify subcommand end-to-end (monkeypatched boundary)
# --------------------------------------------------------------------------


def _patch_boundary(
    monkeypatch: pytest.MonkeyPatch,
    *,
    changed: set[str],
    base_version: str,
    head_version: str,
) -> None:
    monkeypatch.setattr(
        gate, "changed_files", lambda *a, **k: frozenset(changed)
    )
    versions = iter([base_version, head_version])
    monkeypatch.setattr(
        gate,
        "read_version_at",
        lambda ref, **k: gate.parse_version(next(versions)),
    )


def test_verify_cmd_happy_path(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("PR_LABELS", raising=False)
    _patch_boundary(
        monkeypatch,
        changed={"CLAUDE.md", "apm.yml"},
        base_version="version: 1.0.0\n",
        head_version="version: 1.1.0\n",
    )
    rc = gate.main(["verify", "--base-ref", "origin/main", "--labels", "semver:minor"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "OK: universal text and apm.yml version bumped together" in out


def test_verify_cmd_drift_fails(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _patch_boundary(
        monkeypatch,
        changed={"CLAUDE.md"},
        base_version="version: 1.0.0\n",
        head_version="version: 1.0.0\n",
    )
    rc = gate.main(["verify", "--base-ref", "origin/main", "--labels", "semver:minor"])
    out = capsys.readouterr().out
    assert rc == 1
    assert "::error file=apm.yml::" in out


def test_verify_cmd_prepush_no_labels_passes(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("PR_LABELS", raising=False)
    _patch_boundary(
        monkeypatch,
        changed={"AGENTS.md", "apm.yml"},
        base_version="version: 1.0.0\n",
        head_version="version: 2.0.0\n",
    )
    rc = gate.main(["verify", "--base-ref", "origin/main"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "labels not checked (pre-push)" in out


def test_verify_cmd_git_failure_is_loud(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def boom(*a: Any, **k: Any) -> frozenset[str]:
        raise subprocess.CalledProcessError(128, ["git"], stderr="bad rev")

    monkeypatch.setattr(gate, "changed_files", boom)
    rc = gate.main(["verify", "--base-ref", "origin/nope"])
    err = capsys.readouterr().err
    assert rc == 1
    assert "could not read the version-bump inputs" in err
