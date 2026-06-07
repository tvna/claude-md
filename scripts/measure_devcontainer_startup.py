#!/usr/bin/env python3
"""Measure devcontainer startup phase timings to locate the bottleneck.

Phase 0 of #1322 (Refs #1173): DevContainer startup feels slow, but "caching
is the cause" is a hypothesis, not a measured fact. Before changing the
toolchain-cache shape we need per-phase numbers so the eventual fix rests on
evidence (CLAUDE.md section 2), not intuition.

What it measures, reading the lifecycle straight from a devcontainer config:

* ``pull``           -- time to pull the prebuilt image, plus the image size.
* ``postCreate``     -- time of each ``&&``-split segment of
  ``postCreateCommand`` (``nix develop ... uv sync``, ``install-agent-cli``,
  ``configure-agent-runtime`` ...), run sequentially in one container so each
  segment builds on the previous one exactly as a real start does.
* ``postStart``      -- time of each segment of ``postStartCommand``.

The web remote session cannot run a container runtime, so this is driven from
CI (``.github/workflows/measure-devcontainer-startup.yml``) -- mirroring the
reproducible-in-CI measurement posture of #1173. ``initializeCommand`` is a
host-side podman call and is intentionally NOT replayed here; the
container-side costs above are the portable, environment-independent signal.

Design: pure parsing / splitting / aggregation on top, every container call
funnelled through one injectable :func:`_run`, so :func:`measure` and the
:class:`DockerSession` argv builders are unit-tested with fakes and no runtime.

Contract:
- Inputs: ``--config`` (required, path to a devcontainer.json); ``--runtime``
  (default ``docker``), ``--workspace``, ``--user``, ``--host-dir``, ``--cap``
  (repeatable), ``--no-pull``, ``--output``. No env-var fallbacks.
- Outputs: the JSON report on stdout (and to ``--output`` when given), an ASCII
  markdown summary on stderr (for ``$GITHUB_STEP_SUMMARY``); exit 0 on success.
- Failure policy: fails loud per CLAUDE.md section 4 -- a missing runtime,
  unreadable/malformed config, mutable image tag, or failed pull/start/inspect
  raises and exits non-zero. A per-segment non-zero exit is recorded as data
  (the postStart egress step is best-effort off the real host), not swallowed.

Tested by ``tests/test_measure_devcontainer_startup.py``.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

# A segment of a lifecycle command is split on the top-level ``&&`` chain the
# devcontainer configs use. Quotes are not parsed: the claude/codex configs
# only ever use ``&&`` between top-level commands (the postStart ``if ... fi``
# carries no ``&&``), so a literal split is faithful for them. Document the
# limitation rather than pull in a shell parser for inputs that never need one.
_SEGMENT_SEP = "&&"


@dataclass(frozen=True)
class RunResult:
    """Outcome of one timed container call."""

    returncode: int
    stdout: str
    seconds: float


def _run(
    cmd: list[str],
    *,
    runner: Callable[..., Any] = subprocess.run,
    clock: Callable[[], float] = time.monotonic,
) -> RunResult:
    """Run ``cmd`` (fixed argv, no shell), returning its result and duration.

    ``runner`` and ``clock`` are injectable so the orchestration is testable
    without a real container runtime.
    """
    start = clock()
    proc = runner(cmd, capture_output=True, text=True, check=False)
    elapsed = clock() - start
    return RunResult(returncode=proc.returncode, stdout=proc.stdout, seconds=elapsed)


def resolve_runtime(name: str, *, which: Callable[[str], str | None] = shutil.which) -> str:
    """Return the absolute path of the container runtime, or fail loudly.

    Resolving the full path keeps the subprocess argv off a partial executable
    name (ruff S607) and surfaces a missing runtime as a clear error rather
    than a confusing ``FileNotFoundError`` deep in a call.
    """
    path = which(name)
    if path is None:
        raise ValueError(f"container runtime not found on PATH: {name!r}")
    return path


def load_config(path: Path) -> dict[str, Any]:
    """Parse a devcontainer.json into a dict (loud on missing/malformed)."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ValueError(f"cannot read devcontainer config: {path}") from exc
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"malformed JSON in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"devcontainer config is not an object: {path}")
    return data


def get_image(config: dict[str, Any]) -> str:
    """Return the ``image`` reference, rejecting mutable tags."""
    image = config.get("image")
    if not isinstance(image, str) or not image:
        raise ValueError("devcontainer config has no string 'image'")
    if image.endswith((":main", ":latest")):
        raise ValueError(f"refusing to measure a mutable image tag: {image}")
    return image


def split_segments(command: str | None) -> list[str]:
    """Split a lifecycle command string into top-level ``&&`` segments.

    Returns an empty list for a missing or whitespace-only command. See the
    module note on why a literal split is faithful for these configs.
    """
    if not command:
        return []
    return [segment.strip() for segment in command.split(_SEGMENT_SEP) if segment.strip()]


class Session(Protocol):
    """Container session protocol used by :func:`measure` (see DockerSession)."""

    image: str

    def pull(self) -> RunResult: ...
    def image_size(self) -> int: ...
    def start(self) -> None: ...
    def exec(self, segment: str) -> RunResult: ...
    def close(self) -> None: ...


