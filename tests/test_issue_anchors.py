"""Tests for ``scripts/issue_anchors.py`` (issue #1640).

Covers the loader validation (fail-loud on every malformed-config shape),
the ``resolve`` / ``substitute`` library surface, the ``get`` / ``render``
CLI, and the live repository config: the anchor table must keep resolving
to the numbers the workflows hardcoded before the #1640 refactor, so the
migration stays behaviour-preserving.
"""

from __future__ import annotations

from pathlib import Path

import issue_anchors
import pytest

pytestmark = pytest.mark.shard_default


VALID_CONFIG = """\
schema_version = 1

[[anchors]]
key = "alpha"
issue = 11
writes = "comment"
consumers = ["scripts/issue_anchors.py"]

[[anchors]]
key = "beta-two"
issue = 22
writes = "commit-trailer"
consumers = ["a.md", "b.md"]
"""


@pytest.fixture
def config(tmp_path: Path) -> Path:
    path = tmp_path / "tracking-issues.toml"
    path.write_text(VALID_CONFIG, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# load_anchors / resolve
# ---------------------------------------------------------------------------


def test_load_anchors_returns_key_to_issue_map(config: Path) -> None:
    assert issue_anchors.load_anchors(config) == {"alpha": 11, "beta-two": 22}


def test_resolve_returns_issue_number(config: Path) -> None:
    assert issue_anchors.resolve("beta-two", config_path=config) == 22


def test_resolve_unknown_key_fails_loud(config: Path) -> None:
    with pytest.raises(ValueError, match="unknown anchor key 'nope'"):
        issue_anchors.resolve("nope", config_path=config)


def test_load_anchors_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(OSError):
        issue_anchors.load_anchors(tmp_path / "absent.toml")


@pytest.mark.parametrize(
    ("snippet", "match"),
    [
        ("schema_version = 2\n[[anchors]]\nkey='a'\nissue=1\nconsumers=['x']", "schema_version"),
        ("schema_version = 1\n", "non-empty"),
        ("schema_version = 1\nanchors = [1]\n", "not a table"),
        ("schema_version = 1\n[[anchors]]\nkey='Bad Key'\nissue=1\nconsumers=['x']", "anchor key"),
        ("schema_version = 1\n[[anchors]]\nissue=1\nconsumers=['x']", "anchor key"),
        ("schema_version = 1\n[[anchors]]\nkey='a'\nissue=0\nconsumers=['x']", "positive integer"),
        ("schema_version = 1\n[[anchors]]\nkey='a'\nissue=true\nconsumers=['x']", "positive integer"),
        ("schema_version = 1\n[[anchors]]\nkey='a'\nissue='9'\nconsumers=['x']", "positive integer"),
        ("schema_version = 1\n[[anchors]]\nkey='a'\nissue=1\nconsumers=[]", "consumers"),
        ("schema_version = 1\n[[anchors]]\nkey='a'\nissue=1\nconsumers=[3]", "consumers"),
        ("schema_version = 1\n[[anchors]]\nkey='a'\nissue=1", "consumers"),
        (
            "schema_version = 1\n"
            "[[anchors]]\nkey='a'\nissue=1\nconsumers=['x']\n"
            "[[anchors]]\nkey='a'\nissue=2\nconsumers=['y']",
            "duplicate anchor key",
        ),
    ],
)
def test_load_anchors_rejects_malformed_config(
    tmp_path: Path, snippet: str, match: str
) -> None:
    path = tmp_path / "bad.toml"
    path.write_text(snippet + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match=match):
        issue_anchors.load_anchors(path)


# ---------------------------------------------------------------------------
# substitute
# ---------------------------------------------------------------------------


def test_substitute_replaces_every_token(config: Path) -> None:
    text = "Closes #__ISSUE_ANCHOR:alpha__ and Refs #__ISSUE_ANCHOR:beta-two__."
    assert (
        issue_anchors.substitute(text, config_path=config)
        == "Closes #11 and Refs #22."
    )


def test_substitute_without_tokens_is_identity(config: Path) -> None:
    assert issue_anchors.substitute("plain text", config_path=config) == "plain text"


def test_substitute_unknown_key_fails_loud(config: Path) -> None:
    with pytest.raises(ValueError, match="unknown anchor key 'ghost'"):
        issue_anchors.substitute("__ISSUE_ANCHOR:ghost__", config_path=config)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def test_cli_get_prints_bare_number(
    config: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert issue_anchors.main(["get", "alpha", "--config", str(config)]) == 0
    assert capsys.readouterr().out == "11\n"


def test_cli_get_unknown_key_exits_1(
    config: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert issue_anchors.main(["get", "nope", "--config", str(config)]) == 1
    assert "::error::issue_anchors:" in capsys.readouterr().err


def test_cli_get_missing_config_exits_1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    absent = tmp_path / "absent.toml"
    assert issue_anchors.main(["get", "alpha", "--config", str(absent)]) == 1
    assert "::error::issue_anchors:" in capsys.readouterr().err


def test_cli_get_malformed_toml_exits_1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bad = tmp_path / "bad.toml"
    bad.write_text("schema_version = [unclosed", encoding="utf-8")
    assert issue_anchors.main(["get", "alpha", "--config", str(bad)]) == 1
    assert "::error::issue_anchors:" in capsys.readouterr().err


def test_cli_render_rewrites_file_in_place(config: Path, tmp_path: Path) -> None:
    body = tmp_path / "body.md"
    body.write_text("Closes #__ISSUE_ANCHOR:alpha__\n", encoding="utf-8")
    rc = issue_anchors.main(["render", "--file", str(body), "--config", str(config)])
    assert rc == 0
    assert body.read_text(encoding="utf-8") == "Closes #11\n"


def test_cli_render_unknown_token_exits_1_and_keeps_file(
    config: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    body = tmp_path / "body.md"
    original = "Refs #__ISSUE_ANCHOR:ghost__\n"
    body.write_text(original, encoding="utf-8")
    rc = issue_anchors.main(["render", "--file", str(body), "--config", str(config)])
    assert rc == 1
    assert body.read_text(encoding="utf-8") == original
    assert "::error::issue_anchors:" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# Live repository config: the migration is behaviour-preserving.
# ---------------------------------------------------------------------------


def test_live_config_keeps_pre_refactor_issue_numbers() -> None:
    """Each anchor resolves to the number CI hardcoded before #1640."""
    assert issue_anchors.load_anchors() == {
        "security-tracking": 178,
        "coverage-failure": 197,
        "ci-budget-parent": 1156,
        "generated-docs": 960,
        "agents-regen": 18,
        "devcontainer-pins": 696,
        "flake-pin": 1171,
    }
