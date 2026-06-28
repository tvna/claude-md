# Pre-push gate performance and the test-suite speed redesign

Tracking issue: #985. Companion code: `.githooks/pre-push`,
`scripts/preflight_all.py`, `scripts/preflight_cache.py`, `tests/conftest.py`,
`pyproject.toml` (`[dependency-groups] local` -> `pytest-xdist`).

This standard records *why* the pre-push verification gate was slow, the
redesign that made it fast, and the invariants a future change must preserve so
the gate stays fast **without** weakening any deterministic check.

## The problem

`.githooks/pre-push` runs `scripts/preflight_all.py`, which mirrors the gates CI
runs on `pull_request:`. Its `pytest` step executed the entire suite serially
(`uv run python -m pytest -q`). Two costs compounded:

1. **Serial full suite (~294s).** Measured at 3222+ tests / ~4m53s (#985).
2. **The re-push multiplier.** A single PR cycle re-runs the suite once per push
   attempt. PR #983 needed four pushes (rebase, stale `--force-with-lease`, new
   branch); ~14.5 minutes of pytest burned, none of it exercising a source
   change after the first green run.

A 5-minute, all-or-nothing gate pushes contributors toward the full
`PREFLIGHT_SKIP_ALL=1` bypass, which skips *every* gate at once; a strictly
worse safety posture than a fast gate that always runs. (Narrowing the routine
`PREFLIGHT_SKIP=1` lever to skip only `prek`, issue #2133, keeps the cheap gates
running, but a fast suite is what removes the pull toward the full bypass.)

## Root cause: real `time.sleep` backoff in tests, not CPU

Profiling (#985) showed the dominant cost was **idle wall-clock**, not work.
Roughly 29 tests that drive high-level entry points; `auto_retro.run` via
`fetch_check_runs`, and the `_github_api.apply_call` retry path; pay the real
`(2, 4, 8)`s / `(5, 10)`s retry backoff because they do not inject the
`sleeper` seam. Each such test waited ~14s. That is ~400s of pure sleeping,
which `pytest-xdist` cannot parallelise away (idle time, not work): `-n auto`
on its own moved the flat suite only 294s -> 273s.

The seam was *present* (`sleeper: Callable = time.sleep`) but unreachable from a
test harness, because a default argument captures `time.sleep` **at import
time**. Patching `time.sleep` afterwards cannot reach an already-bound default.

## The redesign

Five changes, layered cheapest-first. Each preserves coverage parity with CI.

### 1. Make the sleeper seam patchable (the big lever)

Sleeping seams now resolve `time.sleep` **at call time** instead of capturing it
as a default argument:

```python
def fetch_check_runs(..., sleeper: Callable[[float], None] | None = None):
    sleeper = sleeper if sleeper is not None else time.sleep
    ...
```

`tests/conftest.py` then installs one autouse fixture that makes `time.sleep` a
no-op for every test. Because resolution is now at call time, the patch reaches
the seam.

**Coverage parity holds exactly.** The same code paths execute and the same
assertions run; only the *waiting* is removed. Tests that assert backoff
*values* inject their own fake `sleeper` (a Mock) and never touch `time.sleep`,
so they are unaffected. A test that needs a real delay restores it within its
own scope via `monkeypatch.setattr(time, "sleep", ...)`.

Scope discipline: apply the seam change only to modules whose tests actually pay
the backoff, and keep each changed file at or above the per-file coverage floor
(`scripts/preflight_coverage.py`, currently 90%). Fixing `apply_call` in
`_github_api.py` also speeds up every caller's retry tests *through* it, so the
seam does not need to be repeated in each caller.

### 2. Parallelise pytest with xdist

The pre-push `pytest` step runs `uv run --group local python -m pytest -q -n
auto`. `pytest-xdist` lives in the `local` dependency group (local-only; CI
parallelises across its shard matrix instead), so the run activates it
explicitly. This parallelises the residual real work across cores.

### 3. Content-addressed skip cache (strict parity, kills the multiplier)

`scripts/preflight_cache.py` fingerprints the test-relevant working tree
(`scripts/`, `tests/`, `pyproject.toml`, `uv.lock`) plus the pytest argv. After
a green heavy-tier run the fingerprint is recorded at
`<git-dir>/preflight_heavy_cache.json` (per-clone, untracked). On the next push,
if the fingerprint is byte-identical the heavy step is reported `pass (cached)`
and not re-executed.

This is the durable fix for the #983 multiplier: re-pushes of an unchanged tree
cost ~0s. It does not weaken the gate; the cached pass *was* produced by the
full suite at that exact tree, and any edit, dependency bump, or command change
busts the fingerprint and forces a full run. `PREFLIGHT_NO_CACHE=1` forces a
full run and refreshes the fingerprint.

### 4. Fail-fast: cheap gates before the heavy suite

`preflight_all.run_all` runs all cheap, sub-second gates first (branch-base,
ruff, mypy, static scans). Heavy steps (`heavy=True`, i.e. pytest)
run **only** when every cheap step passed. A branch-base
failure now short-circuits in under a second instead of after the suite; the
PR #983 "5 minutes then rejected for an unrelated reason" failure mode.

### 5. Observability and de-duplication

`preflight_all` prints per-step wall-clock and a total, so the slow gate is
identifiable from the summary alone. The duplicate `preflight_branch_base.py
verify` call was removed from `.githooks/pre-push` (it is a cheap step inside
`preflight_all.py`, which now runs the cheap tier before pytest).

## Result

Full suite under the new pre-push command: ~294s -> ~4s with all tests passing
(measured #985). Re-push of an unchanged tree: ~0s (cache). The deterministic
set is identical to CI's; nothing was removed.

## Invariants for future changes

- **Never trade a deterministic gate for speed.** The full suite still runs; the
  cache only skips a re-run that is provably redundant (identical fingerprint),
  and CI's sharded matrix remains the backstop.
- **New sleeping code uses the call-time seam** (`sleeper=None` then resolve), so
  the autouse no-op fixture keeps tests fast.
- **Touch only the seams whose tests pay backoff**, and keep every changed script
  at or above the per-file coverage floor before pushing.
- **Re-measure on change.** `time uv run --group local python -m pytest -q -n
  auto` is the pre-push wall-clock; record it when a change claims a perf delta.
