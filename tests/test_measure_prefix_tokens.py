"""Tests for ``scripts/measure_prefix_tokens.py``.

The ``scripts/`` directory is on ``sys.path`` via the ``pythonpath`` key
under ``[tool.pytest.ini_options]`` in ``pyproject.toml``.

The measurer is split into pure functions (``measure_target``, ``measure``,
``render_table``, ``render_json``, ``_share``, ``_display_path``) and an I/O
seam (``make_api_counter`` -> the Anthropic SDK, ``main``). The pure
functions are exercised with injected counters; the SDK seam is covered by
injecting a fake ``anthropic`` module into ``sys.modules`` so no test
touches the network or requires the real dependency.

Refs the cache-read reduction issue.
"""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import measure_prefix_tokens as mpt
import pytest

pytestmark = pytest.mark.shard_preflight


# ---------------------------------------------------------------------------
# target construction
# ---------------------------------------------------------------------------


class TestTargets:
    def test_repo_targets_are_rooted(self, tmp_path: Path) -> None:
        targets = mpt.repo_targets(tmp_path)
        labels = [t.label for t in targets]
        assert "CLAUDE.md (Claude prefix)" in labels
        assert targets[0].path == tmp_path / "CLAUDE.md"
        # The APM source path is rooted under the given repo root.
        assert any(
            t.path == tmp_path / ".apm/instructions/master.instructions.md"
            for t in targets
        )

    def test_extra_targets_label_and_path(self) -> None:
        targets = mpt.extra_targets(["/x/SKILL.md"])
        assert targets == [mpt.Target("extra: /x/SKILL.md", Path("/x/SKILL.md"))]

    def test_extra_targets_empty(self) -> None:
        assert mpt.extra_targets([]) == []


# ---------------------------------------------------------------------------
# measure_target / measure
# ---------------------------------------------------------------------------


class TestMeasureTarget:
    def test_success_counts_tokens_and_bytes(self, tmp_path: Path) -> None:
        f = tmp_path / "a.md"
        f.write_text("hello", encoding="utf-8")
        m = mpt.measure_target(mpt.Target("A", f), lambda _t: 42)
        assert m.byte_size == 5
        assert m.tokens == 42
        assert m.error is None

    def test_bytes_count_utf8_not_chars(self, tmp_path: Path) -> None:
        f = tmp_path / "u.md"
        f.write_text("é", encoding="utf-8")  # 1 char, 2 UTF-8 bytes
        m = mpt.measure_target(mpt.Target("U", f), lambda _t: 1)
        assert m.byte_size == 2

    def test_no_counter_marks_unavailable(self, tmp_path: Path) -> None:
        f = tmp_path / "a.md"
        f.write_text("hi", encoding="utf-8")
        m = mpt.measure_target(mpt.Target("A", f), None)
        assert m.byte_size == 2
        assert m.tokens is None
        assert m.error == "no API access"

    def test_missing_file_degrades_row(self, tmp_path: Path) -> None:
        m = mpt.measure_target(mpt.Target("Gone", tmp_path / "nope.md"), lambda _t: 1)
        assert m.byte_size is None
        assert m.tokens is None
        assert m.error is not None
        assert m.error.startswith("unreadable:")

    def test_counter_failure_captured_not_raised(self, tmp_path: Path) -> None:
        f = tmp_path / "a.md"
        f.write_text("hi", encoding="utf-8")

        def boom(_t: str) -> int:
            raise RuntimeError("api down")

        m = mpt.measure_target(mpt.Target("A", f), boom)
        assert m.byte_size == 2
        assert m.tokens is None
        assert m.error == "count failed: api down"

    def test_measure_runs_all_targets_in_order(self, tmp_path: Path) -> None:
        (tmp_path / "a.md").write_text("aa", encoding="utf-8")
        (tmp_path / "b.md").write_text("bbbb", encoding="utf-8")
        targets = [
            mpt.Target("A", tmp_path / "a.md"),
            mpt.Target("B", tmp_path / "b.md"),
        ]
        results = mpt.measure(targets, lambda t: len(t))
        assert [m.tokens for m in results] == [2, 4]


