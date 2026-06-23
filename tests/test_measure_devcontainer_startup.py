"""Unit tests for scripts/measure_devcontainer_startup.py (Refs #1322).

All container interaction is funnelled through an injectable runner/session, so
these tests exercise the parsing, argv-building, aggregation, and CLI wiring
with fakes and never touch a real container runtime.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import measure_devcontainer_startup as mod
import pytest

pytestmark = pytest.mark.shard_ci_ops


class FakeProc:
    """Stand-in for subprocess.CompletedProcess."""

    def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def make_runner(results: list[FakeProc]) -> tuple[Any, list[list[str]]]:
    """Return a runner that yields ``results`` in order, plus a calls log."""
    calls: list[list[str]] = []
    iterator = iter(results)

    def runner(cmd: list[str], **_kwargs: Any) -> FakeProc:
        calls.append(cmd)
        return next(iterator)

    return runner, calls


def make_clock(values: list[float]) -> Any:
    """Return a clock callable that yields ``values`` in order."""
    iterator = iter(values)
    return lambda: next(iterator)


# --------------------------------------------------------------------------- #
# _run
# --------------------------------------------------------------------------- #


def test_run_times_and_wraps_result() -> None:
    runner, calls = make_runner([FakeProc(returncode=3, stdout="hi")])
    result = mod._run(["docker", "ps"], runner=runner, clock=make_clock([10.0, 10.75]))
    assert result == mod.RunResult(returncode=3, stdout="hi", seconds=0.75)
    assert calls == [["docker", "ps"]]


def test_run_captures_stderr() -> None:
    runner, _calls = make_runner([FakeProc(returncode=1, stdout="out", stderr="boom")])
    result = mod._run(["docker", "x"], runner=runner, clock=make_clock([0.0, 1.0]))
    assert result.stderr == "boom"


def test_run_tolerates_runner_without_stderr() -> None:
    # A fake that models only stdout (no stderr attr) must not crash _run.
    class StdoutOnly:
        returncode = 0
        stdout = "ok"

    result = mod._run(["x"], runner=lambda *_a, **_k: StdoutOnly(), clock=make_clock([0.0, 0.0]))
    assert result.stderr == ""


# --------------------------------------------------------------------------- #
# resolve_runtime
# --------------------------------------------------------------------------- #


def test_resolve_runtime_returns_path() -> None:
    assert mod.resolve_runtime("docker", which=lambda _name: "/usr/bin/docker") == "/usr/bin/docker"


def test_resolve_runtime_missing_raises() -> None:
    with pytest.raises(ValueError, match="container runtime not found"):
        mod.resolve_runtime("docker", which=lambda _name: None)


# --------------------------------------------------------------------------- #
# load_config / get_image / split_segments
# --------------------------------------------------------------------------- #


def test_load_config_reads_json(tmp_path: Path) -> None:
    cfg = tmp_path / "devcontainer.json"
    cfg.write_text('{"image": "x"}', encoding="utf-8")
    assert mod.load_config(cfg) == {"image": "x"}


def test_load_config_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="cannot read devcontainer config"):
        mod.load_config(tmp_path / "absent.json")


def test_load_config_malformed_raises(tmp_path: Path) -> None:
    cfg = tmp_path / "bad.json"
    cfg.write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError, match="malformed JSON"):
        mod.load_config(cfg)


def test_load_config_non_object_raises(tmp_path: Path) -> None:
    cfg = tmp_path / "arr.json"
    cfg.write_text("[1, 2]", encoding="utf-8")
    with pytest.raises(ValueError, match="not an object"):
        mod.load_config(cfg)


def test_get_image_ok() -> None:
    assert mod.get_image({"image": "ghcr.io/x/y:abc123"}) == "ghcr.io/x/y:abc123"


@pytest.mark.parametrize("image", ["ghcr.io/x/y:main", "ghcr.io/x/y:latest"])
def test_get_image_rejects_mutable_tag(image: str) -> None:
    with pytest.raises(ValueError, match="mutable image tag"):
        mod.get_image({"image": image})


@pytest.mark.parametrize("config", [{}, {"image": ""}, {"image": 5}])
def test_get_image_missing_raises(config: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match="no string 'image'"):
        mod.get_image(config)


def test_reject_mutable_tag_passes_immutable() -> None:
    assert mod.reject_mutable_tag("claude-md-measure:local") == "claude-md-measure:local"


@pytest.mark.parametrize("image", ["x:main", "x:latest"])
def test_reject_mutable_tag_rejects(image: str) -> None:
    with pytest.raises(ValueError, match="mutable image tag"):
        mod.reject_mutable_tag(image)


def test_split_segments_splits_on_and() -> None:
    assert mod.split_segments("a && b && c") == ["a", "b", "c"]


def test_split_segments_trims_and_drops_empty() -> None:
    assert mod.split_segments("  a &&  && b ") == ["a", "b"]


@pytest.mark.parametrize("value", [None, "", "   "])
def test_split_segments_empty(value: str | None) -> None:
    assert mod.split_segments(value) == []


def test_split_segments_no_separator_returns_whole() -> None:
    cmd = 'if [ "$X" = "1" ]; then run; fi'
    assert mod.split_segments(cmd) == [cmd]


# --------------------------------------------------------------------------- #
# DockerSession argv builders
# --------------------------------------------------------------------------- #


def make_session(results: list[FakeProc], **overrides: Any) -> tuple[mod.DockerSession, list[list[str]]]:
    runner, calls = make_runner(results)
    defaults: dict[str, Any] = {
        "runtime": "/usr/bin/docker",
        "image": "img:sha",
        "workspace": "/workspaces/claude-md",
        "user": "claude",
        "host_dir": "/host/repo",
        "caps": [],
        "runner": runner,
        "clock": make_clock([0.0] * 20),
    }
    defaults.update(overrides)
    return mod.DockerSession(**defaults), calls


def test_session_pull_argv() -> None:
    session, calls = make_session([FakeProc(stdout="")])
    session.pull()
    assert calls == [["/usr/bin/docker", "pull", "img:sha"]]


def test_session_image_size_parses_int() -> None:
    session, _calls = make_session([FakeProc(stdout="12345\n")])
    assert session.image_size() == 12345


def test_session_image_size_failure_raises() -> None:
    session, _calls = make_session([FakeProc(returncode=1, stdout="")])
    with pytest.raises(ValueError, match="image inspect failed"):
        session.image_size()


def test_session_start_argv_and_id() -> None:
    session, calls = make_session([FakeProc(stdout="container99\n")], caps=["NET_ADMIN"])
    session.start()
    assert session.container_id == "container99"
    assert calls[0] == [
        "/usr/bin/docker",
        "run",
        "-d",
        "--rm",
        "-w",
        "/workspaces/claude-md",
        "-v",
        "/host/repo:/workspaces/claude-md",
        "--user",
        "claude",
        "--cap-add",
        "NET_ADMIN",
        "img:sha",
        "sleep",
        "infinity",
    ]


def test_session_start_without_user_omits_flag() -> None:
    session, calls = make_session([FakeProc(stdout="c1")], user="")
    session.start()
    assert "--user" not in calls[0]


def test_session_start_failure_raises() -> None:
    session, _calls = make_session([FakeProc(returncode=1, stdout="")])
    with pytest.raises(ValueError, match="failed to start container"):
        session.start()


def test_session_exec_before_start_raises() -> None:
    session, _calls = make_session([])
    with pytest.raises(ValueError, match="exec called before start"):
        session.exec("echo hi")


def test_session_exec_argv() -> None:
    session, calls = make_session([FakeProc(stdout="cid"), FakeProc(stdout="ok")])
    session.start()
    session.exec("uv sync")
    assert calls[1] == ["/usr/bin/docker", "exec", "cid", "bash", "-lc", "uv sync"]


def test_session_close_removes_container() -> None:
    session, calls = make_session([FakeProc(stdout="cid"), FakeProc(stdout="")])
    session.start()
    session.close()
    assert calls[1] == ["/usr/bin/docker", "rm", "-f", "cid"]
    assert session.container_id is None


def test_session_close_without_start_is_noop() -> None:
    session, calls = make_session([])
    session.close()
    assert calls == []


# --------------------------------------------------------------------------- #
# measure
# --------------------------------------------------------------------------- #


class FakeSession:
    """In-memory Session for measure() tests."""

    def __init__(self, *, exec_results: dict[str, mod.RunResult], size: int = 100) -> None:
        self.image = "img:sha"
        self._exec_results = exec_results
        self._size = size
        self.events: list[str] = []

    def pull(self) -> mod.RunResult:
        self.events.append("pull")
        return mod.RunResult(returncode=0, stdout="", seconds=2.5)

    def image_size(self) -> int:
        return self._size

    def start(self) -> None:
        self.events.append("start")

    def exec(self, segment: str) -> mod.RunResult:
        self.events.append(f"exec:{segment}")
        return self._exec_results[segment]

    def close(self) -> None:
        self.events.append("close")


def test_measure_full_report() -> None:
    session = FakeSession(
        exec_results={
            "uv sync": mod.RunResult(0, "", 4.0),
            "egress": mod.RunResult(7, "", 0.2),
        },
        size=2_000_000,
    )
    report = measure_report = mod.measure(session, post_create=["uv sync"], post_start=["egress"], do_pull=True)
    assert report["image"] == "img:sha"
    assert report["pull_seconds"] == 2.5
    assert report["pull_returncode"] == 0
    assert report["image_size_bytes"] == 2_000_000
    assert report["phases"] == [
        {"phase": "postCreate", "command": "uv sync", "seconds": 4.0, "returncode": 0},
        {"phase": "postStart", "command": "egress", "seconds": 0.2, "returncode": 7},
    ]
    assert report["total_phase_seconds"] == 4.2
    assert session.events == ["pull", "start", "exec:uv sync", "exec:egress", "close"]
    assert measure_report is report


def test_measure_skips_pull() -> None:
    session = FakeSession(exec_results={})
    report = mod.measure(session, post_create=[], post_start=[], do_pull=False)
    assert "pull_seconds" not in report
    assert session.events == ["start", "close"]


def test_measure_closes_on_exec_error() -> None:
    class Boom(FakeSession):
        def exec(self, segment: str) -> mod.RunResult:
            self.events.append("exec")
            raise RuntimeError("boom")

    session = Boom(exec_results={})
    with pytest.raises(RuntimeError, match="boom"):
        mod.measure(session, post_create=["x"], post_start=[], do_pull=False)
    assert session.events[-1] == "close"


def test_measure_runs_warmup_before_postcreate() -> None:
    session = FakeSession(
        exec_results={
            "nix develop .#claude --command true": mod.RunResult(0, "", 18.0),
            "uv sync": mod.RunResult(0, "", 6.0),
        },
    )
    report = mod.measure(
        session,
        post_create=["uv sync"],
        post_start=[],
        warmup=["nix develop .#claude --command true"],
        do_pull=False,
    )
    assert report["phases"] == [
        {
            "phase": "warmup",
            "command": "nix develop .#claude --command true",
            "seconds": 18.0,
            "returncode": 0,
        },
        {"phase": "postCreate", "command": "uv sync", "seconds": 6.0, "returncode": 0},
    ]
    # Warmup is exec'd before postCreate so the closure is warm for uv sync.
    assert session.events == [
        "start",
        "exec:nix develop .#claude --command true",
        "exec:uv sync",
        "close",
    ]
    assert report["total_phase_seconds"] == 24.0


def test_measure_no_warmup_keeps_phases_unchanged() -> None:
    session = FakeSession(exec_results={"uv sync": mod.RunResult(0, "", 6.0)})
    report = mod.measure(session, post_create=["uv sync"], post_start=[], do_pull=False)
    assert [p["phase"] for p in report["phases"]] == ["postCreate"]


def test_measure_records_stderr_tail_only_on_failure_with_content() -> None:
    session = FakeSession(
        exec_results={
            "ok": mod.RunResult(0, "", 1.0, stderr="noise on success"),
            "boom": mod.RunResult(1, "", 0.5, stderr="line1\nfatal: boom"),
            "silent": mod.RunResult(2, "", 0.1, stderr="   "),
        },
    )
    report = mod.measure(session, post_create=["ok", "boom", "silent"], post_start=[], do_pull=False)
    phases = {p["command"]: p for p in report["phases"]}
    assert "stderr_tail" not in phases["ok"]  # clean exit needs no explanation
    assert phases["boom"]["stderr_tail"] == "line1\nfatal: boom"
    assert "stderr_tail" not in phases["silent"]  # failed but empty stderr


# --------------------------------------------------------------------------- #
# _stderr_tail
# --------------------------------------------------------------------------- #


def test_stderr_tail_keeps_last_lines() -> None:
    text = "\n".join(f"line{i}" for i in range(50))
    tail = mod._stderr_tail(text)
    assert tail.splitlines()[0] == "line30"  # last 20 of 0..49
    assert tail.splitlines()[-1] == "line49"


def test_stderr_tail_caps_chars() -> None:
    assert len(mod._stderr_tail("x" * 5000)) == mod._STDERR_TAIL_CHARS


def test_stderr_tail_sanitises_non_ascii() -> None:
    tail = mod._stderr_tail("cafeé boom")
    assert tail.isascii()
    assert "boom" in tail


# --------------------------------------------------------------------------- #
# _parse_du / probe_composition
# --------------------------------------------------------------------------- #


def test_parse_du_extracts_size_and_path() -> None:
    out = "12345\t/nix/store/aaa-foo\n6789\t/nix/store/bbb-bar\n"
    assert mod._parse_du(out) == [
        {"bytes": 12345, "path": "/nix/store/aaa-foo"},
        {"bytes": 6789, "path": "/nix/store/bbb-bar"},
    ]


def test_parse_du_skips_blank_and_malformed() -> None:
    out = "\n  \nnotanumber /x\n42 /ok\nonlyonefield\n"
    assert mod._parse_du(out) == [{"bytes": 42, "path": "/ok"}]


def test_probe_composition_splits_total_top_and_base() -> None:
    store_out = "\n".join(
        [
            "900\t/nix/store",  # total line, excluded from top
            "500\t/nix/store/aaa-python",
            "300\t/nix/store/bbb-node",
            "100\t/nix/store/ccc-ruff",
        ]
    )
    base_out = "200\t/usr\n50\t/opt\n"
    session = FakeSession(
        exec_results={
            mod._STORE_DU_CMD: mod.RunResult(0, store_out, 0.1),
            mod._BASE_DU_CMD: mod.RunResult(0, base_out, 0.1),
        }
    )
    result = mod.probe_composition(session, top_n=2)
    assert result["nix_store_bytes"] == 900
    assert result["top_store_paths"] == [
        {"bytes": 500, "path": "/nix/store/aaa-python"},
        {"bytes": 300, "path": "/nix/store/bbb-node"},
    ]
    assert result["base_dirs"] == [{"bytes": 200, "path": "/usr"}, {"bytes": 50, "path": "/opt"}]


def test_probe_composition_missing_total_defaults_zero() -> None:
    session = FakeSession(
        exec_results={
            mod._STORE_DU_CMD: mod.RunResult(0, "500\t/nix/store/aaa", 0.1),
            mod._BASE_DU_CMD: mod.RunResult(0, "", 0.1),
        }
    )
    result = mod.probe_composition(session)
    assert result["nix_store_bytes"] == 0
    assert result["base_dirs"] == []


def test_store_du_cmd_excludes_links_farm() -> None:
    # Phase 1b (#1332): the store walk MUST exclude /nix/store/.links, else nix
    # store optimisation (a content-addressed hardlink farm) makes du pile the
    # whole closure onto the .links line and report the real package dirs as ~0
    # bytes; hiding the per-derivation cut target. This is the contract that
    # made the breakdown resolvable; lock it so a refactor cannot silently drop
    # the exclude and regress to an unusable composition probe.
    assert "--exclude=.links" in mod._STORE_DU_CMD
    assert "/nix/store" in mod._STORE_DU_CMD
    # The base-distro walk has no .links farm and must not carry the exclude.
    assert "--exclude" not in mod._BASE_DU_CMD


def test_measure_with_probe_adds_composition() -> None:
    session = FakeSession(
        exec_results={
            "uv sync": mod.RunResult(0, "", 1.0),
            mod._STORE_DU_CMD: mod.RunResult(0, "900\t/nix/store\n500\t/nix/store/aaa", 0.1),
            mod._BASE_DU_CMD: mod.RunResult(0, "200\t/usr", 0.1),
        }
    )
    report = mod.measure(session, post_create=["uv sync"], post_start=[], do_pull=False, probe=True)
    assert report["composition"]["nix_store_bytes"] == 900
    assert report["composition"]["top_store_paths"] == [{"bytes": 500, "path": "/nix/store/aaa"}]
    # Probe runs while the container is up, before close.
    assert session.events[-3:] == [f"exec:{mod._STORE_DU_CMD}", f"exec:{mod._BASE_DU_CMD}", "close"]


def test_measure_without_probe_has_no_composition() -> None:
    session = FakeSession(exec_results={})
    report = mod.measure(session, post_create=[], post_start=[], do_pull=False)
    assert "composition" not in report


# --------------------------------------------------------------------------- #
# _human_size / format_summary
# --------------------------------------------------------------------------- #


def test_human_size_mib() -> None:
    assert mod._human_size(5 * 1024 * 1024) == "5.0 MiB"


def test_human_size_gib() -> None:
    assert mod._human_size(3 * 1024 * 1024 * 1024) == "3.00 GiB"


def test_format_summary_includes_rows_and_pull() -> None:
    report = {
        "image": "img:sha",
        "image_size_bytes": 2 * 1024 * 1024,
        "pull_seconds": 1.234,
        "pull_returncode": 0,
        "total_phase_seconds": 4.0,
        "phases": [{"phase": "postCreate", "command": "uv sync", "seconds": 4.0, "returncode": 0}],
    }
    summary = mod.format_summary(report)
    assert "image: `img:sha`" in summary
    assert "2.0 MiB" in summary
    assert "pull: 1.234s" in summary
    assert "| postCreate | 4.000 | 0 | uv sync |" in summary
    assert summary.isascii()


def test_format_summary_flags_failed_pull_and_truncates() -> None:
    long_cmd = "x" * 120
    report = {
        "image": "img:sha",
        "image_size_bytes": 10,
        "pull_seconds": 0.5,
        "pull_returncode": 1,
        "total_phase_seconds": 0.0,
        "phases": [{"phase": "postStart", "command": long_cmd, "seconds": 0.0, "returncode": 0}],
    }
    summary = mod.format_summary(report)
    assert "pull: 0.500s (FAILED)" in summary
    assert "..." in summary
    assert long_cmd not in summary


def test_format_summary_renders_segment_failures() -> None:
    report = {
        "image": "img:sha",
        "image_size_bytes": 10,
        "total_phase_seconds": 0.5,
        "phases": [
            {
                "phase": "postCreate",
                "command": "nix develop",
                "seconds": 0.5,
                "returncode": 1,
                "stderr_tail": "fatal: permission denied",
            },
            {"phase": "postStart", "command": "egress", "seconds": 0.0, "returncode": 0},
        ],
    }
    summary = mod.format_summary(report)
    assert "## Segment failures" in summary
    assert "postCreate (exit 1): `nix develop`" in summary
    assert "fatal: permission denied" in summary
    assert summary.isascii()


def test_format_summary_no_failures_section_when_all_pass() -> None:
    report = {
        "image": "img:sha",
        "image_size_bytes": 10,
        "total_phase_seconds": 0.0,
        "phases": [{"phase": "postCreate", "command": "ok", "seconds": 0.1, "returncode": 0}],
    }
    assert "Segment failures" not in mod.format_summary(report)


def test_format_summary_without_pull() -> None:
    report = {
        "image": "img:sha",
        "image_size_bytes": 10,
        "total_phase_seconds": 0.0,
        "phases": [],
    }
    summary = mod.format_summary(report)
    assert "pull:" not in summary


def test_format_summary_renders_composition() -> None:
    report = {
        "image": "img:sha",
        "image_size_bytes": 10,
        "total_phase_seconds": 0.0,
        "phases": [],
        "composition": {
            "nix_store_bytes": 3 * 1024 * 1024 * 1024,
            "top_store_paths": [{"bytes": 500 * 1024 * 1024, "path": "/nix/store/aaa-python"}],
            "base_dirs": [{"bytes": 2 * 1024 * 1024, "path": "/usr"}],
        },
    }
    summary = mod.format_summary(report)
    assert "## Image composition" in summary
    assert "/nix/store: 3.00 GiB" in summary
    assert "| /usr | 2.0 MiB |" in summary
    assert "| /nix/store/aaa-python | 500.0 MiB |" in summary
    assert summary.isascii()


def test_format_summary_without_composition_has_no_section() -> None:
    report = {
        "image": "img:sha",
        "image_size_bytes": 10,
        "total_phase_seconds": 0.0,
        "phases": [],
    }
    assert "Image composition" not in mod.format_summary(report)


# --------------------------------------------------------------------------- #
# run (CLI)
# --------------------------------------------------------------------------- #


def write_config(tmp_path: Path) -> Path:
    cfg = tmp_path / "devcontainer.json"
    cfg.write_text(
        json.dumps(
            {
                "image": "ghcr.io/x/y:abc",
                "postCreateCommand": "uv sync && install cli",
                "postStartCommand": "egress",
            }
        ),
        encoding="utf-8",
    )
    return cfg


def test_run_end_to_end(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    captured: dict[str, Any] = {}

    def factory(**kwargs: Any) -> FakeSession:
        captured.update(kwargs)
        return FakeSession(
            exec_results={
                "uv sync": mod.RunResult(0, "", 1.0),
                "install cli": mod.RunResult(0, "", 2.0),
                "egress": mod.RunResult(0, "", 0.5),
            }
        )

    out = tmp_path / "report.json"
    rc = mod.run(
        ["--config", str(write_config(tmp_path)), "--output", str(out), "--cap", "NET_ADMIN"],
        session_factory=factory,
        which=lambda _name: "/usr/bin/docker",
    )
    assert rc == 0
    assert captured["runtime"] == "/usr/bin/docker"
    assert captured["image"] == "ghcr.io/x/y:abc"
    assert captured["caps"] == ["NET_ADMIN"]
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["total_phase_seconds"] == 3.5
    assert json.loads(capsys.readouterr().out)["total_phase_seconds"] == 3.5


def test_run_no_pull(tmp_path: Path) -> None:
    sessions: list[FakeSession] = []

    def factory(**_kwargs: Any) -> FakeSession:
        session = FakeSession(
            exec_results={
                "uv sync": mod.RunResult(0, "", 1.0),
                "install cli": mod.RunResult(0, "", 2.0),
                "egress": mod.RunResult(0, "", 0.5),
            }
        )
        sessions.append(session)
        return session

    rc = mod.run(
        ["--config", str(write_config(tmp_path)), "--no-pull"],
        session_factory=factory,
        which=lambda _name: "/usr/bin/docker",
    )
    assert rc == 0
    assert "pull" not in sessions[0].events


def test_run_image_override_replaces_config_image(tmp_path: Path) -> None:
    # --image overrides the config's image (used to measure a locally built
    # image from .devcontainer/images/<agent>) while the lifecycle segments
    # still come from --config. Refs #1491.
    captured: dict[str, Any] = {}

    def factory(**kwargs: Any) -> FakeSession:
        captured.update(kwargs)
        return FakeSession(
            exec_results={
                "uv sync": mod.RunResult(0, "", 1.0),
                "install cli": mod.RunResult(0, "", 2.0),
                "egress": mod.RunResult(0, "", 0.5),
            }
        )

    rc = mod.run(
        ["--config", str(write_config(tmp_path)), "--image", "claude-md-measure:local", "--no-pull"],
        session_factory=factory,
        which=lambda _name: "/usr/bin/docker",
    )
    assert rc == 0
    assert captured["image"] == "claude-md-measure:local"


def test_run_image_override_rejects_mutable_tag(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="mutable image tag"):
        mod.run(
            ["--config", str(write_config(tmp_path)), "--image", "x:latest", "--no-pull"],
            session_factory=lambda **_kwargs: FakeSession(exec_results={}),
            which=lambda _name: "/usr/bin/docker",
        )


def test_run_probe_composition_end_to_end(tmp_path: Path) -> None:
    def factory(**_kwargs: Any) -> FakeSession:
        return FakeSession(
            exec_results={
                "uv sync": mod.RunResult(0, "", 1.0),
                "install cli": mod.RunResult(0, "", 2.0),
                "egress": mod.RunResult(0, "", 0.5),
                mod._STORE_DU_CMD: mod.RunResult(0, "900\t/nix/store\n500\t/nix/store/aaa", 0.1),
                mod._BASE_DU_CMD: mod.RunResult(0, "200\t/usr", 0.1),
            }
        )

    out = tmp_path / "report.json"
    rc = mod.run(
        ["--config", str(write_config(tmp_path)), "--output", str(out), "--probe-composition", "--top-n", "5"],
        session_factory=factory,
        which=lambda _name: "/usr/bin/docker",
    )
    assert rc == 0
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["composition"]["nix_store_bytes"] == 900
    assert report["composition"]["top_store_paths"] == [{"bytes": 500, "path": "/nix/store/aaa"}]
