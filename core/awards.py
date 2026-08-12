"""
awards.py — What you get for the years.

Every other reward in this game is a multiplier, and multipliers have a fatal
property over a long run: the tenth one is invisible. Going from x1.12 to x1.24
doesn't register. By month six a purely numerical reward track has stopped
saying anything.

Cosmetics don't dilute. A palette earned at ten thousand layers is exactly as
vivid in month thirty as in month three, because it isn't more of a thing you
already had — it's a different kind of thing. It's also a record: every time
the UI is that colour, it says you dug ten thousand layers.

Two tiers:

  TRINKET   small, frequent, roughly weekly. Earned by accumulation — layers,
            rifts, daemons raised, days elapsed. Requirements are VISIBLE, so
            they read as goals.

  LANDMARK  rare, quarterly or beyond. Earned by feats — a 5-star Mega, an
            incursion held undefeated, a rift taken to mastery 99. HIDDEN
            until earned, so they read as discoveries.

Awards are permanent. They survive Reformat, because they are the record of
everything the instance has ever done, and folding a run shouldn't erase your
own history.

Time-based awards always carry a second condition. "Day 365" alone would dump
a year of backlogged rewards on someone who discovers the game late, cheapening
all of them at once; "365 days AND a thousand layers" reads as endurance.
"""

from __future__ import annotations

import time

from . import db, mastery

TRINKET, LANDMARK = "trinket", "landmark"

# kind: theme | decor | adornment | environment | title
AWARDS = [
    # ---------------------------------------------------------------- depth --
    {"key": "first_hundred", "tier": TRINKET, "kind": "title",
     "name": "Layerbreaker", "detail": "100 layers dug",
     "need": {"layers": 100}},
    {"key": "deep_current", "tier": TRINKET, "kind": "decor",
     "name": "Deep Current", "detail": "a slow drift through the tank",
     "need": {"layers": 500}},
    {"key": "shaftlight", "tier": TRINKET, "kind": "decor",
     "name": "Shaftlight", "detail": "light from somewhere far above",
     "need": {"layers": 2000}},
    {"key": "ferrous", "tier": TRINKET, "kind": "theme",
     "name": "Ferrous", "detail": "iron and rust",
     "need": {"layers": 5000}},
    {"key": "the_deep", "tier": LANDMARK, "kind": "environment",
     "name": "The Deep", "detail": "the tank becomes an abyss",
     "need": {"layers": 25000}},

    # -------------------------------------------------------------- breadth --
    {"key": "cartographer", "tier": TRINKET, "kind": "title",
     "name": "Cartographer", "detail": "8 rifts resolved",
     "need": {"rifts": 8}},
    {"key": "constellation", "tier": TRINKET, "kind": "decor",
     "name": "Constellation", "detail": "a point of light per rift you hold",
     "need": {"rifts": 15}},
    {"key": "resonant", "tier": TRINKET, "kind": "theme",
     "name": "Resonant", "detail": "violet and signal-green",
     "need": {"mastery_total": 250}},
    {"key": "the_choir", "tier": LANDMARK, "kind": "environment",
     "name": "The Choir", "detail": "every rift you hold, singing at once",
     "need": {"mastery_total": 1500}},

    # ----------------------------------------------------------------- time --
    {"key": "patient", "tier": TRINKET, "kind": "title",
     "name": "The Patient", "detail": "30 days, and 500 layers",
     "need": {"days": 30, "layers": 500}},
    {"key": "slow_water", "tier": TRINKET, "kind": "decor",
     "name": "Slow Water", "detail": "drifting motes that were always there",
     "need": {"days": 90, "layers": 2000}},
    {"key": "long_dark", "tier": TRINKET, "kind": "theme",
     "name": "The Long Dark", "detail": "near-black, for a room at night",
     "need": {"days": 180, "layers": 4000}},
    {"key": "year_one", "tier": LANDMARK, "kind": "theme",
     "name": "Year One", "detail": "gold on deep blue — a year of running",
     "need": {"days": 365, "layers": 10000}},

    # ----------------------------------------------------------------- care --
    {"key": "keeper", "tier": TRINKET, "kind": "title",
     "name": "Keeper", "detail": "10 daemons raised",
     "need": {"raised": 10}},
    {"key": "the_nest_grows", "tier": TRINKET, "kind": "decor",
     "name": "Fronds", "detail": "something living, planted in the tank",
     "need": {"raised": 25}},
    {"key": "well_kept", "tier": TRINKET, "kind": "adornment",
     "name": "Well-Kept", "detail": "a soft halo on contented daemons",
     "need": {"contented": 6}},
    {"key": "verdant", "tier": TRINKET, "kind": "theme",
     "name": "Verdant", "detail": "loam and moss",
     "need": {"raised": 50}},
    {"key": "the_garden", "tier": LANDMARK, "kind": "environment",
     "name": "The Garden", "detail": "the tank overgrows",
     "need": {"raised": 150, "contented": 12}},

    # --------------------------------------------------------------- rarity --
    {"key": "starlit", "tier": LANDMARK, "kind": "adornment",
     "name": "Starlit", "detail": "a five-star daemon at Mega wears its rarity",
     "need": {"five_star_mega": 1}},
    {"key": "unbroken", "tier": LANDMARK, "kind": "title",
     "name": "Unbroken", "detail": "an incursion held without ever losing one",
     "need": {"wards": 5, "no_falls": True}},
    {"key": "lineage", "tier": LANDMARK, "kind": "adornment",
     "name": "Lineage", "detail": "ascended daemons trail their rank",
     "need": {"max_rank": 5}},
    {"key": "mastered_one", "tier": LANDMARK, "kind": "theme",
     "name": "Mastered", "detail": "white on black — a rift known completely",
     "need": {"max_mastery": 99}},
    {"key": "folded", "tier": LANDMARK, "kind": "environment",
     "name": "Folded", "detail": "the aether, seen from outside",
     "need": {"cycles": 2}},
]
BY_KEY = {a["key"]: a for a in AWARDS}


