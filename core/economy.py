"""
economy.py — Resources, harvest yields, battle loot, and the Hatchery.

Tuning philosophy (per the design brief): Melvor-style slow burn. A single
early harvester earns tens of Bits per hour; your first synthesized egg is a
day-one goal, not a minute-one one. All rates honor AETHER_ECON_MULT so tests
(and the impatient) can run the economy at any speed without touching code.

Resource kinds
  bits            universal currency, from every harvester and every clear
  essence.<kind>  biome-flavored: ferro/tide/loam/volt/umbra/plasma —
                  which DEVICE you harvest determines which essence you get
  cores           rare: boss kills + slow trickle from harvested boss nodes
"""

from __future__ import annotations

import os
import time

from . import content, db
from .daemon import Daemon, generate_daemon
from .seed import Rng, _digest

ECON_MULT = float(os.environ.get("AETHER_ECON_MULT", "1.0"))
HATCH_SECONDS = float(os.environ.get("AETHER_HATCH_SECONDS", str(8 * 3600)))

# each biome yields the essence of its signature (first-listed) element
ESSENCE_BY_BIOME = {key: content.BIOMES[key]["elements"][0].lower()
                    for key in content.BIOMES}          # foundry->ferro, ...
ESSENCE_KINDS = sorted(set(ESSENCE_BY_BIOME.values()))  # ferro/loam/plasma/tide/umbra/volt
ELEMENT_FOR_ESSENCE = {v: content.BIOMES[k]["elements"][0]
                       for k, v in ESSENCE_BY_BIOME.items()}

LOOT_MULT = float(os.environ.get("AETHER_LOOT_MULT", "1.0"))
DORMANT_RATE_MULT = 1.0   # retained for signature compatibility; presence is gone   # offline devices harvest slower...
                          # ...but yield umbra essence instead of their biome's


# --------------------------------------------------------------- harvesting --
def harvest_rates(daemon: Daemon, rift: dict, node_index: int,
                  dormant: bool, progress: dict | None = None) -> dict:
    """Per-HOUR yields for this daemon working this node. Boss nodes trickle
    cores; regular nodes yield bits + the rift's essence. Overclock tiers and
    wards multiply everything."""
    from . import war
    from .world import is_gatekeeper
    layer = max(1, node_index)
    progress = progress or db.get_progress(rift["mac"])
    # deeper layers pay far better — that's the whole reason to dig
    depth_factor = rift["depth"] + layer * 0.55
    power_factor = (daemon.power() / 150.0) ** 0.6
    mult = (ECON_MULT * (DORMANT_RATE_MULT if dormant else 1.0)
            * war.tier_mults(progress)["yields"])

    bits_hr = (6.0 + depth_factor * 3.2) * power_factor * mult
    essence_kind = "umbra" if dormant else ESSENCE_BY_BIOME[rift["biome_key"]]
    out = {"bits": bits_hr, f"essence.{essence_kind}": bits_hr / 10.0}
    if is_gatekeeper(layer):
        out["cores"] = (0.6 + rift["depth"] * 0.05) / 24.0 * mult
        out["bits"] *= 0.5
    return out


def accrue_harvest(daemon: Daemon, rift: dict, harvest: dict,
                   dormant: bool, now: float | None = None) -> dict:
    """Pay out everything earned since last_tick. Returns what was earned."""
    now = now or time.time()
    hours = max(0.0, (now - harvest["last_tick"]) / 3600.0)
    if hours <= 0:
        return {}
    rates = harvest_rates(daemon, rift, harvest["node_index"], dormant)
    earned = {k: v * hours for k, v in rates.items()}
    for kind, amt in earned.items():
        db.res_add(kind, amt)
    db.update_harvest(daemon.id, last_tick=now,
                      lifetime_bits=harvest["lifetime_bits"] + earned.get("bits", 0))
    return earned


