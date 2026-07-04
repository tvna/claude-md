"""Tests for scripts/_trusted_bots.py fallback paths.

Refs #859.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import _trusted_bots as tb
import pytest

pytestmark = pytest.mark.shard_policy


def test_load_falls_back_to_defaults_on_os_error(capsys: pytest.CaptureFixture[str]) -> None:
    with patch.object(Path, "read_text", side_effect=OSError("permission denied")):
        general, non_ascii, review_marker = tb._load()

    assert "dependabot[bot]" in general
    assert "codecov[bot]" in non_ascii
    assert "chatgpt-codex-connector[bot]" in review_marker
    assert "permission denied" in capsys.readouterr().err


def test_load_falls_back_to_defaults_on_toml_parse_error(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    with patch.object(Path, "read_text", return_value="[[invalid toml"):
        general, non_ascii, review_marker = tb._load()

    assert "dependabot[bot]" in general
    assert "codecov[bot]" in non_ascii
    assert "chatgpt-codex-connector[bot]" in review_marker
    assert "cannot parse" in capsys.readouterr().err
