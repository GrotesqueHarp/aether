"""
ticker.py — The world's heartbeat.

A single background thread that makes AETHER feel alive while nobody's looking:

  1. Care drift   — daemons get hungry/tired/corrupted in real time; neglect
                    gets flagged in the journal before it turns into a Virus
                    evolution you didn't want.
  2. Presence     — periodically re-reads the ARP table (cheap, no sweep). A
                    device that leaves the network sends its rift *dormant*:
                    the journal notes it "going dark", enemies inside grow
                    stronger (and pay more XP), and its signature daemon can't
                    be captured until the device returns.
  3. Expeditions  — dispatched daemons fight through their assigned rift one
                    node at a time on a slow clock, resting when exhausted,
                    reporting every victory/rout to the journal.

Every interval is env-tunable so you can speed the world up for testing:
  AETHER_TICK, AETHER_PRESENCE_EVERY, AETHER_PRESENCE_GRACE, AETHER_FIGHT_EVERY
"""

from __future__ import annotations

import os
import threading
import time

from . import db, scan
from .daemon import Daemon
from .world import generate_rift, world_name
from .battle import simulate

TICK = float(os.environ.get("AETHER_TICK", "30"))
PRESENCE_EVERY = float(os.environ.get("AETHER_PRESENCE_EVERY", "180"))
PRESENCE_GRACE = float(os.environ.get("AETHER_PRESENCE_GRACE", "600"))
FIGHT_EVERY = float(os.environ.get("AETHER_FIGHT_EVERY", "150"))

DRIFT_PER_HOUR = {"hunger": -14, "energy": -10, "happiness": -6,
                  "discipline": -3, "corruption": +4}

# Energy is the meter that gates fighting, and it was the only one with no
# automation — it drained flat out at -10/h whether or not the daemon was doing
# anything, so the only way to keep a party combat-ready was clicking Rest
# around the clock. Now a daemon that isn't posted to a job recovers on its
# own; working daemons still burn it, just slowly. Idling is how you recover.
ENERGY_REGEN = float(os.environ.get("AETHER_ENERGY_REGEN", "9"))    # idle, /hr
ENERGY_WORK_DRAIN = float(os.environ.get("AETHER_ENERGY_WORK", "-3.5"))  # posted

# journal warning cooldowns: (daemon_id, kind) -> last ts
_warned: dict[tuple, float] = {}
WARN_COOLDOWN = 2 * 3600


# --------------------------------------------------------------------------
def dormancy(mac: str) -> bool:
    """Is this rift's device currently off the network? Unknown MACs count as
    awake so manually-added rifts are playable."""
    dev = db.get_device(mac)
    return bool(dev) and not dev["online"]


def dormant_enemy(enemy: Daemon) -> Daemon:
    """Dormant rifts drift toward Umbra: tougher, stranger enemies."""
    enemy.level += 3
    if enemy.element != "Umbra":
        enemy.element = "Umbra"
    return enemy


DORMANT_XP_MULT = 1.35


# --------------------------------------------------------------------------
def apply_drift(now: float | None = None):
    """Advance care meters for elapsed real time. Idempotent per elapsed span.
    Bastion automations soften the drift — that's the point of building them."""
    from . import bastion
    now = now or time.time()
    last = float(db.get_meta("last_tick", "0") or 0)
    if last == 0:
        db.set_meta("last_tick", str(now))
        return
    hours = (now - last) / 3600.0
    if hours < 0.002:
        return
    hunger_mult = bastion.hunger_drift_mult()
    hap_floor = bastion.happiness_floor()
    corr_drain = bastion.corruption_drain_per_hour()
    for d in db.list_daemons():
        working = bool(db.get_harvest(d.id) or db.get_training(d.id)
                       or db.get_expedition(d.id))
        for k, per in DRIFT_PER_HOUR.items():
            if k == "energy":
                rate = ENERGY_WORK_DRAIN if working else ENERGY_REGEN
            else:
                rate = per * (hunger_mult if k == "hunger" else 1.0)
            d.care[k] = max(0, min(100, d.care[k] + rate * hours))
        if corr_drain:
            d.care["corruption"] = max(0, d.care["corruption"] - corr_drain * hours)
        if hap_floor:
            d.care["happiness"] = max(d.care["happiness"], hap_floor)
        db.save_daemon(d)
        _maybe_warn(d, now)
    db.set_meta("last_tick", str(now))


def _maybe_warn(d: Daemon, now: float):
    checks = [
        ("hunger", d.care["hunger"] < 18, f"{d.name} is starving in the Nest."),
        ("corrupt", d.care["corruption"] > 70,
         f"Corruption is taking hold of {d.name} — cleanse it soon."),
        ("energy", d.care["energy"] < 10, f"{d.name} is exhausted."),
    ]
    for kind, cond, text in checks:
        key = (d.id, kind)
        if cond and now - _warned.get(key, 0) > WARN_COOLDOWN:
            db.add_event("care_warn", text, daemon_id=d.id)
            _warned[key] = now


# --------------------------------------------------------------------------
def check_presence(now: float | None = None):
    """Cheap ARP read; flip devices online/offline and journal the transitions."""
    now = now or time.time()
    try:
        live = {d["mac"] for d in scan.read_arp_table()}
    except Exception:
        return
    for dev in db.list_devices():
        mac = dev["mac"]
        if mac in live:
            if not dev["online"]:
                db.add_event("presence_wake",
                             f"{dev['hostname'] or mac} is back online — "
                             f"{world_name(mac)} brightens.", mac=mac)
            db.touch_device(mac)
        else:
            if dev["online"] and now - dev["last_seen"] > PRESENCE_GRACE:
                db.set_device_online(mac, False)
                db.add_event("presence_dark",
                             f"{dev['hostname'] or mac} went dark — "
                             f"{world_name(mac)} grows dim. Its daemons drift "
                             f"toward Umbra.", mac=mac)


