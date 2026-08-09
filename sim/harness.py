"""
harness.py — Run AETHER headless, at speed, against a scratch database.

The point: milestones we care about are days apart, so we can never feel them
by playing. This runs the REAL game modules — same economy, same battle sim,
same ticker functions the container calls — on a virtual clock, so a simulated
month costs a couple of seconds and produces a timeline we can actually tune
against.

Nothing here reimplements game logic. If the sim says a tier takes nine days,
that is what the shipped code does.

    sim = Sim(env={"AETHER_ECON_MULT": "3"})
    sim.run(days=14, policy=IdlePolicy())
    sim.report()
"""

from __future__ import annotations

import importlib
import os
import sys
import tempfile

from .clock import VirtualClock

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

# core.db reads AETHER_DB at import time, so these must be reloaded after the
# environment is set for a given run
_GAME_MODULES = ["core.seed", "core.content", "core.daemon", "core.battle",
                 "core.world", "core.scan", "core.db", "core.economy",
                 "core.bastion", "core.war", "core.ticker"]


class Policy:
    """Decides what the player does. Chunk 2 gives this a brain."""
    name = "base"

    def act(self, sim: "Sim"):
        pass


class IdlePolicy(Policy):
    """The control group: never touches the game. Useful for isolating pure
    drift/decay behavior and proving the harness itself doesn't leak."""
    name = "idle"


