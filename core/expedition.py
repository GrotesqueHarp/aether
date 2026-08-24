"""
expedition.py — what an expedition actually did, gathered up and handed back.

An expedition runs for hours while you are not looking, and until now it left
only a trail of individual Pulse lines — one per fight, scattered among
everything else the world was doing. Scrolling back through forty of those to
work out whether six hours of digging was worth it is not reading a report,
it is doing forensics.

So each expedition keeps a running tally, and when it ends — bottomed out,
routed, or recalled — that tally becomes one summary: how far it got, what it
beat, what it brought home, and how it ended.

The tally lives in `meta` rather than in new columns on the expeditions table,
so this needed no migration. That is the same place bonds and seams live, and
it suits the shape of the thing: it exists only while one expedition is
running, and is deleted the moment the report is written.
"""

from __future__ import annotations

import json
import time

from . import db

KEY = "exped_tally:"
REPORTS_KEY = "exped_reports"
KEEP_REPORTS = 20

# How it ended, and how that reads in the report.
ENDINGS = {
    "done":   "the shaft bottomed out",
    "routed": "routed, and limped home",
    "recall": "recalled",
    "gone":   "lost track of its daemon",
}


def _key(daemon_id: int) -> str:
    return f"{KEY}{daemon_id}"


def begin(daemon_id: int, mac: str, orders: str, start_layer: int):
    db.set_meta(_key(daemon_id), json.dumps({
        "mac": mac, "orders": orders, "started": time.time(),
        "start_layer": start_layer, "layer": start_layer,
        "won": 0, "lost": 0, "layers": 0, "xp": 0, "levels": 0,
        "bosses": 0, "scouted": 0, "rested": 0, "mastery": 0.0,
        "loot": {},
    }))


def get(daemon_id: int) -> dict | None:
    raw = db.get_meta(_key(daemon_id))
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return None


def note(daemon_id: int, *, loot: dict | None = None, **deltas):
    """Add to the running tally. Silently does nothing if the expedition
    started before this feature existed — an in-flight expedition on an
    upgraded install still ends cleanly, just without a report."""
    t = get(daemon_id)
    if t is None:
        return
    for k, v in deltas.items():
        if k == "layer":                      # a position, not a total
            t["layer"] = v
        else:
            t[k] = t.get(k, 0) + v
    for kind, amt in (loot or {}).items():
        t["loot"][kind] = t["loot"].get(kind, 0) + amt
    db.set_meta(_key(daemon_id), json.dumps(t))


def _phrase(t: dict, reason: str, name: str, world: str) -> str:
    hours = max(0.0, (time.time() - t["started"]) / 3600.0)
    dur = (f"{hours*60:.0f} minutes" if hours < 1.5
           else f"{hours:.1f} hours" if hours < 48
           else f"{hours/24:.1f} days")
    bits = [f"{name} returns from {world} after {dur}"]

    if t["orders"] == "scout":
        bits.append(f"mapping {t['scouted']} stretch(es) of ground")
    elif t["layers"]:
        bits.append(f"digging {t['layers']} layer(s) to reach layer {t['layer']}")
    elif t["orders"] == "farm":
        bits.append(f"working layer {t['layer']}")
    else:
        bits.append("without gaining ground")

    if t["won"] or t["lost"]:
        rec = f"{t['won']} win(s)"
        if t["lost"]:
            rec += f", {t['lost']} loss(es)"
        if t["bosses"]:
            rec += f", {t['bosses']} Gatekeeper(s) felled"
        bits.append(rec)

    if t["xp"]:
        bits.append(f"+{t['xp']} XP" + (f" and {t['levels']} level(s)"
                                        if t["levels"] else ""))
    if t["loot"]:
        bits.append("carrying " + ", ".join(
            f"{v:g} {k.replace('essence.', '')}"
            for k, v in sorted(t["loot"].items())))
    if t["rested"]:
        bits.append(f"resting {t['rested']} time(s) along the way")

    return " — ".join([bits[0] + ", " + bits[1]] + bits[2:]) + \
        f". ({ENDINGS.get(reason, reason)})"


def finish(daemon_id: int, reason: str, name: str = "", world: str = "",
           mac: str = "") -> dict | None:
    """Turn the tally into one Pulse line and one stored report, then clear it.

    Called from every path that ends an expedition, so a report is never
    silently skipped — including the routed and recalled cases, which are
    exactly the ones you most want to read.
    """
    t = get(daemon_id)
    db.set_meta(_key(daemon_id), "")
    if not t:
        return None
    report = {
        "daemon_id": daemon_id, "daemon": name,
        "mac": mac or t.get("mac", ""), "world": world,
        "orders": t["orders"], "reason": reason,
        "started": t["started"], "finished": time.time(),
        "start_layer": t["start_layer"], "end_layer": t["layer"],
        "layers": t["layers"], "won": t["won"], "lost": t["lost"],
        "bosses": t["bosses"], "xp": t["xp"], "levels": t["levels"],
        "scouted": t["scouted"], "rested": t["rested"],
        "mastery": round(t.get("mastery", 0.0), 1),
        "loot": t["loot"],
    }
    if name and world:
        db.add_event("exped_report", _phrase(t, reason, name, world),
                     mac=report["mac"], daemon_id=daemon_id)
    _store(report)
    return report


def _store(report: dict):
    try:
        recent = json.loads(db.get_meta(REPORTS_KEY) or "[]")
    except (TypeError, ValueError):
        recent = []
    recent.insert(0, report)
    db.set_meta(REPORTS_KEY, json.dumps(recent[:KEEP_REPORTS]))


def recent(limit: int = 10) -> list[dict]:
    try:
        return json.loads(db.get_meta(REPORTS_KEY) or "[]")[:limit]
    except (TypeError, ValueError):
        return []
