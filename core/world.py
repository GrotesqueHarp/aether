"""
world.py — Turn a device (MAC + hostname) into an explorable Rift.

The OUI selects the biome; the full MAC seeds habitats, the wild daemons that
roam them, and a linear chain of combat nodes ending in a boss. All
deterministic: re-scanning your network regenerates the exact same worlds.
"""

from __future__ import annotations

from . import content
from .seed import rift_rng, oui, normalize_mac, Rng, _digest
from .daemon import generate_daemon


def _pick_biome(mac: str) -> str:
    o = oui(mac)
    if o in content.OUI_BIOME:
        return content.OUI_BIOME[o]
    # otherwise seed a biome from the manufacturer block so all devices from
    # the same maker share a world flavor
    return Rng(_digest("aether.biome", o)).choice(content.BIOME_KEYS)


def world_name(mac: str) -> str:
    r = rift_rng(mac, "name")
    return f"The {r.choice(content.WORLD_ADJ)} {r.choice(content.WORLD_NOUN)}"


def generate_rift(mac: str, hostname: str = "", vendor: str = "") -> dict:
    """Full world descriptor for a device."""
    mac = normalize_mac(mac)
    biome_key = _pick_biome(mac)
    biome = content.BIOMES[biome_key]
    r = rift_rng(mac)

    # difficulty scales with a seeded "depth" so some devices are tougher rifts
    depth = r.randint(1, 10)

    # habitats: a few themed zones, each favoring the biome's elements
    n_hab = r.randint(2, 4)
    habitats = []
    for i in range(n_hab):
        hr = r.sub("habitat", str(i))
        el = hr.choice(biome["elements"])
        habitats.append({
            "id": i,
            "name": f"{el} {hr.choice(['Sector','Cluster','Node Field','Shoal','Terrace'])}",
            "element": el,
            "density": round(0.4 + hr.random() * 0.6, 2),
        })

    # combat nodes: a linear crawl, difficulty ramping to a boss
    n_nodes = r.randint(4, 7)
    nodes = []
    for i in range(n_nodes):
        nr = r.sub("node", str(i))
        is_boss = (i == n_nodes - 1)
        lvl = depth + i * 2 + (6 if is_boss else 0)
        enemy = generate_daemon(
            nr.sub("enemy"),
            origin_mac=mac,
            favored_elements=biome["elements"],
            min_rarity=(3 if is_boss else 1),
            stage=_stage_for_level(lvl),
        )
        enemy.level = lvl
        if is_boss:
            enemy.name = f"{enemy.name} the Gatekeeper"
        nodes.append({
            "index": i,
            "is_boss": is_boss,
            "enemy_level": lvl,
            "enemy": enemy.to_dict(),
            "reward_xp": 12 + lvl * 4 + (60 if is_boss else 0),
        })

    # the rift's signature wild daemon you can try to capture
    wild = generate_daemon(
        r.sub("signature"), origin_mac=mac,
        favored_elements=biome["elements"], min_rarity=2,
        stage="Rookie",
    )
    wild.level = depth + 3

    return {
        "mac": mac,
        "oui": oui(mac),
        "hostname": hostname or "unknown-host",
        "vendor": vendor or "",
        "world_name": world_name(mac),
        "biome_key": biome_key,
        "biome": biome,
        "depth": depth,
        "habitats": habitats,
        "nodes": nodes,
        "signature_daemon": wild.to_dict(),
    }


def _stage_for_level(lvl: int) -> str:
    if lvl >= 40:
        return "Ultimate"
    if lvl >= 24:
        return "Champion"
    if lvl >= 12:
        return "Rookie"
    if lvl >= 3:
        return "Hatchling"
    return "Hatchling"
