"""
world.py — Turn a device (MAC + hostname) into an explorable Rift.

The OUI selects the biome; the full MAC seeds habitats, the wild daemons that
roam them, and a linear chain of combat nodes ending in a boss. All
deterministic: re-scanning your network regenerates the exact same worlds.
"""

from __future__ import annotations

import os

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


DISCOVERY_DEPTH_STEP = float(os.environ.get("AETHER_DISCOVERY_DEPTH", "1.6"))


def discovery_tier(mac: str) -> int:
    """The Array level this rift was resolved at. Reading it here keeps every
    caller — layer_spec, layer_enemies, harvest rates — automatically aware
    that a late find is a harder world, without threading it through by hand."""
    try:
        from . import db
        dev = db.get_device(mac)
        if dev is None:
            return 0
        return int(dev["found_at"] or 0)
    except Exception:
        return 0


def generate_rift(mac: str, hostname: str = "", vendor: str = "") -> dict:
    """Full world descriptor for a device."""
    mac = normalize_mac(mac)
    biome_key = _pick_biome(mac)
    biome = content.BIOMES[biome_key]
    r = rift_rng(mac)

    # difficulty scales with a seeded "depth" so some devices are tougher rifts
    # seeded base difficulty, plus everything the Array had to reach past to
    # hear this one at all
    depth = r.randint(1, 10) + round(DISCOVERY_DEPTH_STEP * discovery_tier(mac))

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
        "layers": LAYERS,
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


# ---------------------------------------------------------------- layers ----
# A rift is a shaft you dig, not a corridor you walk. Every device has the same
# 100 layers; how hard they hit depends on the rift's seeded depth. Gatekeepers
# stand every 25 layers, and every 10th layer yields one — and only one —
# capturable daemon.
#
# Layers are generated on demand rather than up front: building 100 enemies for
# every rift on every API call would be pure waste when the UI only ever shows
# a handful at a time.
LAYERS = 100
GATEKEEPER_EVERY = 25
CAPTURE_EVERY = 10
# Harvest posts are twice as common as capture shelves. Income is meant to come
# from posted daemons, so the first post has to be reachable by a lone starter
# — otherwise there's nothing to fund the second daemon with.
HARVEST_EVERY = 5


def is_gatekeeper(layer: int) -> bool:
    return layer % GATEKEEPER_EVERY == 0


def foes_at(layer: int) -> int:
    """Deeper layers send more of them. Capped at 4 — parties max out at 3, and
    beyond that a fight stops being winnable no matter how strong you are."""
    return 1 + min(3, max(0, (layer - 1) // 30))


def is_harvest_shelf(layer: int) -> bool:
    return layer % HARVEST_EVERY == 0


def layer_level(depth: int, layer: int, tier: int = 0, mac: str | None = None) -> int:
    # gentle opening: the first ten layers ramp in, so a starter daemon can
    # reach its first harvest post without a party
    # Familiar Ground (mastery 50): ground you know well fights easier
    familiar = 0
    if mac:
        try:
            from . import db, mastery
            if mastery.has(db.get_progress(mac).get("mastery_xp", 0), "familiar"):
                familiar = 2
        except Exception:
            familiar = 0
    ramp = 0.45 + 0.055 * min(layer, 10)
    base = depth + layer * (0.75 + depth * 0.06) * ramp
    return max(1, round(base * (1 + 0.35 * tier)) + tier * 5 - familiar)


def layer_enemies(mac: str, layer: int, tier: int = 0) -> list:
    """The pack waiting on this layer. More foes deeper down, but each one is
    individually softened so total difficulty curves smoothly instead of
    stepping every time the count goes up."""
    mac = normalize_mac(mac)
    rift = generate_rift(mac)
    depth, biome = rift["depth"], rift["biome"]
    n = foes_at(layer)
    boss = is_gatekeeper(layer)
    lvl = layer_level(depth, layer, tier, mac)
    # split the difficulty budget across the pack
    each = max(1, round(lvl / (1 + 0.22 * (n - 1))))

    out = []
    for i in range(n):
        er = rift_rng(mac).sub("layer", str(layer), "foe", str(i))
        lead = (i == 0)
        e = generate_daemon(
            er, origin_mac=mac, favored_elements=biome["elements"],
            min_rarity=(3 if boss and lead else 1),
            stage=_stage_for_level(each))
        e.level = each + (4 if boss and lead else 0)
        if boss and lead:
            e.name = f"{e.name} the Gatekeeper"
        out.append(e)
    return out


def layer_spec(mac: str, layer: int, tier: int = 0) -> dict:
    """Display/reward descriptor for one layer."""
    rift = generate_rift(mac)
    lvl = layer_level(rift["depth"], layer, tier, rift["mac"])
    boss = is_gatekeeper(layer)
    return {
        "layer": layer,
        "is_gatekeeper": boss,
        "enemy_level": lvl,
        "foes": foes_at(layer),
        "capture_layer": layer % CAPTURE_EVERY == 0,
        "harvest_shelf": is_harvest_shelf(layer),
        "reward_xp": int((10 + lvl * 4 + (80 if boss else 0)) * (1 + 0.4 * tier)),
    }


def layer_window(mac: str, cleared: int, tier: int = 0, back: int = 4,
                 ahead: int = 3) -> list:
    """The slice of the shaft worth rendering: a little history for context,
    the frontier, and a peek at what's below."""
    lo = max(1, cleared - back + 1)
    hi = min(LAYERS, cleared + ahead)
    return [layer_spec(mac, L, tier) for L in range(lo, hi + 1)]


def captures_available(cleared: int, taken: int, mastery_xp: float = 0.0) -> int:
    """One capture per 10 layers reached, minus what you've already claimed.

    A rift at mastery 25 ("Echo") gives one extra per tier — knowing a place
    well enough to find what it hides."""
    from . import mastery
    earned = cleared // CAPTURE_EVERY
    if mastery.has(mastery_xp, "echo"):
        earned += 1
    return max(0, earned - taken)


def capture_daemon(mac: str, milestone: int, tier: int = 0):
    """A distinct daemon for each 10-layer milestone, deterministic per rift,
    milestone and tier."""
    mac = normalize_mac(mac)
    rift = generate_rift(mac)
    r = rift_rng(mac).sub("capture", str(tier), str(milestone))
    lvl = layer_level(rift["depth"], milestone * CAPTURE_EVERY, tier, rift["mac"])
    d = generate_daemon(
        r, origin_mac=mac, favored_elements=rift["biome"]["elements"],
        min_rarity=2 if milestone < 5 else 3,
        stage=_stage_for_level(lvl))
    d.level = max(1, int(lvl * 0.8))
    return d