# -------------------------------------------------------------- battle loot --
def node_loot(rift: dict, node_index: int, dormant: bool,
              progress: dict | None = None) -> dict:
    """One-time drop for clearing a node (frontier clears only)."""
    from . import war
    from .world import is_gatekeeper, layer_spec
    layer = max(1, node_index)
    progress = progress or db.get_progress(rift["mac"])
    lvl = layer_spec(rift["mac"], layer, progress.get("tier", 0))["enemy_level"]
    mult = (ECON_MULT * (1.35 if dormant else 1.0)
            * war.tier_mults(progress)["yields"])
    essence_kind = "umbra" if dormant else ESSENCE_BY_BIOME[rift["biome_key"]]
    # Clearing a layer is progress, not payday. Battle drops are a trickle to
    # get you started; the real economy is a daemon posted on a shelf pulling
    # resources in around the clock whether you're watching or not.
    loot = {"bits": round((3 + lvl * 0.7) * mult * LOOT_MULT, 1),
            f"essence.{essence_kind}": round((0.5 + lvl * 0.15) * mult * LOOT_MULT, 1)}
    if is_gatekeeper(layer):
        loot["cores"] = round(0.5 * (1 + progress.get("tier", 0) * 0.5), 1)
    return loot


def grant(loot: dict):
    for kind, amt in loot.items():
        db.res_add(kind, amt)


# ---------------------------------------------------------------- hatchery ---
def egg_cost(essence_kind: str) -> dict:
    """Cost scales with how many daemons you already command (roster + eggs),
    Cookie-Clicker style, so the Nest grows but never explodes."""
    owned = len(db.list_daemons()) + len(db.list_eggs())
    scale = 1.7 ** max(0, owned - 1)
    return {"bits": round(150 * scale, 1),
            f"essence.{essence_kind}": round(20 * scale, 1)}


def synthesize_egg(essence_kind: str) -> dict:
    from . import bastion
    if essence_kind not in ESSENCE_KINDS:
        return {"ok": False, "reason": "bad_essence"}
    cost = egg_cost(essence_kind)
    if not db.res_spend(cost):
        return {"ok": False, "reason": "cant_afford", "cost": cost}
    hatch_at = time.time() + HATCH_SECONDS * bastion.incubation_mult()
    egg_id = db.add_egg(essence_kind, hatch_at)
    return {"ok": True, "egg_id": egg_id, "hatch_at": hatch_at, "cost": cost}


def hatch(egg: dict) -> Daemon:
    """Deterministic per-egg: seeded by id + essence. The essence biases the
    element hard, and a lucky roll raises the rarity floor."""
    rng = Rng(_digest("aether.egg", str(egg["id"]), egg["essence"],
                      str(egg["created"])))
    min_rarity = 1
    roll = rng.random()
    if roll < 0.06:
        min_rarity = 3
    elif roll < 0.30:
        min_rarity = 2
    d = generate_daemon(
        rng, origin_mac="",
        favored_elements=[ELEMENT_FOR_ESSENCE[egg["essence"]]],
        min_rarity=min_rarity, stage="Hatchling")
    return d


# ------------------------------------------------------------------ selling -
# What a daemon is worth when you let it go. Rarity and stage matter far more
# than level, so a 5-star Mega is genuinely worth keeping around rather than
# grinding a common one up.
RARITY_VALUE = {1: 1.0, 2: 1.5, 3: 2.2, 4: 3.2, 5: 4.5}
STAGE_VALUE = {"Egg": 0.4, "Hatchling": 1.0, "Rookie": 1.5,
               "Champion": 2.2, "Ultimate": 3.2, "Mega": 4.5}
ELEMENT_TO_ESSENCE = {v: k for k, v in ELEMENT_FOR_ESSENCE.items()}


def sell_value(d) -> dict:
    """Bits always; its element's essence if that element has one; Cores only
    for genuinely rare, well-grown daemons."""
    mult = RARITY_VALUE.get(d.rarity, 1.0) * STAGE_VALUE.get(d.stage, 1.0)
    out = {"bits": round((60 + d.level * 18) * mult, 1)}
    ess = ELEMENT_TO_ESSENCE.get(d.element)
    if ess:
        out["essence." + ess] = round((6 + d.level * 1.5)
                                      * RARITY_VALUE.get(d.rarity, 1.0), 1)
    else:
        out["bits"] = round(out["bits"] * 1.35, 1)   # no essence? pay in Bits
    if d.rarity >= 4 and d.stage in ("Ultimate", "Mega"):
        out["cores"] = float(d.rarity - 3)
    return out


