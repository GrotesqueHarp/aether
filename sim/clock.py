"""
clock.py — A virtual clock for headless simulation.

Every AETHER module calls `time.time()` at call time (nothing does
`from time import time`), so replacing the attribute on the time module makes
the whole game believe whatever we tell it. That means a simulated month runs
in a couple of seconds without a single sleep and without touching game code.

    with VirtualClock() as clk:
        clk.advance(hours=6)
        ticker.apply_drift(clk.now)

`time.sleep` is stubbed to a no-op for the same reason: nothing should ever
actually block during a simulation.
"""

from __future__ import annotations

import time as _time

# a fixed, boring epoch so runs are reproducible and log timestamps are stable
DEFAULT_START = 1_760_000_000.0


class VirtualClock:
    def __init__(self, start: float = DEFAULT_START):
        self.now = float(start)
        self.start = float(start)
        self._real_time = _time.time
        self._real_sleep = _time.sleep
        self._installed = False

    # -- control -------------------------------------------------------------
    def advance(self, seconds: float = 0, minutes: float = 0, hours: float = 0,
                days: float = 0) -> float:
        self.now += seconds + minutes * 60 + hours * 3600 + days * 86400
        return self.now

    @property
    def elapsed(self) -> float:
        return self.now - self.start

    @property
    def elapsed_days(self) -> float:
        return self.elapsed / 86400.0

    @property
    def elapsed_hours(self) -> float:
        return self.elapsed / 3600.0

    def wall_time(self) -> float:
        """Real wall-clock time, for measuring how fast the sim itself runs."""
        return self._real_time()

    # -- patching ------------------------------------------------------------
    def install(self):
        if self._installed:
            return self
        _time.time = lambda: self.now
        _time.sleep = lambda _s=0: None
        self._installed = True
        return self

    def uninstall(self):
        if not self._installed:
            return
        _time.time = self._real_time
        _time.sleep = self._real_sleep
        self._installed = False

    def __enter__(self):
        return self.install()

    def __exit__(self, *exc):
        self.uninstall()
        return False
