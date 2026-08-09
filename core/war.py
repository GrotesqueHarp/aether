"""
war.py — Overclocking and the Null.

Overclock: a fully stabilized rift can be pushed to Tier+1 — same seeded
world, everything reset to unconquered, enemies ×1.6^tier stats, all yields
×2^tier. The infinite loop.

The Null: harvesting a stabilized world builds SIGNAL. At threshold, an
Incursion spawns with a forgiving real-time deadline (12–24h). Garrison
defenders (they can keep harvesting while on guard) or repel it early
yourself. Hold: Cores + Aethercite, Ward+1 (permanently better yields,
angrier Null). Fall: the world reverts to unconquered at its current tier,
wards shatter, harvesters limp home. Nothing dies; conquest just resumes.
"""

from __future__ import annotations

import os
import time

from . import db, content
from .daemon import Daemon, generate_daemon
from .seed import Rng, _digest
from .battle import simulate_team

SIGNAL_RATE = float(os.environ.get("AETHER_SIGNAL_RATE", "1.0"))
SIGNAL_THRESHOLD = 24.0          # harvester-hours (scaled) to draw the Null
INCURSION_MIN_H = float(os.environ.get("AETHER_INCURSION_MIN_H", "12"))
INCURSION_MAX_H = float(os.environ.get("AETHER_INCURSION_MAX_H", "24"))

TIER_STAT_MULT = 1.6             # enemy base-stat multiplier per tier
TIER_YIELD_MULT = 2.0            # loot & harvest multiplier per tier
TIER_XP_MULT = 1.5
WARD_YIELD_BONUS = 0.10          # +10% yields per ward


# ------------------------------------------------------------- overclock ----
def tier_mults(progress: dict) -> dict:
    t, w = progress.get("tier", 0), progress.get("ward", 0)
    return {"stats": TIER_STAT_MULT ** t,
            "yields": (TIER_YIELD_MULT ** t) * (1 + WARD_YIELD_BONUS * w),
            "xp": TIER_XP_MULT ** t}


def scale_enemy(enemy: Daemon, progress: dict) -> Daemon:
    t = progress.get("tier", 0)
    if t > 0:
        m = TIER_STAT_MULT ** t
        for k in enemy.base_stats:
            enemy.base_stats[k] = int(enemy.base_stats[k] * m)
        for k in enemy.growth:
            enemy.growth[k] = round(enemy.growth[k] * m, 2)
        enemy.level += t * 5
    return enemy


OVERCLOCK_CORES = float(os.environ.get("AETHER_OVERCLOCK_CORES", "3"))


def overclock_cost(tier: int) -> dict:
    """Pushing a tier costs Cores, and costs more the deeper you go. Free
    overclocking was a trap: it looks like pure progress, so you take it on
    every rift at once and wake up with nothing but Tier-1 bosses to fight."""
    return {"cores": round(OVERCLOCK_CORES * (1 + tier), 1)} if OVERCLOCK_CORES else {}


def next_tier_boss_power(mac: str, tier_delta: int = 1) -> int:
    """What the final Gatekeeper would hit like one tier up — so the UI can
    warn before you commit, instead of after."""
    from .world import layer_enemies, LAYERS
    prog = db.get_progress(mac)
    foes = layer_enemies(mac, LAYERS, prog["tier"] + tier_delta)
    return sum(f.power() for f in foes)


def overclock(mac: str, n_nodes: int) -> dict:
    prog = db.get_progress(mac)
    if prog["cleared"] < n_nodes or not prog["boss_down"]:
        return {"ok": False, "reason": "not_fully_cleared"}
    cost = overclock_cost(prog["tier"])
    if cost and not db.res_spend(cost):
        return {"ok": False, "reason": "cant_afford", "cost": cost}
    # eject harvesters — the world is about to reset under them
    for h in db.list_harvests(mac):
        d = db.get_daemon(h["daemon_id"])
        db.end_harvest(h["daemon_id"])
        if d:
            db.add_event("harvest_ejected",
                         f"{d.name} withdraws as the rift begins to overclock.",
                         mac=mac, daemon_id=d.id)
    db.end_incursion(mac)
    db.set_progress_fields(mac, cleared=0, boss_down=0,
                           tier=prog["tier"] + 1, signal=0.0)
    return {"ok": True, "tier": prog["tier"] + 1, "cost": cost}


