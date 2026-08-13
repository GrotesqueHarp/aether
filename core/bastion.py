"""
bastion.py — Base building on your Anchor device.

Nine facilities in four families:

  Training halls  the Forge (ATK) / Bulwark (DEF) / Circuit (SPD) / Core
                  Chamber (HP). Slot a daemon in and it gains permanent base
                  stat points over real hours — this is what "automates away"
                  click-training. Slots and rates grow with level.
  Support         Hatchery Wing (faster incubation).
  Automations     Auto-Feeder / Playroom / Cleansing Font — they buy back your
                  attention by softening the care drift.
  War             the Aegis — empowers defenders during Null incursions.

Costs follow the incremental curve (base × 1.55^level) in Bits + a themed
essence, with Cores joining the bill from level 5 up, so there is always a
next purchase and Cores finally have a sink.
"""

from __future__ import annotations

import os
import time

from . import db
from .daemon import Daemon, STAT_KEYS

TRAIN_MULT = float(os.environ.get("AETHER_TRAIN_MULT", "1.0"))

FACILITIES = {
    "forge": {
        "name": "The Forge", "kind": "hall", "stat": "atk", "essence": "ferro",
        "desc": "Hammer-song and sparks. Daemons here gain ATK over time.",
        "base_bits": 200,
    },
    "bulwark": {
        "name": "The Bulwark", "kind": "hall", "stat": "def", "essence": "loam",
        "desc": "Weight training against packed-earth firewalls. Gains DEF.",
        "base_bits": 200,
    },
    "circuit": {
        "name": "The Circuit", "kind": "hall", "stat": "spd", "essence": "volt",
        "desc": "An endless lightning track. Gains SPD.",
        "base_bits": 200,
    },
    "core_chamber": {
        "name": "The Core Chamber", "kind": "hall", "stat": "hp", "essence": "tide",
        "desc": "Deep pressure conditioning. Gains HP.",
        "base_bits": 200,
    },
    "waystation": {
        "name": "The Waystation", "kind": "support", "essence": "volt",
        "desc": "Somewhere for expeditions to stage from. Each level lets one "
                "more party work the rifts you have already opened.",
        "base_bits": 600,
    },
    "array": {
        "name": "The Array", "kind": "support", "essence": "ferro",
        "desc": "A listening tower aimed at subspace. Each level resolves more "
                "distant rifts out of the noise — and once a rift is found it "
                "stays found.",
        "base_bits": 400,
    },
    "hatchery_wing": {
        "name": "Hatchery Wing", "kind": "support", "essence": "plasma",
        "desc": "Warm coils around the eggs. Each level incubates 6% faster.",
        "base_bits": 300,
    },
    "auto_feeder": {
        "name": "Auto-Feeder", "kind": "automation", "essence": "loam",
        "desc": "Rations on a timer. Each level slows hunger drift 12%.",
        "base_bits": 250,
    },
    "playroom": {
        "name": "Playroom", "kind": "automation", "essence": "plasma",
        "desc": "Bouncing packets and chase-loops. Sets a happiness floor.",
        "base_bits": 250,
    },
    "cleansing_font": {
        "name": "Cleansing Font", "kind": "automation", "essence": "umbra",
        "desc": "Umbra turned against itself. Passively drains corruption.",
        "base_bits": 350,
    },
    "aegis": {
        "name": "The Aegis", "kind": "war", "essence": "umbra",
        "desc": "A lattice of wards. Defenders fight 6% stronger per level "
                "during Null incursions.",
        "base_bits": 500,
    },
}
HALLS = {k: v for k, v in FACILITIES.items() if v["kind"] == "hall"}


# ----------------------------------------------------------------- levels ---
WAYSTATION_COST_GROWTH = float(os.environ.get("AETHER_WAYSTATION_GROWTH", "2.1"))


def expedition_slots() -> int:
    """How many expeditions may run at once, network-wide.

    Digging was throughput-bound rather than difficulty-bound: one expedition
    per rift meant a party 150x stronger dug no faster, and more rifts were
    gated behind layers dug — a loop feeding itself. This is the valve. Buying
    capacity is how raw power turns into progress, and it gives a years-long
    curve something to spend on that isn't another multiplier.
    """
    return 1 + db.facility_level("waystation")


ARRAY_COST_GROWTH = float(os.environ.get("AETHER_ARRAY_COST_GROWTH", "2.35"))
ARRAY_GATE_BASE = float(os.environ.get("AETHER_ARRAY_GATE_BASE", "55"))
ARRAY_GATE_POWER = float(os.environ.get("AETHER_ARRAY_GATE_POWER", "2.05"))
ARRAY_BASE_SLOTS = int(os.environ.get("AETHER_ARRAY_BASE", "3"))
ARRAY_PER_LEVEL = int(os.environ.get("AETHER_ARRAY_PER_LEVEL", "2"))


