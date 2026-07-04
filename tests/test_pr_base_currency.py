"""Tests for the ``upsert-files`` base-currency guard (scripts/_pr_base_currency.py).

The guard blocks committing a file whose local base blob differs from the real
remote base, the #2311 unintended-revert class. These exercise the pure
comparison with injected fakes (no git, no network). Refs #2315.
"""

from __future__ import annotations

import json
from typing import Any

import _pr_base_currency as bc
import pytest

pytestmark = pytest.mark.shard_ci_ops


class _FakeContentsApi:
    """Stand-in for ``apply_call`` returning a canned contents-API blob sha per path."""

    def __init__(self, shas: dict[str, str]) -> None:
        # Map path -> remote blob sha; a path absent from the map is a 404.
        self._shas = shas

    def __call__(self, *, method: str, url: str, payload: Any, token: str) -> tuple[int, str]:
        # URL shape: .../contents/<path>?ref=<base>
        path = url.split("/contents/", 1)[1].split("?ref=", 1)[0]
        if path in self._shas:
            return 200, json.dumps({"sha": self._shas[path], "encoding": "base64", "content": ""})
        return 404, "not found"


class TestVerifyBaseCurrency:
    def test_current_base_passes(self) -> None:
        bc.verify_base_currency(
            repo="owner/repo",
            base="main",
            additions=[("scripts/x.py", b"body")],
            deletions=[],
            token="tok",
            apply_call=_FakeContentsApi({"scripts/x.py": "sha-current"}),
            base_resolvable=lambda base: True,
            local_blob_sha=lambda base, path: "sha-current",
        )

    def test_stale_base_raises_and_names_path(self) -> None:
        with pytest.raises(RuntimeError, match=r"stale for: .*dependabot\.yml"):
            bc.verify_base_currency(
                repo="owner/repo",
                base="main",
                additions=[(".github/dependabot.yml", b"body")],
                deletions=[],
                token="tok",
                apply_call=_FakeContentsApi({".github/dependabot.yml": "sha-remote"}),
                base_resolvable=lambda base: True,
                local_blob_sha=lambda base, path: "sha-local-stale",
            )

    def test_new_file_absent_both_sides_passes(self) -> None:
        # A genuinely new file: absent in local base (None) and remote base (404).
        bc.verify_base_currency(
            repo="owner/repo",
            base="main",
            additions=[("scripts/new.py", b"body")],
            deletions=[],
            token="tok",
            apply_call=_FakeContentsApi({}),
            base_resolvable=lambda base: True,
            local_blob_sha=lambda base, path: None,
        )

    def test_remote_present_local_absent_raises(self) -> None:
        # Local base lacks a file that exists on the remote base -> stale.
        with pytest.raises(RuntimeError, match="stale"):
            bc.verify_base_currency(
                repo="owner/repo",
                base="main",
                additions=[("scripts/x.py", b"body")],
                deletions=[],
                token="tok",
                apply_call=_FakeContentsApi({"scripts/x.py": "sha-remote"}),
                base_resolvable=lambda base: True,
                local_blob_sha=lambda base, path: None,
            )

    def test_unresolvable_base_skips_without_network(self) -> None:
        def boom(**kw: Any) -> tuple[int, str]:
            raise AssertionError("must not call the API when base is unresolvable")

        bc.verify_base_currency(
            repo="owner/repo",
            base="main",
            additions=[("scripts/x.py", b"body")],
            deletions=[],
            token="tok",
            apply_call=boom,
            base_resolvable=lambda base: False,
            local_blob_sha=lambda base, path: "whatever",
        )

    def test_deletion_path_is_checked(self) -> None:
        with pytest.raises(RuntimeError, match=r"stale for: .*gone\.py"):
            bc.verify_base_currency(
                repo="owner/repo",
                base="main",
                additions=[],
                deletions=["scripts/gone.py"],
                token="tok",
                apply_call=_FakeContentsApi({"scripts/gone.py": "sha-remote"}),
                base_resolvable=lambda base: True,
                local_blob_sha=lambda base, path: "sha-local-stale",
            )


class TestGetFileBlobSha:
    def test_returns_sha_on_200(self) -> None:
        api = _FakeContentsApi({"scripts/x.py": "abc123"})
        assert bc._get_file_blob_sha(repo="o/r", path="scripts/x.py", ref="main", token="t", apply_call=api) == "abc123"

    def test_returns_none_on_404(self) -> None:
        api = _FakeContentsApi({})
        assert bc._get_file_blob_sha(repo="o/r", path="scripts/x.py", ref="main", token="t", apply_call=api) is None

    def test_raises_on_other_error(self) -> None:
        def err(**kw: Any) -> tuple[int, str]:
            return 500, "boom"

        with pytest.raises(RuntimeError, match="HTTP 500"):
            bc._get_file_blob_sha(repo="o/r", path="scripts/x.py", ref="main", token="t", apply_call=err)