# --------------------------------------------------------------- crucible ---
# Which essences you can earn depends on what hardware you happen to own: a LAN
# with no Bazaar device can never produce Plasma, which used to make four
# facilities permanently unbuildable. The Crucible is the escape hatch — it is
# deliberately lossy, so native essence is always better, but nothing is ever
# unreachable. It also gives the Bits pile-up an actual sink.
TRANSMUTE_RATIO = float(os.environ.get("AETHER_TRANSMUTE_RATIO", "0.55"))
TRANSMUTE_BITS_PER = float(os.environ.get("AETHER_TRANSMUTE_BITS", "14"))
RECLAIM_ESSENCE = float(os.environ.get("AETHER_RECLAIM_ESSENCE", "45"))
RECLAIM_BITS = float(os.environ.get("AETHER_RECLAIM_BITS", "900"))


def transmute_cost(from_kind: str, to_kind: str, out_amount: float) -> dict:
    """What it costs to end up with `out_amount` of `to_kind`."""
    return {f"essence.{from_kind}": round(out_amount / TRANSMUTE_RATIO, 2),
            "bits": round(out_amount * TRANSMUTE_BITS_PER, 1)}


def transmute(from_kind: str, to_kind: str, out_amount: float) -> dict:
    if TRANSMUTE_RATIO <= 0:
        return {"ok": False, "reason": "disabled"}
    if from_kind == to_kind or from_kind not in ESSENCE_KINDS \
            or to_kind not in ESSENCE_KINDS:
        return {"ok": False, "reason": "bad_essence"}
    out_amount = max(1.0, float(out_amount))
    cost = transmute_cost(from_kind, to_kind, out_amount)
    if not db.res_spend(cost):
        return {"ok": False, "reason": "cant_afford", "cost": cost}
    db.res_add(f"essence.{to_kind}", out_amount)
    return {"ok": True, "gained": out_amount, "cost": cost}


def reclaim_cost(count: float = 1) -> dict:
    return {"essence": round(RECLAIM_ESSENCE * count, 1),
            "bits": round(RECLAIM_BITS * count, 1)}


def reclaim(essence_kind: str, count: float = 1) -> dict:
    """Grind essence and Bits into Cores. Cores used to come only from bosses,
    which meant failing to beat a boss locked you out of the upgrades that
    would let you beat it."""
    if RECLAIM_ESSENCE <= 0:
        return {"ok": False, "reason": "disabled"}
    if essence_kind not in ESSENCE_KINDS:
        return {"ok": False, "reason": "bad_essence"}
    count = max(1.0, float(count))
    cost = {f"essence.{essence_kind}": round(RECLAIM_ESSENCE * count, 1),
            "bits": round(RECLAIM_BITS * count, 1)}
    if not db.res_spend(cost):
        return {"ok": False, "reason": "cant_afford", "cost": cost}
    db.res_add("cores", count)
    return {"ok": True, "gained": count, "cost": cost}


# -------------------------------------------------------------------- rates --
def total_rates() -> dict:
    """Summed per-hour income across all active harvesters (for the UI bar)."""
    from .world import generate_rift            # local import, avoids cycle
    from . import ticker
    totals: dict[str, float] = {}
    for h in db.list_harvests():
        d = db.get_daemon(h["daemon_id"])
        if not d:
            continue
        try:
            rift = generate_rift(h["mac"])
        except ValueError:
            continue
        for k, v in harvest_rates(d, rift, h["node_index"],
                                  ticker.dormancy(h["mac"])).items():
            totals[k] = totals.get(k, 0) + v
    return {k: round(v, 2) for k, v in totals.items()}
