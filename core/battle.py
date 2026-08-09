"""
battle.py — The auto-battler.

You don't pick moves. You raised the daemon; now you watch it fight. A battle
is a deterministic (seeded) exchange of turns driven entirely by the two
daemons' stats, attributes, and elements. This returns a full turn-by-turn log
so the UI can animate the fight and the player can see *why* they won or lost —
which is the real feedback loop for the training/care systems.
"""

from __future__ import annotations

from . import content
from .daemon import Daemon
from .seed import Rng, _digest


def type_multiplier(atk: Daemon, dfn: Daemon) -> tuple[float, str]:
    """Combine the attribute triangle (big) and element ring (small)."""
    mult = 1.0
    note = ""
    if content.ATTR_BEATS.get(atk.attribute) == dfn.attribute:
        mult *= 1.5
        note = f"{atk.attribute}▸{dfn.attribute}"
    elif content.ATTR_BEATS.get(dfn.attribute) == atk.attribute:
        mult *= 0.75
    if content.ELEMENT_RING.get(atk.element) == dfn.element:
        mult *= 1.2
        note = (note + " " if note else "") + f"{atk.element}▸{dfn.element}"
    return mult, note


def _hit(rng: Rng, attacker: Daemon, defender: Daemon) -> dict:
    a = attacker.battle_stats()
    d = defender.battle_stats()
    mult, note = type_multiplier(attacker, defender)
    raw = a["atk"] * (100 / (100 + d["def"]))
    variance = 0.85 + rng.random() * 0.30
    crit = rng.chance(0.06 + a["spd"] / 4000)
    dmg = raw * mult * variance * (1.6 if crit else 1.0)
    dmg = max(1, int(round(dmg)))
    return {"dmg": dmg, "crit": crit, "mult": round(mult, 2), "note": note}


def simulate(a: Daemon, b: Daemon, seed_extra: str = "") -> dict:
    """
    Fight a vs b. Returns {winner, log, ...}. Faster daemon acts first each
    round. Deterministic given the two daemons + seed_extra.
    """
    rng = Rng(_digest("aether.battle", a.seed, b.seed, seed_extra))

    hp = {"a": a.battle_stats()["hp"], "b": b.battle_stats()["hp"]}
    max_hp = dict(hp)
    log = []

    order = ("a", "b") if a.battle_stats()["spd"] >= b.battle_stats()["spd"] else ("b", "a")
    fighters = {"a": a, "b": b}

    turn = 0
    while hp["a"] > 0 and hp["b"] > 0 and turn < 60:
        for who in order:
            if hp["a"] <= 0 or hp["b"] <= 0:
                break
            foe = "b" if who == "a" else "a"
            res = _hit(rng, fighters[who], fighters[foe])
            hp[foe] = max(0, hp[foe] - res["dmg"])
            log.append({
                "turn": turn,
                "actor": who,
                "actor_name": fighters[who].name,
                "target": foe,
                "dmg": res["dmg"],
                "crit": res["crit"],
                "mult": res["mult"],
                "note": res["note"],
                "hp_a": hp["a"],
                "hp_b": hp["b"],
            })
        turn += 1

    if hp["a"] <= 0 and hp["b"] <= 0:
        winner = "a" if a.battle_stats()["spd"] >= b.battle_stats()["spd"] else "b"
    elif hp["b"] <= 0:
        winner = "a"
    elif hp["a"] <= 0:
        winner = "b"
    else:  # timeout -> higher remaining HP fraction wins
        winner = "a" if hp["a"] / max_hp["a"] >= hp["b"] / max_hp["b"] else "b"

    return {
        "winner": winner,
        "rounds": turn,
        "max_hp": max_hp,
        "final_hp": hp,
        "log": log,
    }


def simulate_team(team_a: list[Daemon], team_b: list[Daemon],
                  seed_extra: str = "") -> dict:
    """
    Party battle: every combatant acts once per round in global SPD order,
    striking a random living foe. Deterministic given rosters + seed_extra.
    Returns a log the UI can animate: entries carry side+index for both actor
    and target plus a full HP snapshot.
    """
    seeds = ",".join(d.seed for d in team_a) + "|" + ",".join(d.seed for d in team_b)
    rng = Rng(_digest("aether.teambattle", seeds, seed_extra))

    combatants = ([("a", i, d) for i, d in enumerate(team_a)] +
                  [("b", i, d) for i, d in enumerate(team_b)])
    combatants.sort(key=lambda t: -t[2].battle_stats()["spd"])

    hp = {f"{s}{i}": d.battle_stats()["hp"] for s, i, d in combatants}
    max_hp = dict(hp)
    log = []

    def alive(side):
        return [(s, i, d) for s, i, d in combatants
                if s == side and hp[f"{s}{i}"] > 0]

    turn = 0
    while alive("a") and alive("b") and turn < 80:
        for s, i, d in combatants:
            if hp[f"{s}{i}"] <= 0:
                continue
            foes = alive("b" if s == "a" else "a")
            if not foes:
                break
            fs, fi, foe = foes[rng.randint(0, len(foes) - 1)]
            res = _hit(rng, d, foe)
            hp[f"{fs}{fi}"] = max(0, hp[f"{fs}{fi}"] - res["dmg"])
            log.append({
                "turn": turn,
                "actor": f"{s}{i}", "actor_name": d.name,
                "target": f"{fs}{fi}", "target_name": foe.name,
                "dmg": res["dmg"], "crit": res["crit"],
                "mult": res["mult"], "note": res["note"],
                "hp": dict(hp),
            })
        turn += 1

    a_alive, b_alive = bool(alive("a")), bool(alive("b"))
    if a_alive and not b_alive:
        winner = "a"
    elif b_alive and not a_alive:
        winner = "b"
    else:  # timeout or mutual wipe -> higher surviving HP fraction
        frac = lambda side: sum(hp[k] for k in hp if k.startswith(side)) / \
                            max(1, sum(max_hp[k] for k in max_hp if k.startswith(side)))
        winner = "a" if frac("a") >= frac("b") else "b"

    return {"winner": winner, "rounds": turn, "max_hp": max_hp,
            "final_hp": hp, "log": log}
