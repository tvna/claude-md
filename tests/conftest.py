"""Shared pytest fixtures for the scripts test-suite.

Refs #985. The dominant pre-push / CI cost was not CPU but real wall-clock
``time.sleep`` backoff: high-level entry points such as ``auto_retro.run`` (via
``fetch_check_runs``) and ``ci_early_status_probe.decide`` retry remote calls
with a ``(2, 4, 8)``-second backoff, and the ~29 tests that exercise those
entry points do not inject the ``sleeper`` seam, so each paid ~14s of *real*
waiting; roughly 400s of the suite, which pytest-xdist cannot parallelise
away because it is idle time, not work.

The autouse fixture below makes ``time.sleep`` a no-op for every test. This is
effective only because the sleeper seams now resolve ``time.sleep`` at call
time (``sleeper = sleeper if sleeper is not None else time.sleep``) rather than
capturing it as an import-time default argument; patching the module attribute
therefore reaches them.

Coverage parity is preserved exactly; the same code paths execute and the
same assertions run. Tests that assert *backoff values* inject their own fake
``sleeper`` (a Mock) and never reach ``time.sleep``, so they are unaffected. A
test that genuinely needs a real delay can restore it within its own scope via
``monkeypatch.setattr(time, "sleep", _real_sleep)``.
"""

from __future__ import annotations

import time
from collections.abc import Iterator

import pytest


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Make ``time.sleep`` a no-op so retry/backoff waits do not burn wall time.

    Scoped per-test via ``monkeypatch`` so any test that explicitly re-patches
    ``time.sleep`` (or restores the real one) overrides this cleanly.
    """
    monkeypatch.setattr(time, "sleep", lambda _seconds: None)
    yield
