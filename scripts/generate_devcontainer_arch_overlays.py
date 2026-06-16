#!/usr/bin/env python3
"""Generate per-architecture devcontainer entrypoint overlays from the base configs.

The local entrypoints ``.devcontainer/{claude,codex}/devcontainer.json`` pin a
single commit-SHA image tag that is a multi-platform manifest, so ``podman pull``
auto-resolves the host CPU architecture. That auto-resolving default stays the
everyday path. This module adds *opt-in* per-arch overlays so a developer can:

1. explicitly select an architecture (for example run the ``linux/amd64`` image
   under emulation on an Apple Silicon host for cross-arch verification), and
2. see those choices in the VS Code "Reopen in Container" / "Switch Container"
   picker, which lists every ``.devcontainer/<name>/devcontainer.json`` subfolder.

Each overlay ``.devcontainer/<agent>-<arch>/devcontainer.json`` is *generated*
from the base by injecting ``runArgs: ["--platform=linux/<arch>", ...]``,
suffixing ``name``, and pointing ``initializeCommand`` at the platform-aware
image check. The base config image SHA is the single source of truth: the pin
automation (``scripts/update_devcontainer_image_pins.py``) regenerates the
overlays after updating the bases, and this module's ``verify`` subcommand is a
``preflight_all.py`` drift gate so a hand-edited or stale overlay fails CI.

CLI::

    python3 scripts/generate_devcontainer_arch_overlays.py generate  # write overlays
    python3 scripts/generate_devcontainer_arch_overlays.py verify     # exit 1 on drift

Contract:
- Inputs: the ``generate`` or ``verify`` subcommand; ``--repo-root`` (default
  ``.``); the base ``.devcontainer/<agent>/devcontainer.json`` files.
- Outputs (generate): writes/refreshes each overlay only when its content
  changes; prints the changed paths. Outputs (verify): ``::error::`` annotations
  on stderr for each missing or drifted overlay; exit 0 when all overlays match
  their regenerated form, exit 1 otherwise.
- Failure policy: fails loud per CLAUDE.md section 4 (a base missing the
  expected ``initializeCommand`` agent token, or a drifted/missing overlay,
  exits non-zero).

Tested by ``tests/test_generate_devcontainer_arch_overlays.py``. Refs #696, #1296.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

AGENTS: tuple[str, ...] = ("claude", "codex")
ARCHES: tuple[str, ...] = ("amd64", "arm64")

_MARKER_TEMPLATE = (
    "GENERATED FILE -- do not edit. Source: "
    ".devcontainer/{agent}/devcontainer.json. Regenerate: "
    "python3 scripts/generate_devcontainer_arch_overlays.py generate. This "
    "overlay pins --platform=linux/{arch} for explicit cross-arch selection; "
    "see docs/runbooks/devcontainers.md."
)


def base_path(repo_root: Path, agent: str) -> Path:
    return repo_root / ".devcontainer" / agent / "devcontainer.json"


def overlay_path(repo_root: Path, agent: str, arch: str) -> Path:
    return repo_root / ".devcontainer" / f"{agent}-{arch}" / "devcontainer.json"


def render_overlay(base: dict[str, Any], agent: str, arch: str) -> dict[str, Any]:
    """Return the overlay config derived from *base* for *agent*/*arch*.

    The base image SHA and every other field are copied verbatim; only ``name``,
    ``runArgs``, and ``initializeCommand`` are specialised. The ``"//"`` marker
    is inserted first so the generated nature is obvious at the top of the file.
    """
    overlay: dict[str, Any] = {"//": _MARKER_TEMPLATE.format(agent=agent, arch=arch)}
    overlay.update(base)

    name = base.get("name")
    if isinstance(name, str):
        overlay["name"] = f"{name} (linux/{arch})"

    platform_arg = f"--platform=linux/{arch}"
    run_args = base.get("runArgs", [])
    if not isinstance(run_args, list):
        raise ValueError(f"{agent} base runArgs must be a list, got {type(run_args).__name__}")
    overlay["runArgs"] = [platform_arg, *run_args]

    init = base.get("initializeCommand")
    if isinstance(init, str):
        token = f"ensure-agent-image.sh {agent}"
        count = init.count(token)
        if count != 1:
            raise ValueError(
                f"{agent} base initializeCommand must contain exactly one "
                f"'{token}' token, found {count}"
            )
        overlay["initializeCommand"] = init.replace(token, f"{token} --platform linux/{arch}")

    return overlay


def render_overlay_text(base: dict[str, Any], agent: str, arch: str) -> str:
    return json.dumps(render_overlay(base, agent, arch), indent=2) + "\n"


def _load_base(repo_root: Path, agent: str) -> dict[str, Any]:
    path = base_path(repo_root, agent)
    return json.loads(path.read_text(encoding="utf-8"))


def generate(repo_root: Path) -> list[str]:
    """Write each overlay from its base, returning the paths that changed."""
    changed: list[str] = []
    for agent in AGENTS:
        base = _load_base(repo_root, agent)
        for arch in ARCHES:
            path = overlay_path(repo_root, agent, arch)
            expected = render_overlay_text(base, agent, arch)
            current = path.read_text(encoding="utf-8") if path.is_file() else None
            if current == expected:
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(expected, encoding="utf-8")
            changed.append(str(path.relative_to(repo_root)))
    return changed


def verify(repo_root: Path) -> list[str]:
    """Return ``::error::`` strings for each missing or drifted overlay."""
    errors: list[str] = []
    for agent in AGENTS:
        base_file = base_path(repo_root, agent)
        if not base_file.is_file():
            errors.append(
                f"::error::base devcontainer config not found at {base_file}; "
                f"cannot verify the {agent} per-arch overlays."
            )
            continue
        base = json.loads(base_file.read_text(encoding="utf-8"))
        for arch in ARCHES:
            path = overlay_path(repo_root, agent, arch)
            expected = render_overlay_text(base, agent, arch)
            if not path.is_file():
                errors.append(
                    f"::error::missing overlay {path}. Regenerate with "
                    f"'python3 scripts/generate_devcontainer_arch_overlays.py generate'."
                )
                continue
            if path.read_text(encoding="utf-8") != expected:
                errors.append(
                    f"::error::overlay {path} is out of sync with "
                    f"{base_file}. Do not hand-edit overlays; regenerate with "
                    f"'python3 scripts/generate_devcontainer_arch_overlays.py generate'."
                )
    return errors


def _cmd_generate(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root).resolve()
    changed = generate(repo_root)
    if changed:
        for path in changed:
            print(f"wrote {path}")
    else:
        print("devcontainer arch overlays already up to date")
    return 0


def _cmd_verify(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root).resolve()
    errors = verify(repo_root)
    for err in errors:
        print(err, file=sys.stderr)
    if errors:
        print(
            f"FAIL: {len(errors)} devcontainer arch overlay(s) missing or drifted.",
            file=sys.stderr,
        )
        return 1
    print("OK: every devcontainer arch overlay matches its base.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_generate = sub.add_parser("generate", help="Write per-arch overlays from the base configs.")
    p_generate.add_argument("--repo-root", default=".")
    p_generate.set_defaults(func=_cmd_generate)

    p_verify = sub.add_parser("verify", help="Fail when an overlay is missing or drifted.")
    p_verify.add_argument("--repo-root", default=".")
    p_verify.set_defaults(func=_cmd_verify)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
