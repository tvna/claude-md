"""Tests for ``scripts/_commit_signing.py``.

Refs #2138, #1959. The shared ``is_unsigned`` decides a commit's signature
state from the PRESENCE of a ``gpgsig`` header in its raw object (the
verify-commit false-positive fix: a signed-but-locally-unverifiable commit must
read as signed). Both ``preflight_push_unsigned_commits`` (#2138) and
``preflight_signed_commits`` (#1959) import this one definition.
"""

from __future__ import annotations

import subprocess

import pytest
from _commit_signing import is_unsigned

pytestmark = pytest.mark.shard_preflight

_SIGNED = "1111111111111111111111111111111111111111"
_UNSIGNED = "2222222222222222222222222222222222222222"


def _cp(returncode: int = 0, stdout: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=["git"], returncode=returncode, stdout=stdout, stderr="")


def _runner(stdout: str, returncode: int = 0):
    def run(_args: list[str]) -> subprocess.CompletedProcess[str]:
        return _cp(returncode=returncode, stdout=stdout)

    return run


def test_signed_header_present_reads_signed() -> None:
    body = (
        "tree 0\nauthor a <a@b> 0 +0000\ncommitter a <a@b> 0 +0000\n"
        "gpgsig -----BEGIN SSH SIGNATURE-----\n A\n -----END SSH SIGNATURE-----\n"
        "\nmsg\n"
    )
    assert is_unsigned(_runner(body), _SIGNED) is False


def test_sha256_signature_header_reads_signed() -> None:
    body = "tree 0\ncommitter a <a@b> 0 +0000\ngpgsig-sha256 sig\n\nmsg\n"
    assert is_unsigned(_runner(body), _SIGNED) is False


def test_no_header_reads_unsigned() -> None:
    body = "tree 0\nauthor a <a@b> 0 +0000\ncommitter a <a@b> 0 +0000\n\nmsg\n"
    assert is_unsigned(_runner(body), _UNSIGNED) is True


def test_message_mention_does_not_mask_unsigned() -> None:
    # A commit MESSAGE mentioning gpgsig (after the blank line) must not be read
    # as a signature header.
    body = "tree 0\ncommitter a <a@b> 0 +0000\n\ngpgsig in the message\n"
    assert is_unsigned(_runner(body), _UNSIGNED) is True


def test_nonzero_exit_fails_open() -> None:
    assert is_unsigned(_runner("", returncode=128), _UNSIGNED) is False


def test_subprocess_error_fails_open() -> None:
    def run(_args: list[str]) -> subprocess.CompletedProcess[str]:
        raise OSError("boom")

    assert is_unsigned(run, _UNSIGNED) is False