def array_capacity(level: int) -> int:
    """How many rifts you can have resolved at once."""
    return ARRAY_BASE_SLOTS + ARRAY_PER_LEVEL * level


def upgrade_cost(key: str, level: int) -> dict:
    f = FACILITIES[key]
    scale = 1.55 ** level
    if key == "array":
        # Bits-only for the first few levels: the Array is how you reach the
        # essences you don't have yet, so it must never be gated behind one.
        # After that the curve gets deliberately brutal — resolving the whole
        # sky is meant to be the work of a year, not a weekend.
        cost = {"bits": round(f["base_bits"] * (ARRAY_COST_GROWTH ** level), 1)}
        if level >= 2:
            cost["cores"] = float(round(2 * (1.45 ** (level - 2))))
        if level >= 6:
            # Aethercite only comes from holding off the Null, so the deep sky
            # opens only to someone who can defend what they already have
            cost["aethercite"] = float(level - 5)
        return cost

    if key == "waystation":
        c = {"bits": round(f["base_bits"] * (WAYSTATION_COST_GROWTH ** level), 1),
             f"essence.{f['essence']}": round(f["base_bits"] / 6
                                              * (WAYSTATION_COST_GROWTH ** level), 1)}
        if level >= 2:
            c["cores"] = float(round(3 * (1.5 ** (level - 2))))
        return c
    cost = {"bits": round(f["base_bits"] * scale, 1),
            f"essence.{f['essence']}": round(f["base_bits"] / 8 * scale, 1)}
    if level >= 4:                      # cores join the bill at level 5+
        cost["cores"] = float(level - 3)
    return cost


def array_required_layers(level: int) -> int:
    """Layers you must have dug NETWORK-WIDE before the Array will resolve
    another rift. Money alone shouldn't buy the sky — depth should."""
    if level <= 0:
        return 0
    return int(ARRAY_GATE_BASE * (level ** ARRAY_GATE_POWER))


def array_gate(level: int) -> dict | None:
    """None if the next level is unlocked, else what's still missing."""
    need = array_required_layers(level)
    have = db.total_layers_cleared()
    if have >= need:
        return None
    return {"need_layers": need, "have_layers": have}


def upgrade(key: str) -> dict:
    if key not in FACILITIES:
        return {"ok": False, "reason": "bad_facility"}
    lvl = db.facility_level(key)
    if key == "array":
        gate = array_gate(lvl)
        if gate:
            return {"ok": False, "reason": "needs_depth", **gate}
    cost = upgrade_cost(key, lvl)
    if not db.res_spend(cost):
        return {"ok": False, "reason": "cant_afford", "cost": cost}
    db.set_facility_level(key, lvl + 1)
    return {"ok": True, "level": lvl + 1, "cost": cost}


def snapshot() -> dict:
    """Everything the Bastion view needs in one payload."""
    levels = db.all_facility_levels()
    out = {}
    for key, f in FACILITIES.items():
        lvl = levels.get(key, 0)
        out[key] = {
            **{k: f[k] for k in ("name", "kind", "desc", "essence")},
            "stat": f.get("stat"),
            "level": lvl,
            "next_cost": upgrade_cost(key, lvl),
            "effect": effect_line(key, lvl),
        }
        if f["kind"] == "hall":
            out[key]["slots"] = hall_slots(lvl)
            out[key]["rate_per_hour"] = round(hall_rate(lvl), 2)
            out[key]["occupants"] = []
            for t in db.list_training(key):
                d = db.get_daemon(t["daemon_id"])
                if d:
                    out[key]["occupants"].append({
                        "daemon_id": d.id, "name": d.name,
                        "color": d.to_dict()["color"],
                        "gained": t["gained"],
                        "hours": round((time.time() - t["started"]) / 3600, 1),
                    })
    return out


def effect_line(key: str, lvl: int) -> str:
    if lvl == 0:
        return (f"not built · {array_capacity(0)} rifts resolvable"
                if key == "array" else "not built")
    f = FACILITIES[key]
    if f["kind"] == "hall":
        return (f"{hall_slots(lvl)} slot(s) · "
                f"{hall_levels_per_day(lvl):.2f} levels of {f['stat'].upper()}/day")
    if key == "array":
        gate = array_gate(lvl)
        extra = (f" · next needs {gate['need_layers']} layers dug "
                 f"({gate['have_layers']} so far)") if gate else ""
        return f"{array_capacity(lvl)} rifts resolvable{extra}"
    if key == "waystation":
        return f"{expedition_slots()} expedition(s) at once"
    if key == "hatchery_wing":
        return f"incubation ×{incubation_mult():.2f}"
    if key == "auto_feeder":
        return (f"hunger drift ×{hunger_drift_mult():.2f}, "
                f"+{feeder_restore_per_hour():.0f} hunger/h")
    if key == "playroom":
        return f"happiness floor {happiness_floor()}"
    if key == "cleansing_font":
        return f"-{corruption_drain_per_hour():.1f} corruption/h"
    if key == "aegis":
        return f"defenders +{lvl * 6}% in incursions"
    return f"level {lvl}"