# --------------------------------------------------------------- measuring --
def _context() -> dict:
    from . import reformat
    roster = db.list_daemons()
    devices = db.list_devices()
    mx = db.all_mastery_xp()
    levels = [mastery.level_from_xp(x) for x in mx.values()]

    first = db.get_meta("instance_started", "")
    if not first:
        db.set_meta("instance_started", str(time.time()))
        first = str(time.time())
    days = (time.time() - float(first)) / 86400.0

    contented = sum(1 for d in roster
                    if d.care.get("hunger", 0) > 70
                    and d.care.get("happiness", 0) > 70
                    and d.care.get("corruption", 100) < 25)
    falls = sum(1 for e in db.list_events(4000) if e["kind"] == "incursion_fall")
    wards = sum(db.get_progress(d["mac"])["ward"] for d in devices)

    return {
        "layers": db.total_layers_cleared(),
        "rifts": len(devices),
        "mastery_total": sum(levels),
        "max_mastery": max(levels, default=0),
        "days": days,
        "raised": int(float(db.get_meta("daemons_raised", "0") or 0)),
        "contented": contented,
        "max_rank": max((getattr(d, "ascensions", 0) for d in roster), default=0),
        "five_star_mega": sum(1 for d in roster
                              if d.rarity >= 5 and d.stage == "Mega"),
        "wards": wards,
        "no_falls": falls == 0,
        "cycles": reformat.cycles(),
    }


def _meets(need: dict, ctx: dict) -> bool:
    for k, v in need.items():
        have = ctx.get(k, 0)
        if isinstance(v, bool):
            if bool(have) != v:
                return False
        elif have < v:
            return False
    return True


def earned() -> set[str]:
    raw = db.get_meta("awards", "")
    return set(filter(None, raw.split(","))) if raw else set()


def evaluate() -> list[dict]:
    """Grant anything newly deserved. Returns what was just earned."""
    have, ctx = earned(), _context()
    fresh = []
    for a in AWARDS:
        if a["key"] in have:
            continue
        if _meets(a["need"], ctx):
            have.add(a["key"])
            fresh.append(a)
    if fresh:
        db.set_meta("awards", ",".join(sorted(have)))
        for a in fresh:
            db.add_event("award",
                         f"{'A landmark' if a['tier'] == LANDMARK else 'Unlocked'}: "
                         f"{a['name']} — {a['detail']}.")
    return fresh


def _progress_line(need: dict, ctx: dict) -> str:
    bits = []
    for k, v in need.items():
        if isinstance(v, bool):
            continue
        have = ctx.get(k, 0)
        have = int(have) if k != "days" else round(have, 1)
        bits.append(f"{have}/{v}")
    return " · ".join(bits)


def state() -> dict:
    """Everything the wardrobe needs.

    Trinket requirements are shown, since they work as goals. Landmarks are
    withheld until earned — a rare thing you knew was coming isn't a discovery.
    """
    have, ctx = earned(), _context()
    active = {k: v for k, v in
              (p.split(":", 1) for p in
               filter(None, db.get_meta("cosmetics", "").split(",")) if ":" in p)}
    out = []
    for a in AWARDS:
        got = a["key"] in have
        row = {"key": a["key"], "tier": a["tier"], "kind": a["kind"],
               "earned": got}
        if got:
            row |= {"name": a["name"], "detail": a["detail"]}
        elif a["tier"] == TRINKET:
            row |= {"name": a["name"], "detail": a["detail"],
                    "progress": _progress_line(a["need"], ctx)}
        else:
            row |= {"name": "???", "detail": "an unearned landmark"}
        out.append(row)
    return {"awards": out, "active": active,
            "counts": {"earned": len(have), "total": len(AWARDS),
                       "landmarks": sum(1 for a in AWARDS
                                        if a["tier"] == LANDMARK and a["key"] in have)}}


def set_active(kind: str, key: str | None) -> dict:
    """Apply or clear one cosmetic slot. Nothing auto-applies — a reward you
    didn't choose to wear isn't much of a reward."""
    active = {k: v for k, v in
              (p.split(":", 1) for p in
               filter(None, db.get_meta("cosmetics", "").split(",")) if ":" in p)}
    if key is None:
        active.pop(kind, None)
    else:
        a = BY_KEY.get(key)
        if not a or a["kind"] != kind or key not in earned():
            return {"ok": False, "reason": "not_earned"}
        active[kind] = key
    db.set_meta("cosmetics", ",".join(f"{k}:{v}" for k, v in sorted(active.items())))
    return {"ok": True, "active": active}