def downclock(mac: str) -> dict:
    """Step a rift back down a tier. Overclocking is irreversible in most idle
    games and that's exactly what makes it a trap — push every rift too far and
    there is no content left you can beat. Here you can always retreat: the
    rift reboots one tier lower and you reconquer it. Cores are not refunded,
    so it still stings."""
    prog = db.get_progress(mac)
    if prog["tier"] <= 0:
        return {"ok": False, "reason": "already_base"}
    for h in db.list_harvests(mac):
        d = db.get_daemon(h["daemon_id"])
        db.end_harvest(h["daemon_id"])
        if d:
            db.add_event("harvest_ejected",
                         f"{d.name} withdraws as the rift powers down.",
                         mac=mac, daemon_id=d.id)
    db.end_incursion(mac)
    db.set_progress_fields(mac, cleared=0, boss_down=0,
                           tier=prog["tier"] - 1, signal=0.0)
    return {"ok": True, "tier": prog["tier"] - 1}


# ------------------------------------------------------------ null squads ---
def boss_minions(main_enemy: Daemon, rift: dict, progress: dict) -> list[Daemon]:
    """Tier 1+ bosses bring backup — parties become necessary, not optional."""
    t = progress.get("tier", 0)
    n = min(2, t)
    out = []
    for i in range(n):
        r = Rng(_digest(main_enemy.seed, "minion", str(i)))
        m = generate_daemon(r, origin_mac=rift["mac"],
                            favored_elements=rift["biome"]["elements"],
                            stage="Rookie")
        m.level = max(1, main_enemy.level - 6)
        m = scale_enemy(m, {"tier": max(0, t - 1)})
        out.append(m)
    return out


