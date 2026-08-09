"""
agent.py — Something that actually plays AETHER.

Two pieces:

`battle_odds()` runs the deterministic battle sim N times with rotated seeds
and returns a win probability. The sim uses it to decide when to attack; in
v0.8 the same function backs the in-game "party 780 vs 890 — est. 30%"
forecast, so a wall stops being opaque.

`PlayerPolicy` is a person, not a robot. It only acts during *sessions* — a
few check-ins per day with a limited number of actions each — because an
always-on optimizer would report pacing no human will ever experience. Between
sessions only the ticker runs, which is exactly what happens when you close
the tab. If the numbers say "a tier takes two days," they mean two days for
someone who looks at the game three times a day.

Every action goes through the real HTTP API, guards and all.
"""

from __future__ import annotations

from core.battle import simulate_team
from core.daemon import Daemon

from .harness import Policy

# facility build order per strategy: what a player would prioritize
BUILD_ORDERS = {
    "balanced": ["forge", "auto_feeder", "core_chamber", "playroom",
                 "bulwark", "hatchery_wing", "circuit", "cleansing_font", "aegis"],
    "training": ["forge", "core_chamber", "bulwark", "circuit",
                 "auto_feeder", "playroom", "cleansing_font", "aegis",
                 "hatchery_wing"],
    "harvest":  ["hatchery_wing", "auto_feeder", "playroom", "forge",
                 "core_chamber", "cleansing_font", "bulwark", "circuit", "aegis"],
}


# --------------------------------------------------------------- forecasting
def battle_odds(sim, party: list[Daemon], mac: str, node_index: int,
                trials: int = 21) -> float:
    """Win probability for this party against this node, right now."""
    if not party:
        return 0.0
    rift = sim.world.generate_rift(mac)
    if node_index >= len(rift["nodes"]):
        return 0.0
    prog = sim.db.get_progress(mac)
    node = rift["nodes"][node_index]

    enemy = Daemon.from_dict(node["enemy"])
    if sim.ticker.dormancy(mac):
        enemy = sim.ticker.dormant_enemy(enemy)
    enemy = sim.war.scale_enemy(enemy, prog)
    foes = [enemy]
    if node["is_boss"]:
        foes += sim.war.boss_minions(enemy, rift, prog)

    wins = sum(simulate_team(party, foes, seed_extra=f"odds:{node_index}:{i}"
                             )["winner"] == "a" for i in range(trials))
    return wins / trials


