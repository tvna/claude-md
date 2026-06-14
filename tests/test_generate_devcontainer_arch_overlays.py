from __future__ import annotations

import json
from pathlib import Path

import generate_devcontainer_arch_overlays as overlays
import pytest

pytestmark = pytest.mark.shard_ci_ops

SHA = "a" * 40


def _base_config(agent: str) -> dict:
    return {
        "name": f"claude-md {agent.capitalize()}",
        "image": f"ghcr.io/tvna/claude-md-devcontainer-{agent}:{SHA}",
        "initializeCommand": (
            "bash .devcontainer/scripts/check-gh-config-permissions.sh ${HOME}/.config/gh "
            f"&& bash .devcontainer/scripts/ensure-agent-image.sh {agent}"
        ),
        "remoteUser": agent,
        "runArgs": ["--cap-add=NET_ADMIN", "--cap-add=BPF"],
    }


def _write_bases(root: Path) -> None:
    for agent in overlays.AGENTS:
        path = overlays.base_path(root, agent)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(_base_config(agent), indent=2) + "\n", encoding="utf-8")


def test_generate_writes_every_agent_arch_overlay(tmp_path: Path) -> None:
    _write_bases(tmp_path)

    changed = overlays.generate(tmp_path)

    assert len(changed) == len(overlays.AGENTS) * len(overlays.ARCHES)
    for agent in overlays.AGENTS:
        for arch in overlays.ARCHES:
            assert overlays.overlay_path(tmp_path, agent, arch).is_file()
    assert overlays.verify(tmp_path) == []


def test_generate_is_idempotent(tmp_path: Path) -> None:
    _write_bases(tmp_path)
    overlays.generate(tmp_path)

    assert overlays.generate(tmp_path) == []


def test_render_overlay_merges_platform_name_and_init() -> None:
    base = _base_config("claude")

    overlay = overlays.render_overlay(base, "claude", "amd64")

    # --platform is prepended, base runArgs preserved in order.
    assert overlay["runArgs"] == ["--platform=linux/amd64", "--cap-add=NET_ADMIN", "--cap-add=BPF"]
    assert overlay["name"] == "claude-md Claude (linux/amd64)"
    assert "ensure-agent-image.sh claude --platform linux/amd64" in overlay["initializeCommand"]
    # The marker is the first key so the generated nature is obvious.
    assert next(iter(overlay)) == "//"


def test_render_overlay_propagates_base_image_sha_verbatim() -> None:
    base = _base_config("codex")

    overlay = overlays.render_overlay(base, "codex", "arm64")

    assert overlay["image"] == base["image"]
    assert SHA in overlay["image"]


def test_render_overlay_rejects_ambiguous_init_token() -> None:
    base = _base_config("claude")
    # Two occurrences of the agent token make the platform injection ambiguous.
    base["initializeCommand"] = "ensure-agent-image.sh claude && ensure-agent-image.sh claude"

    with pytest.raises(ValueError, match="exactly one"):
        overlays.render_overlay(base, "claude", "amd64")


def test_verify_flags_missing_overlay(tmp_path: Path) -> None:
    _write_bases(tmp_path)
    overlays.generate(tmp_path)
    overlays.overlay_path(tmp_path, "claude", "amd64").unlink()

    errors = overlays.verify(tmp_path)

    assert any("missing overlay" in err for err in errors)


def test_verify_flags_hand_edited_overlay(tmp_path: Path) -> None:
    _write_bases(tmp_path)
    overlays.generate(tmp_path)
    drifted = overlays.overlay_path(tmp_path, "codex", "arm64")
    drifted.write_text(drifted.read_text(encoding="utf-8") + "\n# tampered\n", encoding="utf-8")

    errors = overlays.verify(tmp_path)

    assert any("out of sync" in err for err in errors)


def test_cli_generate_then_verify_roundtrip(tmp_path: Path) -> None:
    _write_bases(tmp_path)

    assert overlays.main(["generate", "--repo-root", str(tmp_path)]) == 0
    assert overlays.main(["verify", "--repo-root", str(tmp_path)]) == 0


def test_cli_verify_fails_on_drift(tmp_path: Path) -> None:
    _write_bases(tmp_path)
    overlays.main(["generate", "--repo-root", str(tmp_path)])
    overlays.overlay_path(tmp_path, "claude", "arm64").unlink()

    assert overlays.main(["verify", "--repo-root", str(tmp_path)]) == 1


def test_committed_overlays_match_their_bases() -> None:
    # The real repository's overlays must stay in sync with their base configs;
    # this mirrors the preflight drift gate so a stale commit fails locally too.
    assert overlays.verify(Path()) == []


def test_codex_poststart_applies_egress_allowlist_without_nix_shell() -> None:
    config = json.loads(overlays.base_path(Path(), "codex").read_text(encoding="utf-8"))

    post_start = config["postStartCommand"]

    assert "nix develop .#network" not in post_start
    assert "bash .devcontainer/scripts/apply-egress-allowlist.sh" in post_start