# ---------------------------------------------------------------------------
# _share
# ---------------------------------------------------------------------------


class TestShare:
    def test_normal(self) -> None:
        assert mpt._share(25, 100) == "25.0%"

    def test_none_tokens(self) -> None:
        assert mpt._share(None, 100) == "-"

    def test_zero_total(self) -> None:
        assert mpt._share(10, 0) == "-"


# ---------------------------------------------------------------------------
# _display_path
# ---------------------------------------------------------------------------


class TestDisplayPath:
    def test_in_repo_is_relative(self) -> None:
        p = mpt.REPO_ROOT / "scripts" / "measure_prefix_tokens.py"
        assert mpt._display_path(p) == "scripts/measure_prefix_tokens.py"

    def test_out_of_repo_is_absolute(self, tmp_path: Path) -> None:
        # tmp_path is outside the repo root -> returned unchanged.
        out = tmp_path / "x.md"
        assert mpt._display_path(out) == str(out)


# ---------------------------------------------------------------------------
# render_table
# ---------------------------------------------------------------------------


def _measurements() -> list[mpt.Measurement]:
    return [
        mpt.Measurement("CLAUDE.md", Path("CLAUDE.md"), 12385, 3000, None),
        mpt.Measurement("AGENTS.md", Path("AGENTS.md"), 12421, 1000, None),
        mpt.Measurement("Gone", Path("nope.md"), None, None, "unreadable: x"),
    ]


class TestRenderTable:
    def test_contains_model_and_total(self) -> None:
        out = mpt.render_table(_measurements(), "claude-opus-4-8")
        assert "model: claude-opus-4-8" in out
        # measured total = 3000 + 1000 = 4000
        assert "**4,000**" in out

    def test_share_computed_against_measured_total(self) -> None:
        out = mpt.render_table(_measurements(), "claude-opus-4-8")
        assert "75.0%" in out  # 3000 / 4000
        assert "25.0%" in out  # 1000 / 4000

    def test_error_rows_listed_in_notes(self) -> None:
        out = mpt.render_table(_measurements(), "claude-opus-4-8")
        assert "Notes:" in out
        assert "Gone: unreadable: x" in out

    def test_harness_owned_section_present(self) -> None:
        out = mpt.render_table(_measurements(), "claude-opus-4-8")
        assert "NOT measurable from repo (harness-owned prefix):" in out
        for name in mpt._HARNESS_OWNED:
            assert name in out

    def test_all_unavailable_total_is_unavailable(self) -> None:
        ms = [mpt.Measurement("X", Path("x"), 10, None, "no API access")]
        out = mpt.render_table(ms, "claude-opus-4-8")
        assert f"| **Measured total** |  |  | **{mpt._UNAVAILABLE}** | |" in out
        # No measured tokens -> no Notes-free run; the note still lists the row.
        assert "X: no API access" in out

    def test_output_is_ascii(self) -> None:
        assert mpt.render_table(_measurements(), "claude-opus-4-8").isascii()


# ---------------------------------------------------------------------------
# render_json
# ---------------------------------------------------------------------------


class TestRenderJson:
    def test_shape(self) -> None:
        out = mpt.render_json(_measurements(), "claude-opus-4-8")
        data = json.loads(out)
        assert data["model"] == "claude-opus-4-8"
        assert data["measured_total_tokens"] == 4000
        assert len(data["components"]) == 3
        assert data["components"][0]["label"] == "CLAUDE.md"
        assert data["harness_owned_not_measurable"] == list(mpt._HARNESS_OWNED)

    def test_null_tokens_serialized(self) -> None:
        data = json.loads(mpt.render_json(_measurements(), "m"))
        assert data["components"][2]["tokens"] is None
        assert data["components"][2]["error"] == "unreadable: x"