@dataclass
class DockerSession:
    """A docker/podman-backed session.

    Every call goes through :func:`_run`; the argv builders are pure given the
    injected ``runner``/``clock``, so this class is unit-tested with a fake
    runner and never needs a real daemon in CI's test job.
    """

    runtime: str
    image: str
    workspace: str
    user: str
    host_dir: str
    caps: list[str] = field(default_factory=list)
    runner: Callable[..., Any] = subprocess.run
    clock: Callable[[], float] = time.monotonic
    container_id: str | None = None

    def _run(self, cmd: list[str]) -> RunResult:
        return _run(cmd, runner=self.runner, clock=self.clock)

    def pull(self) -> RunResult:
        return self._run([self.runtime, "pull", self.image])

    def image_size(self) -> int:
        result = self._run([self.runtime, "image", "inspect", "--format", "{{.Size}}", self.image])
        if result.returncode != 0:
            raise ValueError(f"{self.runtime} image inspect failed for {self.image}")
        return int(result.stdout.strip())

    def start(self) -> None:
        cmd = [self.runtime, "run", "-d", "--rm", "-w", self.workspace, "-v", f"{self.host_dir}:{self.workspace}"]
        if self.user:
            cmd += ["--user", self.user]
        for cap in self.caps:
            cmd += ["--cap-add", cap]
        cmd += [self.image, "sleep", "infinity"]
        result = self._run(cmd)
        container_id = result.stdout.strip()
        if result.returncode != 0 or not container_id:
            raise ValueError(f"failed to start container from {self.image}")
        self.container_id = container_id

    def exec(self, segment: str) -> RunResult:
        if self.container_id is None:
            raise ValueError("exec called before start")
        return self._run([self.runtime, "exec", self.container_id, "bash", "-lc", segment])

    def close(self) -> None:
        if self.container_id is not None:
            self._run([self.runtime, "rm", "-f", self.container_id])
            self.container_id = None


def measure(
    session: Session,
    *,
    post_create: list[str],
    post_start: list[str],
    do_pull: bool = True,
) -> dict[str, Any]:
    """Run the measurement against ``session`` and return a JSON-able report.

    A non-zero segment exit is recorded (returncode + time-to-failure), not
    swallowed: in a measurement a failure is data, and the postStart egress
    step is expected to be only best-effort outside the real host (no eBPF).
    The container is always cleaned up.
    """
    report: dict[str, Any] = {"image": session.image, "phases": []}

    if do_pull:
        pull = session.pull()
        report["pull_seconds"] = round(pull.seconds, 3)
        report["pull_returncode"] = pull.returncode

    report["image_size_bytes"] = session.image_size()

    session.start()
    try:
        for phase, segments in (("postCreate", post_create), ("postStart", post_start)):
            for segment in segments:
                result = session.exec(segment)
                report["phases"].append(
                    {
                        "phase": phase,
                        "command": segment,
                        "seconds": round(result.seconds, 3),
                        "returncode": result.returncode,
                    }
                )
    finally:
        session.close()

    report["total_phase_seconds"] = round(sum(p["seconds"] for p in report["phases"]), 3)
    return report


def _human_size(num_bytes: int) -> str:
    """Render a byte count as an ASCII MiB/GiB string for the summary."""
    mib = num_bytes / (1024 * 1024)
    if mib >= 1024:
        return f"{mib / 1024:.2f} GiB"
    return f"{mib:.1f} MiB"


def format_summary(report: dict[str, Any]) -> str:
    """Render an ASCII markdown summary suitable for $GITHUB_STEP_SUMMARY."""
    lines = [
        "# Devcontainer startup measurement",
        "",
        f"- image: `{report['image']}`",
        f"- image size: {_human_size(report['image_size_bytes'])} "
        f"({report['image_size_bytes']} bytes)",
    ]
    if "pull_seconds" in report:
        flag = "" if report["pull_returncode"] == 0 else " (FAILED)"
        lines.append(f"- pull: {report['pull_seconds']:.3f}s{flag}")
    lines += [
        f"- total lifecycle: {report['total_phase_seconds']:.3f}s",
        "",
        "| phase | seconds | exit | command |",
        "| --- | ---: | ---: | --- |",
    ]
    for entry in report["phases"]:
        command = entry["command"]
        if len(command) > 70:
            command = command[:67] + "..."
        lines.append(f"| {entry['phase']} | {entry['seconds']:.3f} | {entry['returncode']} | {command} |")
    return "\n".join(lines) + "\n"


def run(
    argv: list[str] | None,
    *,
    session_factory: Callable[..., Session] = DockerSession,
    which: Callable[[str], str | None] = shutil.which,
) -> int:
    """CLI entry point. ``session_factory``/``which`` are injectable for tests."""
    parser = argparse.ArgumentParser(description="Measure devcontainer startup phase timings.")
    parser.add_argument("--config", required=True, type=Path, help="Path to a devcontainer.json.")
    parser.add_argument("--runtime", default="docker", help="Container runtime (docker or podman).")
    parser.add_argument("--workspace", default="/workspaces/claude-md", help="In-container workspace path.")
    parser.add_argument("--user", default="", help="Container user (empty: image default).")
    parser.add_argument("--host-dir", default=".", help="Host directory bind-mounted to --workspace.")
    parser.add_argument("--cap", action="append", default=[], help="--cap-add value (repeatable).")
    parser.add_argument("--no-pull", action="store_true", help="Skip the pull step (image already local).")
    parser.add_argument("--output", type=Path, help="Write the JSON report to this path.")
    args = parser.parse_args(argv)

    config = load_config(args.config)
    image = get_image(config)
    post_create = split_segments(config.get("postCreateCommand"))
    post_start = split_segments(config.get("postStartCommand"))

    runtime = resolve_runtime(args.runtime, which=which)
    session = session_factory(
        runtime=runtime,
        image=image,
        workspace=args.workspace,
        user=args.user,
        host_dir=str(Path(args.host_dir).resolve()),
        caps=list(args.cap),
    )

    report = measure(session, post_create=post_create, post_start=post_start, do_pull=not args.no_pull)

    payload = json.dumps(report, indent=2, sort_keys=True)
    if args.output is not None:
        args.output.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    print(format_summary(report), file=sys.stderr)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(run(sys.argv[1:]))
