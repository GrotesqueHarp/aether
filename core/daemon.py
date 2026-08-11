"""
daemon.py — The creatures.

A daemon is defined by an immutable "genome" (rolled once from a seed) plus a
mutable "state" (level, xp, care meters, current stage). Generation is
deterministic given a seed, so the same rift always offers the same wild
daemons. Care and training then take over and make each raised daemon personal.
"""

from __future__ import annotations

import os

from dataclasses import dataclass, field, asdict
from typing import Optional

from . import content
from .seed import Rng, _digest


# Care meters live in 0..100. These drift over time (see nest.tick) and shape
# both battle readiness and which evolution branch a daemon takes.
CARE_DEFAULTS = {
    "hunger": 60,      # higher = more full
    "energy": 80,      # rest / stamina
    "happiness": 70,
    "discipline": 40,  # obedience; raised by training, lowered by overfeeding
    "corruption": 5,   # aether rot; neglect pushes toward Virus evolutions
    "weight": 20,      # affects SPD; overfeeding raises it
}

# --- ascension tuning -------------------------------------------------------
# Compounding per rank, so lineage keeps pace with tier scaling rather than
# falling behind it. 1.18 gives ~2.3x by rank 5 and ~5x by rank 10.
ASCEND_STAT_MULT = float(os.environ.get("AETHER_ASCEND_MULT", "1.18"))
ASCEND_LEVEL = int(os.environ.get("AETHER_ASCEND_LEVEL", "60"))
ASCEND_CORE_BASE = float(os.environ.get("AETHER_ASCEND_CORES", "6"))
ASCEND_RARITY_RANKS = (3, 6)

# Manual training is intentionally weak — see Daemon.train
TRAIN_ENERGY_FLOOR = 40      # must be well rested to hand-train at all
TRAIN_ENERGY_COST = 35       # ~4 hours of idle recovery per click

STAT_KEYS = ["hp", "atk", "def", "spd"]


def _roll_sigil(rng: Rng) -> dict:
    """A compact spec the frontend expands into a unique SVG creature-sigil."""
    return {
        "arms": rng.randint(3, 8),          # symmetry / spoke count
        "rings": rng.randint(1, 4),
        "jitter": round(rng.random(), 3),
        "hue_shift": rng.randint(-24, 24),
        "glyph": rng.choice("△○◇✦❋⬡⬢✵❖◈✷".split() or list("△○◇")),
        "eyes": rng.randint(1, 4),
    }


def _build_name(rng: Rng, element: str, stage: str) -> str:
    head = rng.choice(content.NAME_HEADS)
    # bias one syllable toward the element for family feel
    if rng.chance(0.5):
        head = element
    tail = rng.choice(content.NAME_TAILS_BY_STAGE[stage])
    joiner = "" if tail.startswith("-") else ""
    name = f"{head}{joiner}{tail}"
    return name[0].upper() + name[1:]