# ---------------------------------------------------------------------------
# make_api_counter (SDK seam; fake anthropic module, no network)
# ---------------------------------------------------------------------------


class _FakeResp:
    def __init__(self, n: int) -> None:
        self.input_tokens = n


class _FakeMessages:
    def __init__(self, recorder: dict[str, object]) -> None:
        self._recorder = recorder

    def count_tokens(self, *, model: str, messages: list[dict[str, str]]) -> _FakeResp:
        self._recorder["model"] = model
        self._recorder["messages"] = messages
        return _FakeResp(len(messages[0]["content"]))


class _FakeClient:
    def __init__(self, recorder: dict[str, object]) -> None:
        self.messages = _FakeMessages(recorder)


def _install_fake_anthropic(
    monkeypatch: pytest.MonkeyPatch, recorder: dict[str, object]
) -> None:
    module = types.ModuleType("anthropic")
    module.Anthropic = lambda: _FakeClient(recorder)  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "anthropic", module)


class TestMakeApiCounter:
    def test_missing_sdk_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Setting the entry to None makes `import anthropic` raise ImportError.
        monkeypatch.setitem(sys.modules, "anthropic", None)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy")
        with pytest.raises(RuntimeError, match="not importable"):
            mpt.make_api_counter("claude-opus-4-8")

    def test_no_credential_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _install_fake_anthropic(monkeypatch, {})
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
        with pytest.raises(RuntimeError, match="no Anthropic credential"):
            mpt.make_api_counter("claude-opus-4-8")

    def test_success_counter_calls_endpoint(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        recorder: dict[str, object] = {}
        _install_fake_anthropic(monkeypatch, recorder)
        monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy")
        counter = mpt.make_api_counter("claude-opus-4-8")
        assert counter("hello") == 5
        assert recorder["model"] == "claude-opus-4-8"

    def test_auth_token_credential_accepted(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _install_fake_anthropic(monkeypatch, {})
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "dummy")
        # Should not raise; AUTH_TOKEN alone is a valid credential.
        assert mpt.make_api_counter("claude-opus-4-8")("ab") == 2


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


class TestMain:
    def test_token_path_exits_zero(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
    ) -> None:
        monkeypatch.setattr(mpt, "make_api_counter", lambda _model: (lambda t: len(t)))
        rc = mpt.main(["--repo-root", str(tmp_path)])
        assert rc == 0
        out = capsys.readouterr().out
        assert "Fixed-prefix token measurement" in out

    def test_no_api_exits_two_and_warns(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
    ) -> None:
        def _raise(_model: str) -> mpt.Counter:
            raise RuntimeError("no creds")

        monkeypatch.setattr(mpt, "make_api_counter", _raise)
        rc = mpt.main(["--repo-root", str(tmp_path)])
        assert rc == 2
        captured = capsys.readouterr()
        assert "::warning::token counts unavailable: no creds" in captured.err
        # Byte table still printed even without tokens.
        assert "Fixed-prefix token measurement" in captured.out

    def test_json_flag(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
    ) -> None:
        monkeypatch.setattr(mpt, "make_api_counter", lambda _model: (lambda t: len(t)))
        rc = mpt.main(["--json", "--repo-root", str(tmp_path)])
        assert rc == 0
        data = json.loads(capsys.readouterr().out)
        assert data["model"] == mpt.MODEL_DEFAULT

    def test_extra_path_measured(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
    ) -> None:
        skill = tmp_path / "SKILL.md"
        skill.write_text("body", encoding="utf-8")
        monkeypatch.setattr(mpt, "make_api_counter", lambda _model: (lambda t: len(t)))
        rc = mpt.main(["--json", "--repo-root", str(tmp_path), str(skill)])
        assert rc == 0
        data = json.loads(capsys.readouterr().out)
        labels = [c["label"] for c in data["components"]]
        assert f"extra: {skill}" in labels