# -------------------------------------------------------------------- policy
class PlayerPolicy(Policy):
    name = "player"

    def __init__(self, sessions_per_day: float = 3, actions_per_session: int = 60,
                 win_threshold: float = 0.55, attempt_threshold: float = 0.28,
                 max_retries: int = 6, combat_share: float = 0.5,
                 strategy: str = "balanced",
                 use_expeditions: bool = True, use_crucible: bool = True,
                 crucible_reserve: float = 0.6,
                 max_roster: int = 8,
                 fighters: int = 3, harvest_share: float = 0.6):
        self.sessions_per_day = sessions_per_day
        self.actions_per_session = actions_per_session
        self.win_threshold = win_threshold
        self.attempt_threshold = attempt_threshold
        self.max_retries = max_retries
        self.combat_share = combat_share
        self.strategy = strategy
        self.build_order = BUILD_ORDERS.get(strategy, BUILD_ORDERS["balanced"])
        self.use_expeditions = use_expeditions
        self.use_crucible = use_crucible
        self.crucible_reserve = crucible_reserve
        self.max_roster = max_roster
        self.fighters = fighters
        self.harvest_share = harvest_share
        self.name = f"player:{strategy}"
        self._next_session = None
        self.log: list[dict] = []
        self.sessions = 0
        self.actions = 0
        self.fights = 0

    # -- plumbing ------------------------------------------------------------
    def note(self, sim, phase: str, what: str, detail: str = ""):
        self.log.append({"day": round(sim.clock.elapsed_days, 3),
                         "session": self.sessions, "phase": phase,
                         "what": what, "detail": detail})

    def _post(self, sim, path, payload=None):
        self.actions += 1
        r = sim.client.post(path, json=payload or {})
        try:
            return r.status_code, r.get_json()
        except Exception:
            return r.status_code, {}

    def _get(self, sim, path):
        r = sim.client.get(path)
        return r.get_json() or {}

    def _budget(self) -> bool:
        return self.actions - self._session_start_actions < self.actions_per_session

    def _combat_budget(self) -> bool:
        spent = self.actions - self._combat_start_actions
        return self._budget() and spent < self.actions_per_session * self.combat_share

    # -- roles ---------------------------------------------------------------
    def _roster(self, sim):
        return sorted(sim.db.list_daemons(), key=lambda d: -d.power())

    def _busy(self, sim, d):
        return (sim.db.get_expedition(d.id) or sim.db.get_harvest(d.id)
                or sim.db.get_training(d.id))

    def _party(self, sim):
        """Top N daemons that are free to fight."""
        return [d for d in self._roster(sim) if not self._busy(sim, d)
                ][:self.fighters]

    # -- the session ---------------------------------------------------------
    def act(self, sim):
        now = sim.clock.now
        if self._next_session is None:
            self._next_session = now
        if now < self._next_session:
            return
        self._next_session = now + 86400.0 / self.sessions_per_day
        self.sessions += 1
        self._session_start_actions = self.actions
        r = self._roster(sim)
        self.note(sim, "session", f"check-in #{self.sessions}",
                  f"roster={len(r)} party_pw={sum(d.power() for d in r[:3])} "
                  f"bits={sim.db.res_all().get('bits', 0):.0f}")

        self.do_care(sim)
        self.do_incursions(sim)
        self.do_combat(sim)
        self.do_capture(sim)
        self.do_hatch(sim)
        self.do_build(sim)
        self.do_assign(sim)
        self.do_overclock(sim)
        self.do_expeditions(sim)

    # -- 1. keep everyone alive ---------------------------------------------
    def do_care(self, sim):
        for d in sim.db.list_daemons():
            if not self._budget():
                return
            for meter, action, floor in (("hunger", "feed", 55),
                                         ("energy", "rest", 45),
                                         ("happiness", "play", 45)):
                if d.care[meter] < floor:
                    self._post(sim, f"/api/daemon/{d.id}/care", {"action": action})
            if d.care["corruption"] > 45:
                self._post(sim, f"/api/daemon/{d.id}/care", {"action": "cleanse"})

    # -- 2. the Null waits for no one ---------------------------------------
    def do_incursions(self, sim):
        for inc in sim.db.list_incursions():
            if not self._budget():
                return
            party = self._party(sim)
            # harvesters may defend where they stand, so top them up
            extra = [d for d in self._roster(sim)
                     if sim.db.get_harvest(d.id)][:max(0, 3 - len(party))]
            ids = [d.id for d in (party + extra)][:3]
            if ids:
                self._post(sim, "/api/incursion/garrison",
                           {"mac": inc["mac"], "daemon_ids": ids})
                self.note(sim, "war", f"garrison {len(ids)} defenders",
                          inc["mac"][-8:])

    # -- 3. push the frontier ------------------------------------------------
    def do_combat(self, sim):
        self._combat_start_actions = self.actions
        for dev in sim.db.list_devices():
            mac = dev["mac"]
            rift = sim.world.generate_rift(mac)
            for _ in range(len(rift["nodes"])):
                if not self._combat_budget():
                    return
                prog = sim.db.get_progress(mac)
                node = prog["cleared"]
                if node >= len(rift["nodes"]):
                    break
                party = self._party(sim)
                if not party:
                    return
                odds = battle_odds(sim, party, mac, node)
                if odds < self.attempt_threshold:
                    self.note(sim, "combat", f"skip {dev['hostname'][:14]} n{node}",
                              f"odds={odds:.0%} < {self.attempt_threshold:.0%}")
                    break          # genuinely out of reach; come back stronger

                # Each attempt re-seeds the fight, so a losing roll isn't a
                # verdict — it's a re-roll. Players grind these. Budget the
                # retries against the odds, and stop when the party is spent.
                tries = 1 if odds >= 0.9 else min(self.max_retries,
                                                  int(1.5 / max(odds, 0.05)))
                won = False
                for _try in range(tries):
                    if not self._combat_budget():
                        return
                    party = self._party(sim)
                    if any(d.care["energy"] < 25 for d in party):
                        for d in party:
                            self._post(sim, f"/api/daemon/{d.id}/care",
                                       {"action": "rest"})
                        party = self._party(sim)
                        if any(d.care["energy"] < 25 for d in party):
                            self.note(sim, "combat", "abort: party exhausted",
                                      f"{dev['hostname'][:14]} n{node}")
                            return          # too tired; next session
                    st, res = self._post(sim, "/api/battle", {
                        "daemon_ids": [d.id for d in party],
                        "mac": mac, "node_index": node})
                    self.fights += 1
                    if st == 200 and res.get("won"):
                        won = True
                        break
                self.note(sim, "combat",
                          f"{'CLEARED' if won else 'failed'} "
                          f"{dev['hostname'][:14]} n{node}",
                          f"odds={odds:.0%} tries={tries} party="
                          f"{'/'.join(d.name[:6] for d in party)}")
                if not won:
                    break

    # -- 4. free daemons are wasted daemons ---------------------------------
    def do_capture(self, sim):
        for dev in sim.db.list_devices():
            if len(sim.db.list_daemons()) >= self.max_roster or not self._budget():
                return
            prog = sim.db.get_progress(dev["mac"])
            if prog["boss_down"] and not sim.ticker.dormancy(dev["mac"]):
                self._post(sim, "/api/capture", {"mac": dev["mac"]})

    def do_assign(self, sim):
        """Spare daemons harvest or train, per strategy."""
        roster = self._roster(sim)
        # With a small roster there is no such thing as a reserved fighter —
        # your one daemon has to earn its own egg money.
        pool = roster if len(roster) <= self.fighters else roster[self.fighters:]
        spare = [d for d in pool if not self._busy(sim, d)]
        if not spare:
            return
        n_harvest = round(len(spare) * self.harvest_share)
        # harvest: fill cleared nodes on the deepest progressed rifts first
        open_nodes = []
        for dev in sim.db.list_devices():
            mac = dev["mac"]
            prog = sim.db.get_progress(mac)
            taken = {h["node_index"] for h in sim.db.list_harvests(mac)}
            for i in range(prog["cleared"]):
                if i not in taken:
                    open_nodes.append((prog["tier"], i, mac))
        open_nodes.sort(reverse=True)
        for d in spare[:n_harvest]:
            if not open_nodes or not self._budget():
                break
            _, idx, mac = open_nodes.pop(0)
            self._post(sim, "/api/harvest",
                       {"daemon_id": d.id, "mac": mac, "node_index": idx})
            self.note(sim, "assign", f"{d.name[:8]} -> harvest n{idx}", mac[-8:])
        # train: park the rest in whichever hall has a free slot
        for d in spare[n_harvest:]:
            if not self._budget():
                return
            for hall in self.build_order:
                if hall not in sim.bastion.HALLS:
                    continue
                lvl = sim.db.facility_level(hall)
                if lvl and len(sim.db.list_training(hall)) < sim.bastion.hall_slots(lvl):
                    self._post(sim, "/api/bastion/train",
                               {"daemon_id": d.id, "hall": hall})
                    self.note(sim, "assign", f"{d.name[:8]} -> {hall}")
                    break

    # -- 5. spend ------------------------------------------------------------
    def do_build(self, sim):
        """Buy down the priority list while anything is affordable, converting
        surplus at the Crucible when a specific resource is what's blocking."""
        for _ in range(10):
            if not self._budget():
                return
            snap = self._get(sim, "/api/bastion").get("facilities", {})
            wallet = sim.db.res_all()
            bought = False
            for key in self.build_order:
                f = snap.get(key)
                if not f:
                    continue
                short = {k: v - wallet.get(k, 0)
                         for k, v in f["next_cost"].items()
                         if wallet.get(k, 0) < v}
                if not short:
                    st, _ = self._post(sim, "/api/bastion/upgrade", {"key": key})
                    bought = st == 200
                    if bought:
                        self.note(sim, "build", f"{key} -> L{f['level']+1}",
                                  " + ".join(f"{v:.0f} {k}" for k, v in
                                             f["next_cost"].items()))
                    break
                if self.use_crucible and self._cover_shortfall(sim, short, wallet):
                    bought = True
                    break
            if not bought:
                return

    def _cover_shortfall(self, sim, short: dict, wallet: dict) -> bool:
        """Try to buy our way out of a specific starved resource — but never
        strip-mine the treasury to do it. Conversion is a top-up, not a
        strategy: keep a working balance for eggs and ordinary upgrades."""
        bits = wallet.get("bits", 0)
        reserve = max(300.0, bits * self.crucible_reserve)
        budget = bits - reserve
        if budget <= 0:
            return False
        richest = max((k for k in wallet if k.startswith("essence.")),
                      key=lambda k: wallet[k], default=None)
        for res, missing in short.items():
            if res == "bits":
                return False                      # nothing converts into Bits
            if res == "cores":
                if not richest:
                    return False
                n = max(1, round(missing))
                cost = sim.economy.RECLAIM_BITS * n
                if cost > budget or wallet[richest] < sim.economy.RECLAIM_ESSENCE * n:
                    return False
                st, r = self._post(sim, "/api/crucible/reclaim",
                                   {"essence": richest.split(".")[1], "count": n})
                if st == 200 and r.get("ok"):
                    self.note(sim, "crucible", f"reclaim {n} cores",
                              f"from {richest.split('.')[1]}")
                    return True
                return False
            if res.startswith("essence."):
                want = res.split(".")[1]
                if not richest or richest == res:
                    return False
                amt = max(1, round(missing))
                if amt * sim.economy.TRANSMUTE_BITS_PER > budget:
                    return False
                if wallet[richest] < amt / max(sim.economy.TRANSMUTE_RATIO, .01):
                    return False
                st, r = self._post(sim, "/api/crucible/transmute",
                                   {"from": richest.split(".")[1], "to": want,
                                    "amount": amt})
                if st == 200 and r.get("ok"):
                    self.note(sim, "crucible", f"transmute -> {amt:.0f} {want}",
                              f"from {richest.split('.')[1]}")
                    return True
                return False
        return False

    def do_hatch(self, sim):
        if len(sim.db.list_daemons()) + len(sim.db.list_eggs()) >= self.max_roster:
            return
        h = self._get(sim, "/api/hatchery")
        wallet = sim.db.res_all()
        # buy the egg whose essence we're richest in
        best, best_left = None, -1
        for kind, cost in (h.get("next_cost") or {}).items():
            if all(wallet.get(k, 0) >= v for k, v in cost.items()):
                left = wallet.get(f"essence.{kind}", 0) - cost[f"essence.{kind}"]
                if left > best_left:
                    best, best_left = kind, left
        if best and self._budget():
            st, _ = self._post(sim, "/api/hatchery/synthesize", {"essence": best})
            if st == 200:
                self.note(sim, "hatch", f"egg: {best}",
                          f"roster={len(sim.db.list_daemons())}")

    # -- 6. the loop ---------------------------------------------------------
    def do_overclock(self, sim):
        for dev in sim.db.list_devices():
            if not self._budget():
                return
            mac = dev["mac"]
            rift = sim.world.generate_rift(mac)
            prog = sim.db.get_progress(mac)
            if prog["cleared"] < len(rift["nodes"]) or not prog["boss_down"]:
                continue
            # only push the tier if we could still handle the boss comfortably
            if battle_odds(sim, self._party(sim), mac, len(rift["nodes"]) - 1) > 0.85:
                self._post(sim, "/api/overclock", {"mac": mac})
                self.note(sim, "overclock", f"{dev['hostname'][:14]} -> T{prog['tier']+1}")

    def do_expeditions(self, sim):
        """Hands-off progress between sessions."""
        if not self.use_expeditions:
            return
        free = [d for d in self._roster(sim) if not self._busy(sim, d)]
        if len(free) <= self.fighters:
            return
        for dev in sim.db.list_devices():
            if not self._budget():
                return
            mac = dev["mac"]
            prog = sim.db.get_progress(mac)
            rift = sim.world.generate_rift(mac)
            if prog["cleared"] >= len(rift["nodes"]):
                continue
            if any(e["mac"] == mac for e in sim.db.list_expeditions()):
                continue
            d = free[-1]
            if battle_odds(sim, [d], mac, prog["cleared"]) > 0.6:
                self._post(sim, "/api/expedition",
                           {"daemon_id": d.id, "mac": mac})
                return
