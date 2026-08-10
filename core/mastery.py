"""
mastery.py — Knowing a rift.

Two coupled tracks, deliberately pulling in different directions:

  Mastery   per rift, 1..99, earned by digging and by working its shelves.
            Gives that rift steadily better yields, plus milestone perks.

  Resonance global, from the SUM of mastery across every rift you hold.
            This is the one that rewards breadth: twenty rifts at 25 beat one
            rift at 99, so finding more hardware — and more of the sky — pays
            off in a way that grinding a single shaft never does.

Both are slow on purpose. 99 is a landmark, not a checkbox.
"""

from __future__ import annotations

import os

MAX_LEVEL = 99
XP_K = float(os.environ.get("AETHER_MASTERY_K", "55"))
XP_P = float(os.environ.get("AETHER_MASTERY_P", "2.15"))
YIELD_PER_LEVEL = float(os.environ.get("AETHER_MASTERY_YIELD", "0.01"))
RESONANCE_PER_LEVEL = float(os.environ.get("AETHER_RESONANCE", "0.0015"))

# level -> (key, name, what it does)
MILESTONES = [
    (10, "deep_reading", "Deep Reading",
     "expeditions dig this rift 25% faster"),
    (25, "echo", "Echo",
     "one extra capture per tier from this rift's shelves"),
    (50, "familiar", "Familiar Ground",
     "enemies here fight as though two levels lower"),
    (75, "rich_veins", "Rich Veins",
     "posts here yield 50% more Cores"),
    (99, "mastered", "Mastered",
     "all yields here doubled, and layers dug count double toward the Array"),
]


def xp_for_level(level: int) -> float:
    """Cumulative XP needed to *reach* this level."""
    if level <= 1:
        return 0.0
    return XP_K * ((level - 1) ** XP_P)


def level_from_xp(xp: float) -> int:
    if xp <= 0:
        return 1
    lvl = int((xp / XP_K) ** (1.0 / XP_P)) + 1
    return max(1, min(MAX_LEVEL, lvl))


def progress(xp: float) -> dict:
    lvl = level_from_xp(xp)
    cur = xp_for_level(lvl)
    nxt = xp_for_level(min(MAX_LEVEL, lvl + 1))
    span = max(1.0, nxt - cur)
    return {"level": lvl, "xp": round(xp, 1),
            "into": round(xp - cur, 1), "need": round(span, 1),
            "pct": 0 if lvl >= MAX_LEVEL else round(100 * (xp - cur) / span, 1),
            "unlocked": [k for lv, k, _n, _d in MILESTONES if lvl >= lv],
            "milestones": [{"level": lv, "key": k, "name": n, "desc": d,
                            "have": lvl >= lv} for lv, k, n, d in MILESTONES]}


def has(xp: float, key: str) -> bool:
    lvl = level_from_xp(xp)
    return any(lvl >= lv and k == key for lv, k, _n, _d in MILESTONES)


def yield_mult(xp: float) -> float:
    """Per-rift yield bonus: +1%/level, doubled outright at 99."""
    lvl = level_from_xp(xp)
    m = 1.0 + YIELD_PER_LEVEL * (lvl - 1)
    if lvl >= MAX_LEVEL:
        m *= 2.0
    return m


def resonance(levels: list[int]) -> float:
    """Global multiplier from the breadth of what you've mastered."""
    return 1.0 + RESONANCE_PER_LEVEL * max(0, sum(levels) - len(levels))


# ------------------------------------------------------------------ earning --
def xp_for_clear(layer: int, is_gatekeeper: bool) -> float:
    """Deeper layers teach more; Gatekeepers teach a great deal."""
    return layer * 1.5 * (6.0 if is_gatekeeper else 1.0)


def xp_for_harvest(layer: int, hours: float) -> float:
    """Working a shelf teaches slowly — this is the idle trickle."""
    return layer * 0.35 * hours
