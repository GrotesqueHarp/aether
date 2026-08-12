"""
reformat.py — The outermost loop.

Everything else in this game compounds within a run: a daemon ascends, a rift
masters, a glyph is struck. Reformat is the loop around all of them — you give
the whole save back and keep a permanent multiplier on everything that follows.

Design rules this follows, in order of importance:

  It must never be mandatory. This is a game you leave running for a year; a
  prestige that resets you every fortnight would be a treadmill. The threshold
  is deliberately far out, and the game is complete without ever touching it.

  It must never feel like loss. What you keep — Aethercite, lineage, resolved
  rifts — is chosen so that a Reformat reads as carrying something forward
  rather than starting over. Daemons you ascended stay ascended.

  It must be legible before you commit. The API reports exactly what you'd
  earn and exactly what you'd lose, because a one-way door with a hidden
  payoff is a trap, not a decision.
"""

from __future__ import annotations

import os

from . import db, mastery

# What Reformat measures: total lifetime accomplishment, not current holdings.
# Using current holdings would reward hoarding and punish spending, which is
# backwards — the point is to have USED the economy.
THRESHOLD = float(os.environ.get("AETHER_REFORMAT_THRESHOLD", "4000"))
GAIN_PER_LEVEL = float(os.environ.get("AETHER_REFORMAT_GAIN", "0.12"))
SCALE = float(os.environ.get("AETHER_REFORMAT_SCALE", "1.6"))


def score() -> dict:
    """A single number for 'how far did this run get'.

    Layers dug dominates because it's the one figure that only ever goes up
    and can't be farmed cheaply. Mastery and lineage contribute because they
    represent time invested rather than resources banked.
    """
    layers = db.total_layers_cleared()
    mast = sum(mastery.level_from_xp(x) for x in db.all_mastery_xp().values())
    tiers = sum(db.get_progress(d["mac"])["tier"] for d in db.list_devices())
    ranks = sum(getattr(d, "ascensions", 0) for d in db.list_daemons())
    total = layers + mast * 4 + tiers * 60 + ranks * 45
    return {"layers": layers, "mastery": mast, "tiers": tiers, "ranks": ranks,
            "total": round(total, 1)}


def cycles() -> int:
    return int(float(db.get_meta("reformat_cycles", "0") or 0))


def echo_mult() -> float:
    """The permanent multiplier. Applied to every resource the world produces."""
    return 1.0 + GAIN_PER_LEVEL * cycles()


def threshold_for(cycle: int) -> float:
    """Each Reformat asks more than the last, so they space further apart."""
    return THRESHOLD * (SCALE ** cycle)


def status() -> dict:
    c = cycles()
    sc = score()
    need = threshold_for(c)
    gained = 1 if sc["total"] >= need else 0
    return {
        "cycles": c,
        "score": sc,
        "threshold": round(need, 1),
        "ready": sc["total"] >= need,
        "pct": round(min(100.0, 100 * sc["total"] / need), 1),
        "current_mult": round(echo_mult(), 3),
        "next_mult": round(1.0 + GAIN_PER_LEVEL * (c + gained), 3),
        "keeps": [
            "Aethercite — everything you earned defending the Null",
            "Every daemon's ascension rank, and its traits",
            "Resolved rifts stay resolved; the Array keeps its level",
            "Lifetime layers dug, and the Records history",
        ],
        "loses": [
            "Your roster, apart from one daemon carried forward",
            "All Bits, essence and Cores",
            "Every facility level except the Array",
            "All rift depth, tiers, wards and mastery",
            "Struck glyphs",
        ],
    }


def reformat(keep_daemon_id: int | None = None) -> dict:
    """Fold the run. Returns what happened; the caller journals it."""
    st = status()
    if not st["ready"]:
        return {"ok": False, "reason": "not_ready", "status": st}

    roster = db.list_daemons()
    if not roster:
        return {"ok": False, "reason": "no_roster"}

    # carry one daemon forward — by default the one with the most lineage,
    # since that's the creature the player has invested most in
    keeper = None
    if keep_daemon_id is not None:
        keeper = db.get_daemon(int(keep_daemon_id))
    if keeper is None:
        keeper = max(roster, key=lambda d: (getattr(d, "ascensions", 0), d.power()))

    aethercite = db.res_all().get("aethercite", 0.0)
    array_level = db.facility_level("array")
    layers = db.total_layers_cleared()

    # a carried daemon comes back rested and unmade, but keeps its lineage
    carried = keeper.to_dict()
    carried_id = keeper.id

    db.reset_all(keep_devices=True)

    fresh = db.get_daemon(carried_id)          # gone with the wipe; rebuild it
    from .daemon import Daemon
    d = Daemon.from_dict(carried)
    d.id = None
    d.stage = "Hatchling"
    d.level = 1
    d.xp = 0
    from .daemon import CARE_DEFAULTS
    d.care = dict(CARE_DEFAULTS)
    new_id = db.add_daemon(d)

    # restore what survives a fold
    if aethercite > 0:
        db.res_add("aethercite", aethercite)
    if array_level:
        db.set_facility_level("array", array_level)
    db.set_meta("layers_dug", str(layers))
    db.set_meta("bootstrapped", "1")
    db.set_meta("reformat_cycles", str(cycles() + 1))

    return {"ok": True, "cycles": cycles(), "mult": round(echo_mult(), 3),
            "carried": {"id": new_id, "name": d.name,
                        "ascensions": getattr(d, "ascensions", 0)},
            "kept": {"aethercite": round(aethercite, 1),
                     "array_level": array_level, "layers_dug": layers},
            "score": st["score"]}
