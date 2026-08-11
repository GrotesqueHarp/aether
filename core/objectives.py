"""
objectives.py — The Compass.

A tutorial nobody has to read. Each objective names one thing to do, explains
*why* the mechanic exists, and completes itself when the game state says so —
no modal, no blocking, no "click here" arrows. You can ignore the whole thing
and play; it just quietly ticks along beside you.

Early chapters teach the loop. Later ones stop being a tutorial and become
long-term goals, which is why this doubles as the milestone system: there's no
clean line between "learning the game" and "playing it" in something meant to
last a year.

Conditions read live state rather than remembering that you pressed a button,
so nothing can be missed by doing things out of order — arrive at the state and
it's done, however you got there.
"""

from __future__ import annotations

import json

CHAPTERS = [
    ("first-light", "First Light", "Finding your footing."),
    ("the-work", "The Work", "Building something that runs without you."),
    ("the-bastion", "The Bastion", "Machines that raise your daemons for you."),
    ("deeper", "Deeper", "The shaft goes down a hundred layers."),
    ("the-long-game", "The Long Game", "Years, not evenings."),
]

# id, chapter, title, why (the teaching), how (the doing), condition(ctx)
OBJECTIVES = [
    ("hatch", "first-light", "Hatch your Anchor daemon",
     "Every daemon is generated from a seed, so yours is genuinely yours — the "
     "same seed always grows the same creature.",
     "Press the button on the welcome screen.",
     lambda c: c["roster"] >= 1),

    ("scan", "first-light", "Sweep with the Array",
     "Rifts are seeded from the MAC addresses of real devices on your network, "
     "so your router and your TV each generate their own world. When real "
     "hardware runs out, the Array resolves rifts from open subspace instead.",
     "Rifts → Sweep with the Array.",
     lambda c: c["devices"] >= 1),

    ("dig", "first-light", "Dig your first layer",
     "A rift is a shaft a hundred layers deep. Layers must be taken in order, "
     "and they get harder the further down you go.",
     "Open a rift and press Descend.",
     lambda c: c["layers_dug"] >= 1),

    ("shelf", "first-light", "Reach your first shelf at layer 5",
     "Every fifth layer is a shelf — a place a daemon can be posted to work.",
     "Keep descending until you clear layer 5.",
     lambda c: c["max_depth"] >= 5),

    ("post", "the-work", "Post a daemon on a shelf",
     "This is the whole economy. A posted daemon earns resources continuously, "
     "awake or asleep, tab open or closed. Battle drops are a trickle by "
     "comparison — a post out-earns a layer clear in about sixteen minutes.",
     "On a rift, pick a harvest post and assign a daemon.",
     lambda c: c["harvesters"] >= 1),

    ("egg", "the-work", "Synthesise an egg",
     "Essence comes from harvesting, and its type depends on the rift's biome. "
     "Eggs take real hours to hatch, and the element you feed in biases what "
     "comes out.",
     "The Nest → Hatchery → pick an essence.",
     lambda c: c["eggs_ever"] >= 1),

    ("care", "the-work", "Keep a daemon fed",
     "Care meters feed battle stats directly. Hunger and energy drain over "
     "time; energy refills on its own when a daemon is idle, but hunger does "
     "not — not until you automate it.",
     "The Nest → Feed.",
     lambda c: c["fed"]),

    ("capture", "the-work", "Draw a daemon from a shelf",
     "Every tenth layer offers one daemon, once. Deeper shelves give better "
     "ones, and Overclocking a rift refreshes them all.",
     "Reach layer 10, then use the signature daemon panel.",
     lambda c: c["captures"] >= 1),

    ("facility", "the-bastion", "Build your first facility",
     "The Bastion is where the game stops needing you. Everything here trades "
     "resources for attention you no longer have to spend.",
     "Bastion → Build anything.",
     lambda c: c["facility_levels"] >= 1),

    ("feeder", "the-bastion", "Build the Auto-Feeder",
     "It doesn't just slow hunger — it actively puts food out. From about "
     "level 2 it outpaces the drain entirely, and you never click Feed again.",
     "Bastion → Auto-Feeder.",
     lambda c: c["facilities"].get("auto_feeder", 0) >= 1),

    ("hall", "the-bastion", "Train a daemon in a hall",
     "Hand-training gives one stat point and costs most of a daemon's energy. "
     "A level-1 hall beats it four times over and never stops. Halls are the "
     "answer to clicking.",
     "Build a hall (the Forge, say), then enrol a daemon.",
     lambda c: c["trainees"] >= 1 or c["hall_ever"]),

    ("expedition", "deeper", "Send an expedition",
     "A hundred layers across every rift is not something you hand-fight. "
     "Expeditions dig on their own while the tab is closed — this is how the "
     "shaft actually gets dug.",
     "On a rift, dispatch a daemon on an expedition.",
     lambda c: c["expeditions_ever"]),

    ("crucible", "deeper", "Transmute at the Crucible",
     "Which essences you can earn depends on what hardware you happen to own. "
     "The Crucible converts one into another at a loss, so nothing is ever "
     "permanently out of reach.",
     "Bastion → Crucible → transmute.",
     lambda c: c["transmuted"]),

    ("gatekeeper", "deeper", "Defeat a Gatekeeper",
     "Every twenty-fifth layer holds one. They hit hard and bring company, so "
     "this is usually where a single daemon stops being enough and a party of "
     "three starts.",
     "Dig to layer 25.",
     lambda c: c["max_depth"] >= 25),

    ("glyph", "deeper", "Strike a glyph",
     "Glyphs decide what a daemon is *for* — a Harvest glyph is worthless in a "
     "fight, a Forge glyph worthless on a shelf. Quality is paid for, never "
     "rolled.",
     "Bastion → Glyphs.",
     lambda c: c["glyphs"] >= 1),

    ("mastery10", "the-long-game", "Bring a rift to mastery 10",
     "Every rift has its own 1–99 track earned by digging and harvesting it. "
     "Level 10 makes expeditions there dig a quarter faster; 99 takes about "
     "eight months.",
     "Keep working one rift's shelves.",
     lambda c: c["max_mastery"] >= 10),

    ("array2", "the-long-game", "Upgrade the Array",
     "More rifts is the strongest thing you can do — Resonance scales off the "
     "*sum* of mastery across every rift, so twenty modest rifts beat one "
     "perfect one. The Array is gated on lifetime layers dug, not money.",
     "Bastion → The Array.",
     lambda c: c["facilities"].get("array", 0) >= 1),

    ("depth50", "the-long-game", "Reach layer 50",
     "Halfway down. Yields climb steeply with depth, so the back half of a "
     "shaft is worth far more than the front.",
     "Keep digging.",
     lambda c: c["max_depth"] >= 50),

    ("incursion", "the-long-game", "Hold off the Null",
     "Harvesting a stabilised rift eventually attracts something. You get "
     "twelve to twenty-four hours to post a garrison. Losing costs progress — "
     "never daemons.",
     "Garrison a rift when an incursion appears.",
     lambda c: c["incursion_win"]),

    ("ascend", "the-long-game", "Ascend a daemon",
     "At Mega and level 60 a daemon can be unmade back to a Hatchling, keeping "
     "its name and gaining a permanent +18% to everything, compounding. Enemy "
     "tiers scale exponentially; this is how you keep up.",
     "The Nest → Ascend.",
     lambda c: c["max_ascension"] >= 1),

    ("overclock", "the-long-game", "Overclock a rift",
     "Dig all hundred layers and a rift can be pushed a tier higher: everything "
     "harder, everything richer, shelves refreshed. If you overreach, Downclock "
     "steps it back — nothing here is unrecoverable.",
     "Clear layer 100, then Overclock.",
     lambda c: c["max_tier"] >= 1),
]


