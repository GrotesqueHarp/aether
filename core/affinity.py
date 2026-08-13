"""
affinity.py — What a daemon likes, and who it likes working with.

Assignment used to be sorting by power. This makes it an act of knowing them:
a daemon posted in a biome it favours works visibly better, one put on a job it
dislikes sulks and underperforms, and two that fight or work together long
enough form a bond that outlasts any single posting.

Preferences are DERIVED from the seed, like traits — the same creature always
wants the same things, and every daemon you already own has always had them.
Bonds are earned, so they need storing.

The numbers are real, not decorative. A well-matched roster is meaningfully
better than a well-optimised one, which is the point: it should be worth
building around who these creatures are.
"""

from __future__ import annotations

import os

from . import content
from .seed import Rng, _digest

BIOME_KEYS = list(content.BIOMES)
JOBS = ("harvest", "training", "expedition", "battle")
JOB_LABEL = {"harvest": "working a shelf", "training": "the training halls",
             "expedition": "expeditions", "battle": "fighting"}

LIKED_BIOME_BONUS = float(os.environ.get("AETHER_LIKED_BIOME", "0.18"))
LIKED_JOB_BONUS = float(os.environ.get("AETHER_LIKED_JOB", "0.15"))
DISLIKED_JOB_PENALTY = float(os.environ.get("AETHER_DISLIKED_JOB", "0.12"))

# how long two daemons must share work before a bond forms, in hours
BOND_HOURS = float(os.environ.get("AETHER_BOND_HOURS", "48"))
BOND_MAX = 3
BOND_BONUS = float(os.environ.get("AETHER_BOND_BONUS", "0.07"))


def preferences(daemon) -> dict:
    """One favoured biome, one favoured job, one disliked job."""
    seed = getattr(daemon, "seed", None)
    if not seed:
        return {"biome": None, "likes": None, "dislikes": None}
    r = Rng(_digest("aether.affinity", seed))
    biome = BIOME_KEYS[r.randint(0, len(BIOME_KEYS) - 1)]
    jobs = list(JOBS)
    likes = jobs.pop(r.randint(0, len(jobs) - 1))
    dislikes = jobs[r.randint(0, len(jobs) - 1)]
    return {"biome": biome, "likes": likes, "dislikes": dislikes}


def describe(daemon) -> dict:
    p = preferences(daemon)
    if not p["biome"]:
        return p
    return p | {
        "biome_name": content.BIOMES[p["biome"]]["name"],
        "likes_label": JOB_LABEL.get(p["likes"], p["likes"]),
        "dislikes_label": JOB_LABEL.get(p["dislikes"], p["dislikes"]),
    }


def job_mult(daemon, job: str) -> float:
    """Multiplier for doing this kind of work."""
    p = preferences(daemon)
    m = 1.0
    if p["likes"] == job:
        m += LIKED_JOB_BONUS
    if p["dislikes"] == job:
        m -= DISLIKED_JOB_PENALTY
    return max(0.5, m)


def biome_mult(daemon, biome_key: str) -> float:
    return 1.0 + LIKED_BIOME_BONUS if preferences(daemon)["biome"] == biome_key else 1.0


def contentment(daemon, job: str | None, biome_key: str | None) -> int:
    """How well this posting suits them, -1 unhappy, 0 fine, +1 delighted.
    Used by moods, so a daemon can eventually say so."""
    p = preferences(daemon)
    score = 0
    if job and p["likes"] == job:
        score += 1
    if job and p["dislikes"] == job:
        score -= 1
    if biome_key and p["biome"] == biome_key:
        score += 1
    return max(-1, min(1, score))


# ------------------------------------------------------------------ wishes --
# A daemon may occasionally want something. These are notes in the Pulse, not
# timers: nothing expires, nothing is lost by ignoring them, and honouring one
# is a small kindness rather than a chore. Checked rarely so they stay
# meaningful — a creature that constantly asks is nagging, not characterful.
WISH_COOLDOWN_H = float(os.environ.get("AETHER_WISH_COOLDOWN_H", "72"))
RESTLESS_H = float(os.environ.get("AETHER_RESTLESS_H", "336"))   # two weeks