def null_squad(mac: str, incursion: dict, progress: dict,
               depth: int) -> list[Daemon]:
    """The invaders: umbra-drenched, seeded by the incursion itself."""
    t, w = progress.get("tier", 0), progress.get("ward", 0)
    n = max(1, min(3, 1 + (t + w) // 2))
    out = []
    for i in range(n):
        r = Rng(_digest("aether.null", mac, str(incursion["spawned"]), str(i)))
        d = generate_daemon(r, origin_mac=mac, min_rarity=2, stage="Champion")
        d.element = "Umbra"
        d.attribute = "Virus"
        d.level = depth + 8 + t * 5 + w * 2
        d.name = r.choice(["Static", "Hollow", "Sever", "Drown", "Numb",
                           "Wither", "Erase"]) + r.choice(
                           ["maw", "wraith", "shade", "chorus", "tide"])
        out.append(d)
    return out


# ----------------------------------------------------------- signal/spawn ---
def tick_signal(now: float | None = None):
    """Harvesting stabilized worlds draws the Null. Called from the ticker."""
    from .world import generate_rift
    now = now or time.time()
    last = float(db.get_meta("signal_tick", "0") or 0)
    db.set_meta("signal_tick", str(now))
    if last == 0:
        return
    hours = (now - last) / 3600.0
    by_mac: dict[str, int] = {}
    for h in db.list_harvests():
        by_mac[h["mac"]] = by_mac.get(h["mac"], 0) + 1
    for mac, n in by_mac.items():
        prog = db.get_progress(mac)
        if not prog["boss_down"] or db.get_incursion(mac):
            continue
        gain = n * (1 + prog["tier"] * 0.6) * hours * SIGNAL_RATE
        signal = prog["signal"] + gain
        if signal >= SIGNAL_THRESHOLD:
            _spawn_incursion(mac, prog, now)
            db.set_progress_fields(mac, signal=0.0)
        else:
            db.set_progress_fields(mac, signal=signal)


def _spawn_incursion(mac: str, prog: dict, now: float):
    from .world import generate_rift
    rift = generate_rift(mac)
    r = Rng(_digest("aether.incursion", mac, str(int(now))))
    hours = INCURSION_MIN_H + r.random() * (INCURSION_MAX_H - INCURSION_MIN_H)
    strength = rift["depth"] * (1 + prog["tier"] * 1.2) * (1 + prog["ward"] * 0.35)
    db.spawn_incursion(mac, now + hours * 3600, strength)
    db.add_event("incursion_spawn",
                 f"The Null has noticed {rift['world_name']} — static gathers "
                 f"at its edges. {int(hours)}h to prepare a defense.",
                 mac=mac)


# ------------------------------------------------------------- resolution ---
def resolve_incursion(mac: str, defenders: list[Daemon],
                      manual: bool = False) -> dict:
    """Fight the Null. Used both for early repels and deadline auto-battles."""
    from .world import generate_rift
    from . import bastion
    inc = db.get_incursion(mac)
    if not inc:
        return {"ok": False, "reason": "no_incursion"}
    rift = generate_rift(mac)
    prog = db.get_progress(mac)
    nulls = null_squad(mac, inc, prog, rift["depth"])

    if not defenders:
        return _world_falls(mac, rift, prog, None, nulls)

    # the Aegis empowers defenders (clone so buffs don't persist)
    boosted = []
    aegis = bastion.aegis_power_mult()
    for d in defenders:
        c = Daemon.from_dict(d.to_dict())
        c.id = d.id
        if aegis > 1:
            for k in c.base_stats:
                c.base_stats[k] = int(c.base_stats[k] * aegis)
        boosted.append(c)

    result = simulate_team(boosted, nulls,
                           seed_extra=f"incursion:{inc['spawned']}")
    if result["winner"] == "a":
        return _defense_holds(mac, rift, prog, defenders, nulls, result, manual)
    return _world_falls(mac, rift, prog, defenders, nulls, result)


def _defense_holds(mac, rift, prog, defenders, nulls, result, manual):
    cores = 3.0 + prog["tier"]
    aethercite = 1.0 + prog["ward"] // 2
    db.res_add("cores", cores)
    db.res_add("aethercite", aethercite)
    xp_each = int(40 * (1 + prog["tier"] * 0.5))
    for d in defenders:
        live = db.get_daemon(d.id)
        if live:
            live.gain_xp(xp_each)
            live.wins += 1
            db.save_daemon(live)
    db.set_progress_fields(mac, ward=prog["ward"] + 1)
    db.end_incursion(mac)
    names = ", ".join(d.name for d in defenders)
    db.add_event("incursion_win",
                 f"{names} {'repelled' if manual else 'held the line against'} "
                 f"the Null at {rift['world_name']} — Ward {prog['ward'] + 1} "
                 f"raised. (+{cores:g} Cores, +{aethercite:g} Aethercite)",
                 mac=mac)
    return {"ok": True, "won": True, "battle": result,
            "nulls": [n.to_dict() for n in nulls],
            "reward": {"cores": cores, "aethercite": aethercite,
                       "ward": prog["ward"] + 1, "xp_each": xp_each}}


def _world_falls(mac, rift, prog, defenders, nulls, result=None):
    for h in db.list_harvests(mac):
        d = db.get_daemon(h["daemon_id"])
        db.end_harvest(h["daemon_id"])
        if d:
            d.care["happiness"] = max(0, d.care["happiness"] - 10)
            db.save_daemon(d)
    if defenders:
        for d in defenders:
            live = db.get_daemon(d.id)
            if live:
                live.losses += 1
                live.care["happiness"] = max(0, live.care["happiness"] - 8)
                db.save_daemon(live)
    db.set_progress_fields(mac, cleared=0, boss_down=0, ward=0, signal=0.0)
    db.end_incursion(mac)
    db.add_event("incursion_fall",
                 f"{rift['world_name']} has fallen to the Null"
                 + (" — the garrison was overwhelmed" if defenders else
                    " — no one stood against it")
                 + f". Its wards shatter; the rift must be reconquered"
                 f"{f' (Tier {prog['tier']} holds)' if prog['tier'] else ''}.",
                 mac=mac)
    return {"ok": True, "won": False,
            "battle": result, "nulls": [n.to_dict() for n in nulls],
            "reward": None}


def tick_deadlines(now: float | None = None):
    """Deadline hits: garrison fights, or the world falls undefended."""
    now = now or time.time()
    for inc in db.list_incursions():
        if inc["deadline"] > now:
            continue
        defenders = []
        for sid in (inc["garrison"] or "").split(","):
            if not sid:
                continue
            d = db.get_daemon(int(sid))
            if d and not db.get_expedition(d.id) and not db.get_training(d.id):
                defenders.append(d)
        resolve_incursion(inc["mac"], defenders[:3])