TOPICS = [
    ("The Array and rifts",
     "Each rift is generated from a device's MAC address, so the same hardware "
     "always produces the same world. The Array decides how many you can hold "
     "resolved at once; real devices are found first, then deep-signal rifts "
     "from open subspace. Once found, a rift is yours permanently — nothing "
     "goes dormant when a device leaves the network."),
    ("The descent",
     "100 layers per rift. Gatekeepers every 25, a capture shelf every 10, a "
     "harvest post every 5. Deeper layers mean more foes per fight (up to four) "
     "and steeply better harvest yields. Layers must be taken in order."),
    ("Where resources come from",
     "Harvest posts, overwhelmingly. Clearing a layer drops a trickle; a posted "
     "daemon out-earns a whole layer clear in about a quarter of an hour and "
     "keeps going while you're away. Bits are universal, essence comes in six "
     "biome flavours, Cores gate facilities past level 4, and Aethercite comes "
     "only from repelling the Null."),
    ("Care, and automating it",
     "Daemons get hungry, tired, unhappy and corrupted, and those meters feed "
     "their battle stats. You can tend them by hand, but the intent is that you "
     "stop: the Auto-Feeder restores hunger, the Playroom holds a happiness "
     "floor, the Cleansing Font drains corruption, and energy refills on its own "
     "whenever a daemon isn't posted to a job."),
    ("The Bastion",
     "Four training halls raise a stat permanently per hour, with rates that "
     "compound per level. The Hatchery Wing speeds incubation, the Aegis "
     "strengthens defenders, the Array resolves rifts, and the automations tend "
     "your Nest. Costs rise ~1.55x per level, so every purchase is a choice."),
    ("The Crucible",
     "Converts essence between types at a loss, and grinds essence plus Bits "
     "into Cores. It exists because which essences you can earn depends on what "
     "hardware you happen to own — without it, a network with no Bazaar device "
     "could never build anything needing Plasma."),
    ("Glyphs",
     "Craftable equipment: ATK, DEF, HP, SPD, plus harvest yield, XP gain and "
     "training rate, at quality 1–5. Slots come from what a daemon has been "
     "through — 1 at Hatchling, 2 at Champion, 3 at Mega, plus one at ascension "
     "ranks 3 and 6."),
    ("Ascension",
     "Vertical progression. A maxed daemon returns to a Hatchling and gains a "
     "permanent lineage rank worth +18% to all stats, compounding. It keeps its "
     "seed and name, so it stays recognisably the creature you raised."),
    ("Rift Mastery and Resonance",
     "Mastery is per rift, 1–99, earned by digging and harvesting it, with "
     "milestones at 10, 25, 50, 75 and 99. Resonance is global, drawn from the "
     "sum of mastery across every rift — twenty rifts at 25 beat one at 99, so "
     "breadth pays."),
    ("The Null",
     "Working a stabilized rift draws attention. An incursion spawns with a "
     "12–24 hour deadline; post a garrison (harvesters can defend where they "
     "stand) or repel it early. Holding raises a permanent Ward and pays "
     "Aethercite. Losing costs progress and wards — never daemons."),
    ("Overclock",
     "The endless loop. A fully dug rift resets a tier higher: enemies 1.6x "
     "stronger, yields doubled, and a fresh set of capture shelves. It costs "
     "Cores, and Downclock takes you back if you overreach."),
    ("What to do while away",
     "Everything continues: posts harvest, halls train, eggs hatch, expeditions "
     "dig, incursions count down. Come back and the summary tells you what "
     "happened. Records charts the long curve — this is a game measured in "
     "months, and a resource bar can't show you that."),
]


