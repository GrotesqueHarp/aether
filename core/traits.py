"""
traits.py — Giving daemons a character beyond their numbers.

Without traits a roster is a leaderboard: a 5-star replaces a 3-star and the
decision is arithmetic. A trait makes you keep a mediocre daemon because it is
*the* Tunneler, and makes selling a judgement instead of a subtraction.

Traits are derived from the daemon's seed rather than stored. That means no
migration, every daemon you already own has always had its trait, and the same
seed anywhere produces the same creature down to its habits.

Most traits carry a cost as well as a benefit. A pure upgrade would just be a
rarity roll by another name.
"""

from __future__ import annotations

from .seed import Rng, _digest

# effect keys consumed elsewhere:
#   stat.<hp|atk|def|spd>  multiplier on that combat stat
#   harvest / bits / cores multipliers on what a post produces
#   training               multiplier on hall banking rate
#   expedition             multiplier on expedition digging speed
#   xp                     multiplier on experience gained
#   drift.<meter>          multiplier on that care meter's drift rate
#   defence                multiplier applied when defending an incursion
#   nocturnal              harvest multiplier, but only between 20:00 and 06:00
TRAITS = {
    "tunneler":   {"name": "Tunneler",   "desc": "digs 30% faster on expeditions",
                   "effects": {"expedition": 1.30}},
    "nocturnal":  {"name": "Nocturnal",  "desc": "+25% harvest after dark",
                   "effects": {"nocturnal": 1.25}},
    "diligent":   {"name": "Diligent",   "desc": "+20% training hall rate",
                   "effects": {"training": 1.20}},
    "stoic":      {"name": "Stoic",      "desc": "corrupts half as fast",
                   "effects": {"drift.corruption": 0.5}},
    "voracious":  {"name": "Voracious",  "desc": "+12% ATK, but hungers faster",
                   "effects": {"stat.atk": 1.12, "drift.hunger": 1.4}},
    "feather":    {"name": "Featherweight", "desc": "+15% SPD, -8% HP",
                   "effects": {"stat.spd": 1.15, "stat.hp": 0.92}},
    "ironhide":   {"name": "Ironhide",   "desc": "+15% DEF, -8% SPD",
                   "effects": {"stat.def": 1.15, "stat.spd": 0.92}},
    "quick":      {"name": "Quick Study", "desc": "+25% XP gained",
                   "effects": {"xp": 1.25}},
    "hoarder":    {"name": "Hoarder",    "desc": "+15% Bits from posts",
                   "effects": {"bits": 1.15}},
    "prospector": {"name": "Prospector", "desc": "+30% Cores from posts",
                   "effects": {"cores": 1.30}},
    "restless":   {"name": "Restless",   "desc": "recovers energy fast, tires of company",
                   "effects": {"drift.happiness": 1.35, "energy_regen": 1.45}},
    "warden":     {"name": "Warden",     "desc": "+20% when defending an incursion",
                   "effects": {"defence": 1.20}},
    "homebody":   {"name": "Homebody",   "desc": "+20% harvest, but won't expedition well",
                   "effects": {"harvest": 1.20, "expedition": 0.8}},
    "wanderer":   {"name": "Wanderer",   "desc": "+20% on expeditions, restless on a shelf",
                   "effects": {"expedition": 1.20, "harvest": 0.85}},
}
KEYS = sorted(TRAITS)


def for_daemon(d) -> list[str]:
    """Which traits this daemon has. One normally, two if it's rare."""
    seed = getattr(d, "seed", None)
    if not seed:
        return []
    r = Rng(_digest(seed, "traits.v1"))
    n = 2 if getattr(d, "rarity", 1) >= 4 else 1
    picks, pool = [], list(KEYS)
    for _ in range(min(n, len(pool))):
        pick = pool.pop(r.randint(0, len(pool) - 1))
        picks.append(pick)
    return picks


def describe(d) -> list[dict]:
    return [{"key": k, **{f: TRAITS[k][f] for f in ("name", "desc")}}
            for k in for_daemon(d)]


def mult(d, effect: str) -> float:
    """Combined multiplier for one effect key. 1.0 when nothing applies."""
    total = 1.0
    for k in for_daemon(d):
        total *= TRAITS[k]["effects"].get(effect, 1.0)
    return total


def harvest_mult(d) -> float:
    """Harvest yield, including the time-of-day trait.

    Nocturnal reads the server's local clock — the same wall clock the Tank
    tints itself by, so 'after dark' means the same thing in both places.
    """
    import datetime
    m = mult(d, "harvest")
    if mult(d, "nocturnal") != 1.0:
        hour = datetime.datetime.now().hour
        if hour >= 20 or hour < 6:
            m *= mult(d, "nocturnal")
    return m