# --------------------------------------------------------------------------
def tick_expeditions(now: float | None = None):
    now = now or time.time()
    for ex in db.list_expeditions(active_only=True):
        if now - ex["last_tick"] < FIGHT_EVERY:
            continue
        d = db.get_daemon(ex["daemon_id"])
        if not d:
            db.end_expedition(ex["daemon_id"])
            continue
        _expedition_step(d, ex, now)


def _expedition_step(d: Daemon, ex: dict, now: float):
    mac = ex["mac"]
    db.update_expedition(d.id, last_tick=now)

    # exhausted? rest this tick instead of fighting
    if d.care["energy"] < 15:
        d.care["energy"] = min(100, d.care["energy"] + 14)
        db.save_daemon(d)
        return

    rift = generate_rift(mac)
    prog = db.get_progress(mac)
    if prog["cleared"] >= len(rift["nodes"]):
        db.end_expedition(d.id)
        db.add_event("exped_done",
                     f"{d.name} returns from {rift['world_name']} — every node "
                     f"cleared. It looks proud of itself.", mac=mac, daemon_id=d.id)
        return

    node = rift["nodes"][prog["cleared"]]
    enemy = Daemon.from_dict(node["enemy"])
    dim = dormancy(mac)
    if dim:
        enemy = dormant_enemy(enemy)

    res = simulate(d, enemy, seed_extra=f"exped:{mac}:{node['index']}:{ex['fights']}")
    db.update_expedition(d.id, fights=ex["fights"] + 1)

    if res["winner"] == "a":
        xp = int(node["reward_xp"] * 0.8 * (DORMANT_XP_MULT if dim else 1.0))
        ev = d.gain_xp(xp)
        d.wins += 1
        d.care["energy"] = max(0, d.care["energy"] - 12)
        boss = node["is_boss"]
        db.set_progress(mac, prog["cleared"] + 1, prog["boss_down"] or boss)
        lvl_txt = f" It reached Lv{d.level}!" if ev["levels"] else ""
        if boss:
            db.add_event("exped_boss",
                         f"{d.name} defeated {enemy.name} — {rift['world_name']} "
                         f"is stabilized. (+{xp} XP){lvl_txt}", mac=mac, daemon_id=d.id)
        else:
            db.add_event("exped_win",
                         f"{d.name} cleared node {node['index'] + 1} of "
                         f"{rift['world_name']}, defeating {enemy.name}. "
                         f"(+{xp} XP){lvl_txt}"
                         + (" [dormant rift bonus]" if dim else ""),
                         mac=mac, daemon_id=d.id)
    else:
        d.losses += 1
        d.care["happiness"] = max(0, d.care["happiness"] - 8)
        d.care["energy"] = max(0, d.care["energy"] - 15)
        db.end_expedition(d.id)
        db.add_event("exped_routed",
                     f"{d.name} was routed by {enemy.name} in {rift['world_name']} "
                     f"and limps home to the Nest.", mac=mac, daemon_id=d.id)
    db.save_daemon(d)


# --------------------------------------------------------------------------
def tick_harvests(now: float | None = None):
    """Continuously accrue resources for every assigned harvester."""
    from . import economy
    now = now or time.time()
    for h in db.list_harvests():
        d = db.get_daemon(h["daemon_id"])
        if not d:
            db.end_harvest(h["daemon_id"])
            continue
        try:
            rift = generate_rift(h["mac"])
        except ValueError:
            db.end_harvest(h["daemon_id"])
            continue
        # if the world was somehow un-cleared past this node, eject gracefully
        if db.get_progress(h["mac"])["cleared"] <= h["node_index"]:
            db.end_harvest(h["daemon_id"])
            db.add_event("harvest_ejected",
                         f"{d.name} was pushed off its harvest node in "
                         f"{rift['world_name']}.", mac=h["mac"], daemon_id=d.id)
            continue
        economy.accrue_harvest(d, rift, h, dormancy(h["mac"]), now)


def tick_eggs(now: float | None = None):
    from . import economy
    now = now or time.time()
    for egg in db.list_eggs(incubating_only=True):
        if egg["hatch_at"] > now:
            continue
        d = economy.hatch(egg)
        db.add_daemon(d)
        db.hatch_egg_row(egg["id"])
        db.add_event("hatch",
                     f"An egg cracked open in the Nest — {d.name} "
                     f"({d.element}, {'★' * d.rarity}) emerges.",
                     daemon_id=d.id)


# --------------------------------------------------------------------------
_started = False


def start():
    global _started
    if _started:
        return
    _started = True
    t = threading.Thread(target=_run, daemon=True, name="aether-ticker")
    t.start()


def _run():
    last_presence = 0.0
    while True:
        try:
            now = time.time()
            apply_drift(now)
            tick_expeditions(now)
            tick_harvests(now)
            tick_eggs(now)
            from . import bastion, war
            bastion.tick_training(now)
            war.tick_signal(now)
            war.tick_deadlines(now)
            if now - last_presence > PRESENCE_EVERY:
                check_presence(now)
                last_presence = now
        except Exception:  # noqa: BLE001 — the heartbeat must never die
            pass
        time.sleep(TICK)
