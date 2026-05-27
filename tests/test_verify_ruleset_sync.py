"""Tests for ``scripts/verify_ruleset_sync.py``."""

from __future__ import annotations

import base64
import io
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import verify_ruleset_sync as vrs

pytestmark = pytest.mark.shard_ci_ops
# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

SOT_MAIN: dict[str, Any] = {
    "name": "main-protection",
    "rules": [
        {"type": "deletion"},
        {
            "type": "required_status_checks",
            "parameters": {
                "strict_required_status_checks_policy": True,
                "required_status_checks": [
                    {"context": "Verify issue link / gate"},
                    {"context": "Verify title policy / gate"},
                    {"context": "Verify ruleset sync / gate"},
                ],
            },
        },
    ],
}


def _b64(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


class _Response:
    def __init__(self, payload: object, status: int = 200) -> None:
        self.payload = json.dumps(payload).encode("utf-8")
        self.status = status

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self.payload


def _scripted_opener(*responses: object):
    """Return an opener that yields each response in order."""
    queue = list(responses)

    def opener(_request: urllib.request.Request) -> _Response:
        if not queue:
            raise AssertionError("opener called more times than scripted responses")
        return _Response(queue.pop(0))

    return opener


# ---------------------------------------------------------------------------
# Pure functions
# ---------------------------------------------------------------------------

class TestExtractRequiredContexts:
    def test_typical_three_contexts(self) -> None:
        assert vrs.extract_required_contexts(SOT_MAIN) == {
            "Verify issue link / gate",
            "Verify title policy / gate",
            "Verify ruleset sync / gate",
        }

    def test_no_required_status_checks_rule(self) -> None:
        assert vrs.extract_required_contexts({"rules": [{"type": "deletion"}]}) == set()

    def test_no_rules_key(self) -> None:
        assert vrs.extract_required_contexts({}) == set()

    def test_null_rules(self) -> None:
        assert vrs.extract_required_contexts({"rules": None}) == set()

    def test_rule_without_parameters(self) -> None:
        ruleset = {"rules": [{"type": "required_status_checks"}]}
        assert vrs.extract_required_contexts(ruleset) == set()

    def test_empty_required_status_checks_list(self) -> None:
        ruleset = {
            "rules": [
                {
                    "type": "required_status_checks",
                    "parameters": {"required_status_checks": []},
                }
            ]
        }
        assert vrs.extract_required_contexts(ruleset) == set()

    def test_check_without_context_key_is_ignored(self) -> None:
        ruleset = {
            "rules": [
                {
                    "type": "required_status_checks",
                    "parameters": {
                        "required_status_checks": [
                            {"context": "Verify issue link / gate"},
                            {"integration_id": 15368},
                        ]
                    },
                }
            ]
        }
        assert vrs.extract_required_contexts(ruleset) == {"Verify issue link / gate"}


class TestComputeMissing:
    def test_symmetric(self) -> None:
        assert vrs.compute_missing({"a", "b"}, {"a", "b"}) == set()

    def test_sot_ahead(self) -> None:
        assert vrs.compute_missing({"a", "b", "c"}, {"a"}) == {"b", "c"}

    def test_live_ahead_is_ignored(self) -> None:
        # full drift is owned by ruleset-drift.yml; this gate ignores it.
        assert vrs.compute_missing({"a"}, {"a", "b"}) == set()

    def test_disjoint(self) -> None:
        assert vrs.compute_missing({"a"}, {"b"}) == {"a"}


class TestDecodeBase64Content:
    def test_typical(self) -> None:
        payload = {"encoding": "base64", "content": _b64('{"name": "main-protection"}')}
        assert vrs.decode_base64_content(payload) == '{"name": "main-protection"}'

    def test_handles_embedded_newlines(self) -> None:
        # GitHub wraps base64 every 60 chars.
        raw = _b64("x" * 200)
        wrapped = "\n".join(raw[i : i + 60] for i in range(0, len(raw), 60))
        payload = {"encoding": "base64", "content": wrapped}
        assert vrs.decode_base64_content(payload) == "x" * 200

    def test_unexpected_encoding_raises(self) -> None:
        with pytest.raises(ValueError, match="unexpected encoding"):
            vrs.decode_base64_content({"encoding": "utf-8", "content": "x"})

    def test_missing_content_raises(self) -> None:
        with pytest.raises(ValueError, match="no 'content' string"):
            vrs.decode_base64_content({"encoding": "base64"})


class TestFormatErrorLines:
    def test_sorts_missing_contexts(self) -> None:
        lines = vrs.format_error_lines({"b-ctx", "a-ctx"}, "https://example/docs")
        assert lines[0].endswith("a-ctx")
        assert lines[1].endswith("b-ctx")

    def test_appends_resolution_hint_with_docs_url(self) -> None:
        lines = vrs.format_error_lines({"x"}, "https://example/docs")
        assert "Apply rulesets" in lines[-1]
        assert "https://example/docs" in lines[-1]

    def test_each_line_starts_with_error_annotation(self) -> None:
        lines = vrs.format_error_lines({"x", "y"}, "u")
        for line in lines:
            assert line.startswith("::error::")


# ---------------------------------------------------------------------------
# HTTP boundary
# ---------------------------------------------------------------------------

class TestFetchLiveRulesetByName:
    def test_returns_detail_after_name_match(self) -> None:
        listing = [{"id": 42, "name": "main-protection"}, {"id": 7, "name": "other"}]
        detail = {"id": 42, "name": "main-protection", "rules": []}
        opener = _scripted_opener(listing, detail)

        result = vrs.fetch_live_ruleset_by_name("o/r", "main-protection", "tok", opener=opener)

        assert result == detail

    def test_no_match_raises_with_helpful_message(self) -> None:
        opener = _scripted_opener([{"id": 7, "name": "other"}])

        with pytest.raises(RuntimeError, match="No live ruleset named 'main-protection'"):
            vrs.fetch_live_ruleset_by_name("o/r", "main-protection", "tok", opener=opener)

    def test_multiple_matches_raises(self) -> None:
        opener = _scripted_opener(
            [
                {"id": 42, "name": "main-protection"},
                {"id": 43, "name": "main-protection"},
            ]
        )

        with pytest.raises(RuntimeError, match="Multiple live rulesets"):
            vrs.fetch_live_ruleset_by_name("o/r", "main-protection", "tok", opener=opener)


class TestFetchBaseRefSot:
    def test_returns_decoded_text(self) -> None:
        body = {"encoding": "base64", "content": _b64('{"name": "x"}')}
        opener = _scripted_opener(body)

        text = vrs.fetch_base_ref_sot(
            "o/r", "main", ".github/rulesets/main.json", "tok", opener=opener
        )

        assert text == '{"name": "x"}'


# ---------------------------------------------------------------------------
# Orchestration (verify) + CLI contract
# ---------------------------------------------------------------------------

LIVE_SYMMETRIC: dict[str, Any] = {
    "name": "main-protection",
    "rules": [
        {
            "type": "required_status_checks",
            "parameters": {
                "required_status_checks": [
                    {"context": "Verify issue link / gate"},
                    {"context": "Verify title policy / gate"},
                    {"context": "Verify ruleset sync / gate"},
                ]
            },
        }
    ],
}

LIVE_LAGGING: dict[str, Any] = {
    "name": "main-protection",
    "rules": [
        {
            "type": "required_status_checks",
            "parameters": {
                "required_status_checks": [
                    {"context": "Verify title policy / gate"},
                ]
            },
        }
    ],
}


class TestVerify:
    def test_symmetric_exits_zero(self) -> None:
        out = io.StringIO()
        err = io.StringIO()

        rc = vrs.verify(
            repo="o/r",
            base_ref="main",
            sot_path=".github/rulesets/main.json",
            ruleset_name="main-protection",
            token="tok",
            docs_url="u",
            out_stream=out,
            err_stream=err,
            live_fetcher=lambda r, n, t: LIVE_SYMMETRIC,
            sot_fetcher=lambda r, b, p, t: json.dumps(SOT_MAIN),
        )

        assert rc == 0
        assert "OK" in out.getvalue()
        assert err.getvalue() == ""

    def test_missing_contexts_exits_one_and_lists_each(self) -> None:
        out = io.StringIO()
        err = io.StringIO()

        rc = vrs.verify(
            repo="o/r",
            base_ref="main",
            sot_path=".github/rulesets/main.json",
            ruleset_name="main-protection",
            token="tok",
            docs_url="https://example/docs",
            out_stream=out,
            err_stream=err,
            live_fetcher=lambda r, n, t: LIVE_LAGGING,
            sot_fetcher=lambda r, b, p, t: json.dumps(SOT_MAIN),
        )

        assert rc == 1
        stderr = err.getvalue()
        assert "Verify issue link / gate" in stderr
        assert "Verify ruleset sync / gate" in stderr
        assert "Verify title policy / gate" not in stderr  # already in live
        assert "Apply rulesets" in stderr
        assert "https://example/docs" in stderr

    def test_live_fetcher_error_exits_one(self) -> None:
        out = io.StringIO()
        err = io.StringIO()

        def raise_runtime(_r: str, _n: str, _t: str) -> dict[str, Any]:
            raise RuntimeError("No live ruleset named 'main-protection'")

        rc = vrs.verify(
            repo="o/r",
            base_ref="main",
            sot_path=".github/rulesets/main.json",
            ruleset_name="main-protection",
            token="tok",
            docs_url="u",
            out_stream=out,
            err_stream=err,
            live_fetcher=raise_runtime,
            sot_fetcher=lambda r, b, p, t: json.dumps(SOT_MAIN),
        )

        assert rc == 1
        assert "Failed to fetch live ruleset" in err.getvalue()

    def test_sot_fetcher_error_exits_one(self) -> None:
        out = io.StringIO()
        err = io.StringIO()

        def raise_http(_r: str, _b: str, _p: str, _t: str) -> str:
            raise urllib.error.HTTPError("u", 404, "Not Found", {}, None)  # type: ignore[arg-type]

        rc = vrs.verify(
            repo="o/r",
            base_ref="main",
            sot_path=".github/rulesets/main.json",
            ruleset_name="main-protection",
            token="tok",
            docs_url="u",
            out_stream=out,
            err_stream=err,
            live_fetcher=lambda r, n, t: LIVE_SYMMETRIC,
            sot_fetcher=raise_http,
        )

        assert rc == 1
        assert "Failed to fetch base-ref SoT" in err.getvalue()


class TestMainCli:
    def test_missing_token_exits_one(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.delenv("GH_TOKEN_API", raising=False)

        rc = vrs.main(
            [
                "verify",
                "--repo", "o/r",
                "--base-ref", "main",
                "--sot-path", ".github/rulesets/main.json",
                "--ruleset-name", "main-protection",
            ]
        )

        assert rc == 1
        captured = capsys.readouterr()
        assert "RULESETS_PAT" in captured.err

    def test_verify_requires_repo_and_base_ref(self) -> None:
        with pytest.raises(SystemExit):
            vrs.main(["verify"])

    def test_no_subcommand_exits(self) -> None:
        with pytest.raises(SystemExit):
            vrs.main([])

    def test_verify_calls_orchestrator_with_args(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setenv("GH_TOKEN_API", "tok")
        monkeypatch.setattr(
            vrs, "fetch_live_ruleset_by_name", lambda r, n, t: LIVE_SYMMETRIC
        )
        monkeypatch.setattr(
            vrs, "fetch_base_ref_sot", lambda r, b, p, t: json.dumps(SOT_MAIN)
        )

        rc = vrs.main(
            [
                "verify",
                "--repo", "o/r",
                "--base-ref", "main",
            ]
        )

        assert rc == 0
        captured = capsys.readouterr()
        assert "OK" in captured.out


class TestRepoSotMatchesScript:
    """Guard against accidental SoT/script drift: the live SoT JSON must parse and
    declare the gate's own context (`Verify ruleset sync / gate`) per issue #120."""

    def test_main_sot_declares_self_context(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        sot = json.loads((repo_root / ".github" / "rulesets" / "main.json").read_text())

        contexts = vrs.extract_required_contexts(sot)

        assert "Verify ruleset sync / gate" in contexts