class Sim:
    def __init__(self, env: dict | None = None, db_path: str | None = None,
                 keep_online: bool = True, mock_lan: bool = True,
                 heartbeat_minutes: float = 15.0, diagnostics: bool = True,
                 start: float | None = None):
        self.db_path = db_path or os.path.join(
            tempfile.mkdtemp(prefix="aether-sim-"), "sim.db")
        self.keep_online = keep_online
        self.heartbeat_minutes = heartbeat_minutes
        self.diagnostics = diagnostics
        self._last_heartbeat = 0.0
        self.online_macs: set[str] = set()
        self.snapshots: list[dict] = []
        self._step_count = 0

        # --- environment: sim defaults, caller overrides win.
        # Every AETHER_* key is cleared first: os.environ.update() only adds,
        # so without this a knob set by an earlier run in the same process
        # silently leaks into the next one and an A/B compares a config
        # against itself.
        for key in [k for k in os.environ if k.startswith("AETHER_")]:
            del os.environ[key]
        self.env = {
            "AETHER_DB": self.db_path,
            "AETHER_ECON_MULT": "1.0",
            "AETHER_TRAIN_MULT": "1.0",
            "AETHER_SIGNAL_RATE": "1.0",
            "AETHER_HATCH_SECONDS": str(8 * 3600),
            "AETHER_PRESENCE_GRACE": "600",
        }
        self.env.update(env or {})
        os.environ.update(self.env)

        self.clock = VirtualClock(start=start) if start else VirtualClock()
        self.clock.install()

        # --- (re)load game modules against this run's env
        self.mod = {}
        for name in _GAME_MODULES:
            m = importlib.import_module(name)
            self.mod[name.split(".")[1]] = importlib.reload(m)
        self.db = self.mod["db"]
        self.ticker = self.mod["ticker"]
        self.bastion = self.mod["bastion"]
        self.war = self.mod["war"]
        self.economy = self.mod["economy"]
        self.world = self.mod["world"]

        self.db.init_db()
        if mock_lan:
            self._seed_lan()
        self._bootstrap()

        # The agent plays through the real HTTP routes rather than poking the
        # modules directly — so the sim can never drift from the shipped game.
        # (app.py has no import-time side effects; init/ticker are under
        # __main__, and it binds to the modules we just reloaded.)
        import app as _app
        self.app = _app
        self.client = _app.app.test_client()

    # ------------------------------------------------------------------ setup
    def _seed_lan(self):
        """Persist the mock device set — same path the /api/scan route uses.

        We also stub the ARP reader: there is no real network here, and the
        real one shells out plus does a blocking reverse-DNS lookup per entry.
        `online_macs` is the sim's model of physical reality — drop a MAC from
        it to simulate a device powering off, and dormancy follows naturally.
        """
        self._devices = self.mod["scan"].mock_devices()
        self.online_macs = {d["mac"] for d in self._devices}
        scan = self.mod["scan"]
        scan.read_arp_table = lambda: [
            {"mac": d["mac"], "ip": d.get("ip", ""),
             "hostname": d.get("hostname", ""), "vendor": d.get("vendor", "")}
            for d in self._devices if d["mac"] in self.online_macs]
        for d in self._devices:
            self.db.upsert_device(d["mac"], d.get("hostname", ""),
                                  d.get("ip", ""), d.get("vendor", ""),
                                  online=True)

    def set_online(self, mac: str, online: bool = True):
        """Simulate a device powering on/off mid-run."""
        self.online_macs.add(mac) if online else self.online_macs.discard(mac)

    def _bootstrap(self):
        from core.daemon import starter_daemon
        if self.db.get_meta("bootstrapped") != "1":
            self.db.add_daemon(starter_daemon())
            self.db.set_meta("bootstrapped", "1")

    # ------------------------------------------------------------------- loop
    def step(self, minutes: float = 10.0):
        """Advance the world one beat: everything the container's ticker does."""
        self.clock.advance(minutes=minutes)
        now = self.clock.now

        self.ticker.apply_drift(now)
        self.ticker.tick_expeditions(now)
        self.ticker.tick_harvests(now)
        self.ticker.tick_eggs(now)
        self.bastion.tick_training(now)
        self.war.tick_signal(now)
        self.war.tick_deadlines(now)

        # Models the v0.7 heartbeat: a periodic sweep keeps ARP warm so rifts
        # don't falsely go dormant. Runs on its own cadence, like the real one.
        if now - self._last_heartbeat >= self.heartbeat_minutes * 60:
            self._last_heartbeat = now
            if self.keep_online:
                for mac in self.online_macs:
                    self.db.touch_device(mac)
            self.ticker.check_presence(now)
        self._step_count += 1

    def run(self, days: float = 7.0, step_minutes: float = 10.0,
            policy: Policy | None = None, snapshot_hours: float = 6.0):
        policy = policy or IdlePolicy()
        self.policy = policy
        steps = int(days * 24 * 60 / step_minutes)
        snap_every = max(1, int(snapshot_hours * 60 / step_minutes))
        started = self.clock.wall_time()
        self.snapshot()
        for i in range(steps):
            self.step(step_minutes)
            policy.act(self)
            if (i + 1) % snap_every == 0:
                self.snapshot()
        self.snapshot()
        self.wall_seconds = self.clock.wall_time() - started
        return self

    # -------------------------------------------------------------- inspection
    def snapshot(self) -> dict:
        roster = self.db.list_daemons()
        powers = sorted((d.power() for d in roster), reverse=True)
        rifts = {}
        for dev in self.db.list_devices():
            p = self.db.get_progress(dev["mac"])
            if p["cleared"] or p["tier"] or p["ward"]:
                rifts[dev["hostname"] or dev["mac"]] = {
                    "cleared": p["cleared"], "boss": bool(p["boss_down"]),
                    "tier": p["tier"], "ward": p["ward"]}
        snap = {
            "days": round(self.clock.elapsed_days, 3),
            "hours": round(self.clock.elapsed_hours, 2),
            "resources": {k: round(v, 1) for k, v in self.db.res_all().items()},
            "roster": len(roster),
            "best_power": powers[0] if powers else 0,
            "party_power": sum(powers[:3]),
            "levels": sorted((d.level for d in roster), reverse=True)[:5],
            "facilities": self.db.all_facility_levels(),
            "harvesters": len(self.db.list_harvests()),
            "training": len(self.db.list_training()),
            "eggs": len(self.db.list_eggs()),
            "rifts": rifts,
            "incursions": len(self.db.list_incursions()),
        }
        if self.diagnostics:
            snap.update(self._diagnose())
        self.snapshots.append(snap)
        return snap

    def _diagnose(self) -> dict:
        """What is the player unable to do right now, and why?

        Two questions matter at any moment: what can't I buy, and what can't I
        beat. Recording both at every sample lets us attribute a stall to a
        specific starved resource instead of guessing.
        """
        from .agent import battle_odds
        wallet = self.db.res_all()

        # --- what's unaffordable, and which resource is short
        blocked_by: dict[str, int] = {}
        for key in self.bastion.FACILITIES:
            lvl = self.db.facility_level(key)
            cost = self.bastion.upgrade_cost(key, lvl)
            for res, amt in cost.items():
                if wallet.get(res, 0) < amt:
                    blocked_by[res] = blocked_by.get(res, 0) + 1

        # --- what's unbeatable, and by how much
        party = [d for d in sorted(self.db.list_daemons(), key=lambda x: -x.power())
                 if not (self.db.get_expedition(d.id) or self.db.get_harvest(d.id)
                         or self.db.get_training(d.id))][:3]
        frontier = {}
        for dev in self.db.list_devices():
            mac = dev["mac"]
            depth = self.db.get_progress(mac)["cleared"]
            if depth < self.world.LAYERS:
                frontier[dev["hostname"] or mac] = round(
                    battle_odds(self, party, mac, depth + 1, trials=7), 2)
        return {"blocked_by": blocked_by, "frontier_odds": frontier,
                "best_frontier": max(frontier.values(), default=0.0)}

    def events(self, kinds: tuple[str, ...] | None = None,
               limit: int = 500_000) -> list[dict]:
        evs = self.db.list_events(limit)
        if kinds:
            evs = [e for e in evs if e["kind"] in kinds]
        return list(reversed(evs))          # chronological

    def milestone(self, kind: str) -> float | None:
        """Elapsed days at which an event kind first fired (None if never)."""
        for e in self.events((kind,)):
            return round((e["ts"] - self.clock.start) / 86400.0, 2)
        return None

    def close(self):
        self.clock.uninstall()

    # ------------------------------------------------------------------ output
    def report(self, stream=sys.stdout):
        s = self.snapshots[-1]
        w = getattr(self, "wall_seconds", 0)
        print(f"\n=== {getattr(self, 'policy', IdlePolicy()).name} · "
              f"{s['days']:.1f} simulated days in {w:.2f}s wall "
              f"({self._step_count} steps) ===", file=stream)
        print(f"{'day':>6} {'bits':>11} {'cores':>7} {'roster':>7} "
              f"{'best pw':>8} {'party pw':>9}  rifts", file=stream)
        for snap in self.snapshots:
            r = snap["resources"]
            rifts = " ".join(
                f"{n[:12]}:T{v['tier']}/{v['cleared']}{'★' if v['boss'] else ''}"
                for n, v in snap["rifts"].items()) or "—"
            print(f"{snap['days']:>6.2f} {r.get('bits', 0):>11,.0f} "
                  f"{r.get('cores', 0):>7.1f} {snap['roster']:>7} "
                  f"{snap['best_power']:>8} {snap['party_power']:>9}  {rifts}",
                  file=stream)
        return self
