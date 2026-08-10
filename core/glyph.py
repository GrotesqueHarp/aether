"""
glyph.py — Craftable equipment.

Ascension is the vertical track: every rank makes a daemon flatly better.
Glyphs are the horizontal one. A Loam glyph makes a harvester earn more but
does nothing in a fight; a Forge glyph is the reverse. That turns a roster from
a power ranking into a set of jobs, and gives Aethercite its second sink.

(Named Glyphs rather than Sigils because `sigil` already means the procedural
emblem in every daemon's genome — the thing the UI draws.)

Quality is chosen and paid for, never rolled. This game doesn't ask you to
gamble or to show up at the right moment.
"""

from __future__ import annotations

import os

MAX_QUALITY = 5

GLYPHS = {
    "forge":   {"name": "Forge Glyph",   "essence": "ferro",  "stat": "atk",
                "per": 0.06, "desc": "+{pct}% ATK"},
    "bulwark": {"name": "Bulwark Glyph", "essence": "loam",   "stat": "def",
                "per": 0.06, "desc": "+{pct}% DEF"},
    "tide":    {"name": "Tide Glyph",    "essence": "tide",   "stat": "hp",
                "per": 0.07, "desc": "+{pct}% HP"},
    "circuit": {"name": "Circuit Glyph", "essence": "volt",   "stat": "spd",
                "per": 0.06, "desc": "+{pct}% SPD"},
    "harvest": {"name": "Harvest Glyph", "essence": "loam",   "stat": None,
                "effect": "harvest", "per": 0.09,
                "desc": "+{pct}% harvest yield"},
    "insight": {"name": "Insight Glyph", "essence": "umbra",  "stat": None,
                "effect": "xp", "per": 0.11, "desc": "+{pct}% XP gained"},
    "adept":   {"name": "Adept Glyph",   "essence": "plasma", "stat": None,
                "effect": "training", "per": 0.11,
                "desc": "+{pct}% training hall rate"},
}

# Slots come from what a daemon has been through, not from what you buy: how
# far it evolved, and how many times it has been unmade and raised again.
STAGE_SLOTS = {"Egg": 0, "Hatchling": 1, "Rookie": 1,
               "Champion": 2, "Ultimate": 2, "Mega": 3}
CRAFT_CORE_BASE = float(os.environ.get("AETHER_GLYPH_CORES", "4"))
CRAFT_ESSENCE_BASE = float(os.environ.get("AETHER_GLYPH_ESSENCE", "45"))
CRAFT_BITS_BASE = float(os.environ.get("AETHER_GLYPH_BITS", "900"))


def slots_for(daemon) -> int:
    n = STAGE_SLOTS.get(daemon.stage, 1)
    asc = getattr(daemon, "ascensions", 0)
    if asc >= 3:
        n += 1
    if asc >= 6:
        n += 1
    return min(5, n)


def craft_cost(kind: str, quality: int) -> dict:
    """Steep in quality, so a Q5 is a project rather than a purchase."""
    g = GLYPHS[kind]
    q = max(1, min(MAX_QUALITY, int(quality)))
    scale = q ** 1.9
    cost = {"bits": round(CRAFT_BITS_BASE * scale, 1),
            f"essence.{g['essence']}": round(CRAFT_ESSENCE_BASE * scale, 1),
            "cores": round(CRAFT_CORE_BASE * scale, 1)}
    if q >= 3:
        # Aethercite comes only from repelling the Null, so the strongest
        # glyphs are gated behind defending what you already hold
        cost["aethercite"] = float(q - 2)
    return cost


def magnitude(kind: str, quality: int) -> float:
    return GLYPHS[kind]["per"] * quality


def describe(kind: str, quality: int) -> str:
    return GLYPHS[kind]["desc"].format(pct=round(magnitude(kind, quality) * 100))


def bonus(equipped: list, effect: str) -> float:
    """Summed multiplier for a named effect ('harvest', 'xp', 'training')."""
    total = 0.0
    for g in equipped or []:
        spec = GLYPHS.get(g["kind"])
        if spec and spec.get("effect") == effect:
            total += magnitude(g["kind"], g["quality"])
    return total


def stat_bonus(equipped: list, stat: str) -> float:
    total = 0.0
    for g in equipped or []:
        spec = GLYPHS.get(g["kind"])
        if spec and spec.get("stat") == stat:
            total += magnitude(g["kind"], g["quality"])
    return total


def catalogue() -> list[dict]:
    out = []
    for kind, g in GLYPHS.items():
        out.append({
            "kind": kind, "name": g["name"], "essence": g["essence"],
            "qualities": [{"quality": q, "cost": craft_cost(kind, q),
                           "desc": describe(kind, q)}
                          for q in range(1, MAX_QUALITY + 1)],
        })
    return out