# ------------------------------------------------------------ hall mechanics -
def hall_slots(lvl: int) -> int:
    return 0 if lvl == 0 else 1 + (lvl - 1) // 3


# Halls are denominated in LEVELS' WORTH of growth per day, not raw stat
# points. A stat point is roughly a quarter of a level, so granting hundreds of
# points a day meant a Lv1 daemon parked in a hall for a week hit 921 ATK while
# one that fought its way to Lv30 had 224 — level stopped describing strength
# at all. Now a hall is measured against the thing it competes with.
HALL_LEVELS_PER_DAY = float(os.environ.get("AETHER_HALL_LEVELS_PER_DAY", "0.55"))
HALL_GROWTH = float(os.environ.get("AETHER_HALL_GROWTH", "1.28"))


def hall_levels_per_day(lvl: int) -> float:
    """How many levels' worth of a stat this hall grows in a day."""
    return 0.0 if lvl == 0 else HALL_LEVELS_PER_DAY * (HALL_GROWTH ** (lvl - 1))


def hall_rate(lvl: int, daemon=None) -> float:
    """Base-stat points per hour, scaled to the daemon's own growth rate.

    Kept in points because that's what tick_training banks, but derived from
    levels so a hall is always worth a comprehensible number of levels a day
    regardless of whose stats it's growing.
    """
    if lvl == 0:
        return 0.0
    per_level = 4.0
    if daemon is not None:
        try:
            per_level = max(0.5, sum(daemon.growth.values()) / len(daemon.growth))
        except Exception:
            per_level = 4.0
    return hall_levels_per_day(lvl) * per_level / 24.0 * TRAIN_MULT


def assign(daemon_id: int, hall: str) -> dict:
    if hall not in HALLS:
        return {"ok": False, "reason": "bad_hall"}
    lvl = db.facility_level(hall)
    if lvl == 0:
        return {"ok": False, "reason": "not_built"}
    if len(db.list_training(hall)) >= hall_slots(lvl):
        return {"ok": False, "reason": "hall_full"}
    db.start_training(daemon_id, hall)
    return {"ok": True}


def tick_training(now: float | None = None):
    """Accrue fractional stat points; bank whole points into base stats.
    Training drains energy slowly; exhausted daemons rest in place."""
    now = now or time.time()
    for t in db.list_training():
        d = db.get_daemon(t["daemon_id"])
        if not d:
            db.end_training(t["daemon_id"])
            continue
        hall = HALLS.get(t["hall"])
        if not hall:
            db.end_training(t["daemon_id"])
            continue
        hours = max(0.0, (now - t["last_tick"]) / 3600.0)
        if hours <= 0:
            continue
        if d.care["energy"] < 8:                       # rest instead
            d.care["energy"] = min(100, d.care["energy"] + 8 * hours)
            db.save_daemon(d)
            db.update_training(d.id, last_tick=now)
            continue
        from . import glyph, traits
        rate = hall_rate(db.facility_level(t["hall"]), d)
        rate *= 1.0 + glyph.bonus(getattr(d, "equipped", []), "training")
        rate *= traits.mult(d, "training")
        from . import affinity
        rate *= affinity.job_mult(d, "training")
        rate *= d.training_headroom()
        banked = t["banked"] + rate * hours
        whole = int(banked)
        if whole > 0:
            d.base_stats[hall["stat"]] += whole
            d.trained[hall["stat"]] = d.trained.get(hall["stat"], 0) + whole
            d.care["discipline"] = min(100, d.care["discipline"] + whole * 0.8)
        d.care["energy"] = max(0, d.care["energy"] - 2.0 * hours)
        d.care["hunger"] = max(0, d.care["hunger"] - 1.5 * hours)
        db.save_daemon(d)
        db.update_training(d.id, last_tick=now, banked=banked - whole,
                          gained=t["gained"] + whole)


# ------------------------------------------------- automation drift effects --
def hunger_drift_mult() -> float:
    return max(0.15, 1 - 0.12 * db.facility_level("auto_feeder"))


def feeder_restore_per_hour() -> float:
    """The Auto-Feeder doesn't just slow hunger, it puts food out. Slowing a
    drain still ends at zero eventually; only restoration removes the need to
    click Feed forever. From ~L2 it outpaces the drift entirely."""
    lvl = db.facility_level("auto_feeder")
    return 0.0 if lvl == 0 else 6.0 * lvl


def happiness_floor() -> int:
    lvl = db.facility_level("playroom")
    return 0 if lvl == 0 else min(60, 22 + 3 * lvl)


def corruption_drain_per_hour() -> float:
    return 1.5 * db.facility_level("cleansing_font")


def incubation_mult() -> float:
    return max(0.2, 0.94 ** db.facility_level("hatchery_wing"))


def aegis_power_mult() -> float:
    return 1 + 0.06 * db.facility_level("aegis")