# Reference, as distinct from objectives. Objectives tell you what to do next;
# this tells you how the machine works, and stays useful when you come back
# after a fortnight and can't remember what Aethercite was for.
def _context() -> dict:
    from . import db, mastery
    daemons = db.list_daemons()
    devices = db.list_devices()
    progresses = [db.get_progress(d["mac"]) for d in devices]
    kinds = {e["kind"] for e in db.list_events(3000)}
    return {
        "roster": len(daemons),
        "devices": len(devices),
        "layers_dug": db.total_layers_cleared(),
        "max_depth": max([p["cleared"] for p in progresses], default=0),
        "max_tier": max([p["tier"] for p in progresses], default=0),
        "captures": sum(p["captures_taken"] for p in progresses),
        "max_mastery": max([mastery.level_from_xp(p.get("mastery_xp", 0))
                            for p in progresses], default=1),
        "harvesters": len(db.list_harvests()),
        "trainees": len(db.list_training()),
        # only counts a deliberate synthesis — the starter Kernel hatches from
        # the Anchor egg, which would otherwise tick this on turn one
        "eggs_ever": "egg_laid" in kinds,
        "fed": "care" in kinds or any(d.care.get("hunger", 0) > 70 for d in daemons),
        "facilities": db.all_facility_levels(),
        "facility_levels": sum(db.all_facility_levels().values()),
        "hall_ever": "train_start" in kinds,
        "expeditions_ever": "expedition" in kinds or bool(db.list_expeditions()),
        "transmuted": "transmute" in kinds or "reclaim" in kinds,
        "glyphs": len(db.list_glyphs()),
        "incursion_win": "incursion_win" in kinds,
        "max_ascension": max([getattr(d, "ascensions", 0) for d in daemons], default=0),
    }


def evaluate() -> dict:
    """Check every objective, persist newly completed ones, and report."""
    from . import db
    ctx = _context()
    try:
        done = set(json.loads(db.get_meta("objectives_done", "[]") or "[]"))
    except ValueError:
        done = set()

    newly = []
    out = []
    for oid, chapter, title, why, how, cond in OBJECTIVES:
        try:
            complete = bool(cond(ctx))
        except Exception:
            complete = False
        if complete and oid not in done:
            done.add(oid)
            newly.append(title)
        out.append({"id": oid, "chapter": chapter, "title": title,
                    "why": why, "how": how, "done": oid in done})
    if newly:
        db.set_meta("objectives_done", json.dumps(sorted(done)))
        for title in newly:
            db.add_event("objective", f"Compass: {title}.")

    total = len(out)
    complete = sum(1 for o in out if o["done"])
    # what to point at next: the first unfinished objective of each chapter,
    # so the panel stays short instead of listing twenty things at once
    nxt = [o for o in out if not o["done"]][:3]
    return {"objectives": out, "chapters": [
                {"key": k, "name": n, "blurb": b} for k, n, b in CHAPTERS],
            "total": total, "complete": complete, "next": nxt,
            "newly_completed": newly,
            "reference": [{"title": t, "body": b} for t, b in TOPICS]}