def check_wishes(now: float) -> list[dict]:
    """Look for daemons with something to say. Returns any new wishes."""
    from . import db
    last = float(db.get_meta("wish_tick", "0") or 0)
    if last and now - last < WISH_COOLDOWN_H * 3600:
        return []
    db.set_meta("wish_tick", str(now))
    if not last:
        return []

    out = []
    for d in db.list_daemons():
        p = preferences(d)
        hv = db.get_harvest(d.id)
        tr = db.get_training(d.id)

        # posted somewhere it dislikes, and has been a while
        job = "harvest" if hv else "training" if tr else None
        if job and p["dislikes"] == job:
            out.append({"daemon_id": d.id, "name": d.name, "kind": "dislikes",
                        "text": f"{d.name} would rather not be "
                                f"{JOB_LABEL[job]} — it favours "
                                f"{JOB_LABEL[p['likes']]}."})
            continue

        # a long stint in one place
        started = (hv or tr or {}).get("started")
        if started and (now - started) > RESTLESS_H * 3600:
            weeks = int((now - started) / (7 * 86400))
            out.append({"daemon_id": d.id, "name": d.name, "kind": "restless",
                        "text": f"{d.name} has held the same post for "
                                f"{weeks} weeks and has grown restless."})
            continue

        # separated from someone it's bonded to
        for b in bonds_for(d.id):
            other_busy = db.get_harvest(b["id"]) or db.get_expedition(b["id"])
            mine = hv or db.get_expedition(d.id)
            if b["level"] >= 2 and mine and other_busy and \
                    mine.get("mac") != other_busy.get("mac"):
                out.append({"daemon_id": d.id, "name": d.name, "kind": "misses",
                            "text": f"{d.name} keeps drifting toward the edge "
                                    f"of the Nest, watching for {b['name']}."})
                break

    for w in out[:2]:                      # never more than a couple at once
        db.add_event("wish", w["text"], daemon_id=w["daemon_id"])
    return out[:2]


# ------------------------------------------------------------------- bonds --
def _key(a: int, b: int) -> str:
    return f"{min(a, b)}:{max(a, b)}"


def all_bonds() -> dict:
    from . import db
    raw = db.get_meta("bonds", "")
    out = {}
    for part in filter(None, raw.split(",")):
        try:
            k, v = part.rsplit("=", 1)
            out[k] = float(v)
        except ValueError:
            continue
    return out


def _save(bonds: dict):
    from . import db
    db.set_meta("bonds", ",".join(f"{k}={round(v, 2)}" for k, v in bonds.items()
                                  if v > 0.01))


def level(a: int, b: int) -> int:
    """0 to BOND_MAX. Hours shared, on a curve so the first tier comes soonest."""
    hours = all_bonds().get(_key(a, b), 0.0)
    if hours < BOND_HOURS:
        return 0
    return min(BOND_MAX, 1 + int((hours - BOND_HOURS) / (BOND_HOURS * 2.5)))


def add_time(ids: list[int], hours: float):
    """Credit shared time to every pair in a group."""
    if hours <= 0 or len(ids) < 2:
        return
    bonds = all_bonds()
    fired = []
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            k = _key(a, b)
            before = min(BOND_MAX, max(0, 1 + int((bonds.get(k, 0) - BOND_HOURS)
                                                  / (BOND_HOURS * 2.5)))
                         if bonds.get(k, 0) >= BOND_HOURS else 0)
            bonds[k] = bonds.get(k, 0.0) + hours
            after = min(BOND_MAX, max(0, 1 + int((bonds[k] - BOND_HOURS)
                                                 / (BOND_HOURS * 2.5)))
                        if bonds[k] >= BOND_HOURS else 0)
            if after > before:
                fired.append((a, b, after))
    _save(bonds)
    if fired:
        from . import db
        for a, b, lvl in fired:
            da, dbm = db.get_daemon(a), db.get_daemon(b)
            if da and dbm:
                db.add_event("bond",
                             f"{da.name} and {dbm.name} have worked together "
                             f"long enough to trust each other"
                             f"{' completely' if lvl >= BOND_MAX else ''}.")


def party_bonus(party: list) -> float:
    """Summed bond bonus for a group fighting together."""
    ids = [d.id for d in party if getattr(d, "id", None)]
    total = 0.0
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            total += BOND_BONUS * level(a, b)
    return total


def bonds_for(daemon_id: int) -> list[dict]:
    from . import db
    out = []
    for k, hours in all_bonds().items():
        a, b = (int(x) for x in k.split(":"))
        if daemon_id not in (a, b):
            continue
        other = db.get_daemon(b if a == daemon_id else a)
        lvl = level(a, b)
        if other and lvl > 0:
            out.append({"id": other.id, "name": other.name, "level": lvl,
                        "hours": round(hours, 1)})
    return sorted(out, key=lambda x: -x["level"])
