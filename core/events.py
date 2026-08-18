"""
events.py — Small things that happen in a rift while you're not looking.

A game measured in months has long quiet stretches. These are the texture in
them: a seam of rich ore that pays better for a day, a collapse that costs you
a layer, a stranger that offers to join. Frequent enough to be worth checking
the Pulse for, small enough that none of them demands anything.

Nothing here can lose you a daemon or destroy real progress. The worst outcome
is a layer to re-dig — annoying for an evening, meaningless over a year — and
that is deliberate: an idle game that punishes absence isn't idle.
"""

from __future__ import annotations

import os
import time

from . import db
from .seed import Rng, _digest

CHECK_EVERY_H = float(os.environ.get("AETHER_EVENT_CHECK_H", "6"))
CHANCE_PER_CHECK = float(os.environ.get("AETHER_EVENT_CHANCE", "0.30"))
SEAM_HOURS = float(os.environ.get("AETHER_SEAM_HOURS", "20"))
SEAM_MULT = float(os.environ.get("AETHER_SEAM_MULT", "1.6"))


def active_seam(mac: str) -> float:
    """Yield multiplier from any seam currently running on this rift."""
    raw = db.get_meta(f"seam:{mac}", "")
    if not raw:
        return 1.0
    try:
        until = float(raw)
    except ValueError:
        return 1.0
    return SEAM_MULT if time.time() < until else 1.0


def seam_remaining(mac: str) -> float:
    raw = db.get_meta(f"seam:{mac}", "")
    try:
        return max(0.0, (float(raw) - time.time()) / 3600.0) if raw else 0.0
    except ValueError:
        return 0.0


def _roll_event(mac: str, now: float) -> dict | None:
    from . import world, mastery
    prog = db.get_progress(mac)
    depth = prog["cleared"]
    if depth < 5:
        return None                      # nothing happens in a shallow rift

    rift = world.generate_rift(mac)
    r = Rng(_digest("aether.event", mac, str(int(now / 3600))))
    roll = r.random()
    name = rift["world_name"]

    # a seam: better yields here for a while
    if roll < 0.45:
        if seam_remaining(mac) > 0:
            return None
        db.set_meta(f"seam:{mac}", str(now + SEAM_HOURS * 3600))
        return {"kind": "seam",
                "text": f"A seam of rich ore opens in {name}. Everything posted "
                        f"here yields {SEAM_MULT:g}x for the next "
                        f"{SEAM_HOURS:.0f} hours."}

    # a collapse: one layer must be retaken
    if roll < 0.72:
        if depth < 12:
            return None
        db.set_progress_fields(mac, cleared=max(1, depth - 1))
        return {"kind": "collapse",
                "text": f"Layer {depth} of {name} has caved in. The ground must "
                        f"be retaken — nothing was lost but the digging."}

    # a stranger: a wild daemon offers to join, waiting until you accept
    if roll < 0.90:
        pending = db.get_meta("stranger", "")
        if pending:
            return None
        mile = max(1, depth // world.CAPTURE_EVERY)
        db.set_meta("stranger", f"{mac}|{mile}|{int(now)}")
        return {"kind": "stranger",
                "text": f"Something followed your daemons up out of {name}. It "
                        f"is waiting in the Nest, and does not seem to be in a "
                        f"hurry."}

    # a quiet spell: mastery comes faster here for a while
    db.add_mastery_xp(mac, mastery.xp_for_clear(depth, False) * 4)
    return {"kind": "insight",
            "text": f"Your daemons read something in the walls of {name}. "
                    f"You understand this rift a little better."}


def tick(now: float | None = None):
    """Called from the heartbeat. Checks rarely, and only where you're active."""
    now = now or time.time()
    last = float(db.get_meta("event_tick", "0") or 0)
    if last and now - last < CHECK_EVERY_H * 3600:
        return
    db.set_meta("event_tick", str(now))
    if not last:
        return

    # only rifts you are actually working
    macs = {h["mac"] for h in db.list_harvests()}
    macs |= {e["mac"] for e in db.list_expeditions()}
    if not macs:
        return
    r = Rng(_digest("aether.eventroll", str(int(now))))
    for mac in sorted(macs):
        if r.random() > CHANCE_PER_CHECK:
            continue
        ev = _roll_event(mac, now)
        if ev:
            db.add_event(ev["kind"], ev["text"], mac=mac)


def pending_stranger() -> dict | None:
    raw = db.get_meta("stranger", "")
    if not raw:
        return None
    try:
        mac, mile, when = raw.split("|")
        from . import world
        rift = world.generate_rift(mac)
        return {"mac": mac, "milestone": int(mile), "since": float(when),
                "world": rift["world_name"]}
    except Exception:
        return None


def take_stranger():
    """Accept the wild daemon that has been waiting."""
    p = pending_stranger()
    if not p:
        return {"ok": False, "reason": "none"}
    from . import world
    prog = db.get_progress(p["mac"])
    d = world.capture_daemon(p["mac"], p["milestone"], prog["tier"])
    d.id = None
    d.born = time.time()
    d.origin_layer = p["milestone"] * world.CAPTURE_EVERY
    new_id = db.add_daemon(d)
    db.bump_raised()
    db.set_meta("stranger", "")
    db.add_event("stranger_join",
                 f"{d.name} settles into the Nest as though it had always been "
                 f"there.", daemon_id=new_id)
    return {"ok": True, "daemon_id": new_id, "name": d.name}
