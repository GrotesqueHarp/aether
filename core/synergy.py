"""
synergy.py — Making party composition a question worth asking.

Without this, picking a party is arithmetic: take your three strongest. The
type triangle exists but never enters the decision, because nothing rewards
bringing a Vaccine along.

Bonuses are deliberately modest. They should make a considered party feel
smart, not make an unconsidered one unviable — this is still a game you can
leave running.
"""

from __future__ import annotations

from . import content

RULES = [
    {
        "key": "spectrum",
        "name": "Spectrum",
        "desc": "three different elements — +10% ATK",
        "stat": "atk", "mult": 1.10,
        "test": lambda p: len(p) >= 3 and len({d.element for d in p}) == len(p),
    },
    {
        "key": "triangle",
        "name": "Closed Triangle",
        "desc": "Vaccine, Virus and Data together — +10% HP",
        "stat": "hp", "mult": 1.10,
        "test": lambda p: {d.attribute for d in p} == set(content.ATTRIBUTES),
    },
    {
        "key": "phalanx",
        "name": "Phalanx",
        "desc": "one shared attribute — +12% DEF",
        "stat": "def", "mult": 1.12,
        "test": lambda p: len(p) >= 2 and len({d.attribute for d in p}) == 1,
    },
    {
        "key": "lineage",
        "name": "Shared Lineage",
        "desc": "every member has ascended — +8% SPD",
        "stat": "spd", "mult": 1.08,
        "test": lambda p: len(p) >= 2 and all(
            getattr(d, "ascensions", 0) > 0 for d in p),
    },
]


def evaluate(party: list) -> list[dict]:
    """Which synergies this party earns. Order is stable for the UI."""
    if not party:
        return []
    out = []
    for r in RULES:
        try:
            if r["test"](party):
                out.append({k: r[k] for k in ("key", "name", "desc", "stat", "mult")})
        except Exception:
            continue
    return out


def apply(party: list) -> tuple[list, list[dict]]:
    """Return combat-ready clones with synergies baked in, plus what applied.

    Clones rather than mutating, so a bonus earned for one fight can never be
    written back into a daemon's stored stats.
    """
    from .daemon import Daemon
    active = evaluate(party)
    if not active:
        return party, []
    boosted = []
    for d in party:
        c = Daemon.from_dict(d.to_dict())
        c.id = d.id
        c.equipped = list(getattr(d, "equipped", []))
        for s in active:
            c.base_stats[s["stat"]] = int(c.base_stats[s["stat"]] * s["mult"])
        boosted.append(c)
    return boosted, active