@dataclass
class Daemon:
    # --- genome (immutable identity) ---
    seed: str
    attribute: str
    element: str
    rarity: int                 # 1..5
    base_stats: dict            # growth-independent baseline
    growth: dict                # per-level gain per stat
    sigil: dict
    origin_mac: str             # which rift it came from ("" if starter)
    # --- mutable state ---
    name: str = ""
    stage: str = "Hatchling"
    level: int = 1
    xp: int = 0
    care: dict = field(default_factory=lambda: dict(CARE_DEFAULTS))
    wins: int = 0
    losses: int = 0
    ascensions: int = 0         # lineage rank — see ascend()
    id: Optional[int] = None    # set by the DB layer

    def __post_init__(self):
        # populated by the DB layer from the glyphs table; deliberately not a
        # dataclass field, so it never round-trips into the stored blob
        if not hasattr(self, "equipped"):
            self.equipped = []

    # ---- derived battle stats ------------------------------------------------
    def stat(self, key: str) -> int:
        base = self.base_stats[key]
        grown = base + int(self.growth[key] * (self.level - 1))
        # stage multiplier: later forms are simply bigger
        stage_mult = 1.0 + 0.22 * content.STAGES.index(self.stage)
        val = grown * stage_mult
        # Lineage compounds. Rift tiers scale enemies exponentially (x1.6 per
        # tier) while levelling and halls add linearly, so without a
        # multiplicative channel of your own the curve eventually outruns you
        # no matter how long you grind. Ascension is that channel.
        val *= ASCEND_STAT_MULT ** self.ascensions
        # equipped glyphs: horizontal choice on top of vertical growth
        from . import glyph, traits
        val *= 1.0 + glyph.stat_bonus(getattr(self, "equipped", []), key)
        val *= traits.mult(self, f"stat.{key}")
        # care modifiers
        if key == "spd":
            val *= 1.0 - min(self.care["weight"], 90) / 300.0      # heavy = slow
            val *= 0.85 + self.care["energy"] / 300.0
        if key == "atk":
            val *= 0.9 + self.care["happiness"] / 400.0
        if key == "def":
            val *= 0.9 + self.care["discipline"] / 400.0
        return max(1, int(round(val)))

    def battle_stats(self) -> dict:
        return {k: self.stat(k) for k in STAT_KEYS}

    def power(self) -> int:
        s = self.battle_stats()
        return s["hp"] // 4 + s["atk"] + s["def"] + s["spd"]

    # ---- ascension -----------------------------------------------------------
    def can_ascend(self) -> bool:
        return self.stage == content.STAGES[-1] and self.level >= ASCEND_LEVEL

    def ascend_cost(self) -> dict:
        return {"cores": float(ASCEND_CORE_BASE * (self.ascensions + 1))}

    def ascend(self) -> dict:
        """Return a fully-grown daemon to a Hatchling, permanently stronger.

        It keeps its seed, so it is recognisably the same creature — the point
        is a lineage you've raised repeatedly, not a fresh roll. Wins, losses
        and name carry over; levels and stage do not.
        """
        if not self.can_ascend():
            return {"ok": False, "reason": "not_ready"}
        before = self.power()
        self.ascensions += 1
        self.stage = "Hatchling"
        self.level = 1
        self.xp = 0
        self.care = dict(CARE_DEFAULTS)
        # a lineage refines itself: rarer at ranks 3 and 6
        if self.ascensions in ASCEND_RARITY_RANKS and self.rarity < 5:
            self.rarity += 1
        return {"ok": True, "rank": self.ascensions,
                "power_before": before, "power_after": self.power(),
                "rarity": self.rarity}

    def xp_to_next(self) -> int:
        return 20 + self.level * self.level * 6

    # ---- progression ---------------------------------------------------------
    def gain_xp(self, amount: int) -> dict:
        """Returns a small event dict describing what happened."""
        from . import glyph, traits
        amount = int(amount * (1.0 + glyph.bonus(
            getattr(self, "equipped", []), "xp")) * traits.mult(self, "xp"))
        events = {"xp": amount, "levels": 0, "evolved_to": None}
        self.xp += amount
        while self.xp >= self.xp_to_next():
            self.xp -= self.xp_to_next()
            self.level += 1
            events["levels"] += 1
        return events

    def can_evolve(self) -> bool:
        idx = content.STAGES.index(self.stage)
        if idx >= len(content.STAGES) - 1:
            return False
        gate = content.STAGE_LEVEL_GATE.get(self.stage, 999)
        return self.level >= gate

    def evolution_branch(self) -> str:
        """Care quality decides the attribute a daemon drifts toward."""
        if self.care["corruption"] >= 60 or self.care["happiness"] < 25:
            return "Virus"
        if self.care["discipline"] >= 60 and self.care["happiness"] >= 55:
            return "Vaccine"
        return "Data"

    def evolve(self) -> dict:
        """Advance one stage. May shift attribute based on how it was raised."""
        if not self.can_evolve():
            return {"ok": False, "reason": "not_ready"}
        old_stage, old_attr = self.stage, self.attribute
        idx = content.STAGES.index(self.stage)
        self.stage = content.STAGES[idx + 1]
        # branch drift (soft: only a chance, keeps identity mostly intact)
        branch = self.evolution_branch()
        if branch != self.attribute:
            r = Rng(_digest(self.seed, "evo", self.stage))
            if r.chance(0.6):
                self.attribute = branch
        # a permanent stat bump on top of the stage multiplier
        for k in STAT_KEYS:
            self.base_stats[k] = int(self.base_stats[k] * 1.08) + 1
        return {"ok": True, "from": old_stage, "to": self.stage,
                "attr_from": old_attr, "attr_to": self.attribute}

    # ---- care actions --------------------------------------------------------
    def _clamp(self):
        for k, v in self.care.items():
            self.care[k] = max(0, min(100, v))

    def feed(self, rich: bool = False):
        self.care["hunger"] += 30 if rich else 18
        self.care["happiness"] += 4
        self.care["weight"] += 6 if rich else 2
        if self.care["hunger"] > 100:                       # overfeeding
            self.care["discipline"] -= 5
            self.care["weight"] += 5
        self._clamp()

    def rest(self):
        self.care["energy"] += 35
        self.care["happiness"] += 2
        self._clamp()

    def play(self):
        self.care["happiness"] += 16
        self.care["energy"] -= 10
        self.care["corruption"] -= 6
        self.care["weight"] -= 3
        self._clamp()

    def cleanse(self):
        """Purge aether corruption (costs energy)."""
        self.care["corruption"] -= 22
        self.care["energy"] -= 12
        self._clamp()

    def train(self, stat: str) -> dict:
        """Hand-training a daemon. Deliberately marginal: one point, and it
        costs most of a rested daemon's energy, so a click buys roughly four
        hours of idle recovery. The training halls exist to make this
        obsolete — clicking should never be the efficient path."""
        if stat not in STAT_KEYS:
            return {"ok": False, "reason": "bad_stat"}
        if self.care["energy"] < TRAIN_ENERGY_FLOOR:
            return {"ok": False, "reason": "too_tired"}
        gain = 1
        self.base_stats[stat] += gain
        self.care["energy"] -= TRAIN_ENERGY_COST
        self.care["discipline"] += 6
        self.care["happiness"] -= 3
        self.care["hunger"] -= 8
        self._clamp()
        ev = self.gain_xp(4 + self.level // 2)
        return {"ok": True, "stat": stat, "gain": gain, "xp": ev}

    # ---- serialization -------------------------------------------------------
    def to_dict(self) -> dict:
        d = asdict(self)
        d["battle_stats"] = self.battle_stats()
        d["power"] = self.power()
        d["xp_to_next"] = self.xp_to_next()
        d["can_evolve"] = self.can_evolve()
        d["can_ascend"] = self.can_ascend()
        d["ascend_cost"] = self.ascend_cost()
        d["ascend_level"] = ASCEND_LEVEL
        from . import glyph, traits
        d["traits"] = traits.describe(self)
        d["equipped"] = getattr(self, "equipped", [])
        d["glyph_slots"] = glyph.slots_for(self)
        d["color"] = content.ELEMENT_COLORS.get(self.element, "#8B7CF6")
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Daemon":
        keep = {k: d[k] for k in (
            "seed", "attribute", "element", "rarity", "base_stats", "growth",
            "sigil", "origin_mac", "name", "stage", "level", "xp", "care",
            "wins", "losses", "ascensions", "id") if k in d}
        return cls(**keep)


def generate_daemon(rng: Rng, *, origin_mac: str = "",
                    favored_elements=None, min_rarity: int = 1,
                    stage: str = "Hatchling") -> Daemon:
    """Roll a fresh daemon from an RNG stream."""
    attribute = rng.choice(content.ATTRIBUTES)
    if favored_elements and rng.chance(0.7):
        element = rng.choice(favored_elements)
    else:
        element = rng.choice(content.ELEMENTS)

    rarity = max(min_rarity, rng.weighted(
        [(1, 46), (2, 28), (3, 16), (4, 8), (5, 2)]))

    # base stats scale gently with rarity; each daemon has a "shape"
    budget = 130 + rarity * 22
    weights = [rng.random() + 0.35 for _ in STAT_KEYS]
    tot = sum(weights)
    base_stats = {}
    for k, w in zip(STAT_KEYS, weights):
        share = w / tot
        if k == "hp":
            base_stats[k] = int(28 + budget * share * 2.4)
        else:
            base_stats[k] = int(8 + budget * share * 0.9)

    growth = {k: round(1.4 + rng.random() * 2.6 + rarity * 0.3, 2) for k in STAT_KEYS}
    sigil = _roll_sigil(rng)
    seed_id = _digest(origin_mac, str(rng.random()), element, attribute).hex()[:16]

    d = Daemon(
        seed=seed_id, attribute=attribute, element=element, rarity=rarity,
        base_stats=base_stats, growth=growth, sigil=sigil, origin_mac=origin_mac,
        stage=stage,
    )
    d.name = _build_name(Rng(_digest(seed_id, "name")), element, stage)
    return d


def starter_daemon() -> Daemon:
    """The daemon a new player hatches from their Anchor device."""
    from .seed import Rng as _R
    r = _R(_digest("aether.starter.egg"))
    d = generate_daemon(r, origin_mac="", min_rarity=2, stage="Hatchling")
    d.name = "Kernel"
    return d
