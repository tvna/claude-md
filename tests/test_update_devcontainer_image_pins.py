from __future__ import annotations

import json
from pathlib import Path

import pytest
import update_devcontainer_image_pins as pins

pytestmark = pytest.mark.shard_ci_ops

OLD_SHA = "0" * 40
NEW_SHA = "1" * 40


def _write_repo(root: Path) -> None:
    for agent in pins.AGENTS:
        config_dir = root / ".devcontainer" / agent
        config_dir.mkdir(parents=True, exist_ok=True)
        config = {
            "name": f"claude-md {agent}",
            "image": f"{pins.IMAGE_PREFIX}-{agent}:{OLD_SHA}",
            "remoteUser": agent,
        }
        (config_dir / "devcontainer.json").write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")

    docs_dir = root / "docs" / "runbooks"
    docs_dir.mkdir(parents=True, exist_ok=True)
    (docs_dir / "devcontainers.md").write_text(
        "\n".join(
            [
                "Local devcontainers use immutable commit-SHA image tags. The currently",
                f"pinned images were published from `{OLD_SHA}`:",
                "",
                "| Agent | Image |",
                "|---|---|",
                f"| Claude | `{pins.IMAGE_PREFIX}-claude:{OLD_SHA}` |",
                f"| Codex | `{pins.IMAGE_PREFIX}-codex:{OLD_SHA}` |",
                "",
            ]
        ),
        encoding="utf-8",
    )


def test_update_pins_updates_agent_configs_and_runbook(tmp_path: Path) -> None:
    _write_repo(tmp_path)

    assert pins.update_pins(tmp_path, NEW_SHA) is True

    for agent in pins.AGENTS:
        config = json.loads((tmp_path / ".devcontainer" / agent / "devcontainer.json").read_text(encoding="utf-8"))
        assert config["image"] == f"{pins.IMAGE_PREFIX}-{agent}:{NEW_SHA}"

    runbook = (tmp_path / "docs" / "runbooks" / "devcontainers.md").read_text(encoding="utf-8")
    assert OLD_SHA not in runbook
    assert f"published from `{NEW_SHA}`" in runbook
    assert f"{pins.IMAGE_PREFIX}-claude:{NEW_SHA}" in runbook
    assert f"{pins.IMAGE_PREFIX}-codex:{NEW_SHA}" in runbook


def test_update_pins_is_idempotent(tmp_path: Path) -> None:
    _write_repo(tmp_path)
    assert pins.update_pins(tmp_path, OLD_SHA) is False


def test_update_pins_rejects_invalid_sha(tmp_path: Path) -> None:
    _write_repo(tmp_path)
    with pytest.raises(ValueError, match="40-character lowercase git SHA"):
        pins.update_pins(tmp_path, "not-a-sha")
