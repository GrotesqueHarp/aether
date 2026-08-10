"""
sigils.py — Craftable equipment, and the horizontal half of prestige.

Ascension is vertical: every rank makes a daemon flatly better, and the choice
is only *when*. Sigils are the counterweight — a limited number of slots and
far more sigils than will fit, so equipping is a question of what this daemon
is *for*. A harvester wants yield; a Gatekeeper-breaker wants attack; a hall
trainee wants faster banking. The same roster can be pointed in different
directions without any of them being "wrong".

Effects land in three places: combat stats (via Daemon.stat), harvest yields
(via economy.harvest_rates) and hall training (via bastion.tick_training).
They are stored as multipliers on a daemon's `mods`, attached when the daemon
is loaded and never persisted with it, so unequipping can't leave a ghost.

Aethercite is required from tier 3 up. It only comes from repelling the Null,
which makes the strongest sigils a reward for defending what you already hold
rather than something you can simply buy.
"""

from __future__ import annotations

import os

from . import db
from .seed import Rng, _digest

MAX_TIER = 5
TIER_NAMES = {1: "Faint", 2: "Clear", 3: "Bright", 4: "Radiant", 5: "Absolute"}

# family -> the kinds it can roll, with the per-tier magnitude of each
FAMILIES = {
    "war": {
        "name": "War", "blurb": "Combat stats.",
        "kinds": {
            "atk_pct": ("Edge",     "+{v}% ATK",   0.06),
            "def_pct": ("Bulwark",  "+{v}% DEF",   0.06),
            "hp_pct":  ("Vessel",   "+{v}% HP",    0.07),
            "spd_pct": ("Quicken",  "+{v}% SPD",   0.05),
        },
    },
    "yield": {
        "name": "Yield", "blurb": "What a posted daemon pulls up.",
        "kinds": {
            "bits_pct":    ("Tithe",   "+{v}% Bits harvested",    0.08),
            "essence_pct": ("Distil",  "+{v}% essence harvested", 0.08),
            "cores_pct":   ("Condense","+{v}% Cores harvested",   0.06),
        },
    },
    "craft": {
        "name": "Craft", "blurb": "How fast a daemon improves.",
        "kinds": {
            "train_pct": ("Whetstone", "+{v}% hall training rate", 0.07),
            "xp_pct":    ("Insight",   "+{v}% XP from battles",    0.08),
            "care_pct":  ("Ease",      "-{v}% care drift",         0.05),
        },
    },
}
KIND_FAMILY = {k: fam for fam, spec in FAMILIES.items() for k in spec["kinds"]}


def craft_cost(tier: int) -> dict:
    tier = max(1, min(MAX_TIER, int(tier)))
    cost = {"cores": float(round(4 * (2.1 ** (tier - 1))))}
    if tier >= 3:
        cost["aethercite"] = float(tier - 2)
    return cost


def max_tier(loom_level: int) -> int:
    """The Loom gates how bright a sigil you can strike."""
    return 0 if loom_level <= 0 else min(MAX_TIER, (loom_level + 1) // 2)


def describe(row: dict) -> dict:
    kind = row["kind"]
    fam = KIND_FAMILY.get(kind, "war")
    label, template, _ = FAMILIES[fam]["kinds"][kind]
    pct = round(row["magnitude"] * 100, 1)
    return {
        "id": row["id"],
        "kind": kind,
        "family": fam,
        "tier": row["tier"],
        "name": f"{TIER_NAMES[row['tier']]} {label}",
        "effect": template.format(v=pct),
        "magnitude": row["magnitude"],
        "equipped_to": row["equipped_to"],
    }


def craft(family: str, tier: int) -> dict:
    """Strike a new sigil. You pick the family and the tier; which kind within
    it, and exactly how strong, is rolled — so a Yield sigil is always useful
    but never quite predictable."""
    if family not in FAMILIES:
        return {"ok": False, "reason": "bad_family"}
    lvl = db.facility_level("loom")
    cap = max_tier(lvl)
    if cap == 0:
        return {"ok": False, "reason": "no_loom"}
    tier = max(1, min(int(tier), cap))
    cost = craft_cost(tier)
    if not db.res_spend(cost):
        return {"ok": False, "reason": "cant_afford", "cost": cost}

    n = int(float(db.get_meta("sigils_struck", "0") or 0)) + 1
    db.set_meta("sigils_struck", str(n))
    rng = Rng(_digest("aether.sigil", family, str(tier), str(n)))
    kinds = list(FAMILIES[family]["kinds"])
    kind = kinds[rng.randint(0, len(kinds) - 1)]
    base = FAMILIES[family]["kinds"][kind][2]
    # 0.8x - 1.25x variance, so two sigils of a kind are rarely identical
    mag = round(base * tier * (0.8 + rng.random() * 0.45), 4)
    sid = db.add_sigil(kind, tier, mag)
    row = db.get_sigil(sid)
    return {"ok": True, "sigil": describe(row), "cost": cost}


def mods_for(daemon_id: int) -> dict:
    """Merged multipliers from everything equipped to this daemon."""
    out: dict[str, float] = {}
    for row in db.list_sigils(equipped_to=daemon_id):
        out[row["kind"]] = out.get(row["kind"], 0.0) + row["magnitude"]
    return out


def equip(sigil_id: int, daemon_id: int) -> dict:
    row = db.get_sigil(sigil_id)
    if not row:
        return {"ok": False, "reason": "no_sigil"}
    d = db.get_daemon(daemon_id)
    if not d:
        return {"ok": False, "reason": "no_daemon"}
    used = len(db.list_sigils(equipped_to=daemon_id))
    if row["equipped_to"] != daemon_id and used >= d.sigil_slots():
        return {"ok": False, "reason": "no_slots", "slots": d.sigil_slots()}
    db.set_sigil_owner(sigil_id, daemon_id)
    return {"ok": True}


def unequip(sigil_id: int) -> dict:
    if not db.get_sigil(sigil_id):
        return {"ok": False, "reason": "no_sigil"}
    db.set_sigil_owner(sigil_id, None)
    return {"ok": True}


def scrap(sigil_id: int) -> dict:
    """Melt a sigil back down. Half the Cores, rounded down — enough that
    unwanted rolls aren't dead weight, not so much that rerolling is free."""
    row = db.get_sigil(sigil_id)
    if not row:
        return {"ok": False, "reason": "no_sigil"}
    refund = {k: float(int(v / 2)) for k, v in craft_cost(row["tier"]).items()}
    refund = {k: v for k, v in refund.items() if v > 0}
    for k, v in refund.items():
        db.res_add(k, v)
    db.delete_sigil(sigil_id)
    return {"ok": True, "refund": refund}
