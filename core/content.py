"""
content.py — Static game vocabulary: attributes, elements, biomes, and the
lexicon used to name daemons and worlds. Kept data-only so it's easy to expand.
"""

# --- Attribute triangle (classic three-way, big battle multiplier) -----------
# Vaccine beats Virus, Virus beats Data, Data beats Vaccine.
ATTRIBUTES = ["Vaccine", "Data", "Virus"]
ATTR_BEATS = {"Vaccine": "Virus", "Virus": "Data", "Data": "Vaccine"}

# --- Elements (flavor + a lighter secondary matchup) -------------------------
ELEMENTS = [
    "Ember", "Tide", "Volt", "Loam", "Gale",
    "Frost", "Lumen", "Umbra", "Ferro", "Plasma",
]
# each element is strong vs the next in the ring (minor multiplier)
ELEMENT_RING = {ELEMENTS[i]: ELEMENTS[(i + 1) % len(ELEMENTS)] for i in range(len(ELEMENTS))}

ELEMENT_COLORS = {
    "Ember": "#F0714A", "Tide": "#3FA9D6", "Volt": "#E8C84D", "Loam": "#B08A54",
    "Gale": "#8FD6B4", "Frost": "#7FCBEB", "Lumen": "#F4E9B8", "Umbra": "#8B7CF6",
    "Ferro": "#A6B0BE", "Plasma": "#E86AD0",
}

# --- Life stages (the "digivolution" ladder) ---------------------------------
STAGES = ["Egg", "Hatchling", "Rookie", "Champion", "Ultimate", "Mega"]
# level required to be *eligible* to advance out of each stage
STAGE_LEVEL_GATE = {"Egg": 0, "Hatchling": 3, "Rookie": 12, "Champion": 24, "Ultimate": 40}

# --- Biomes. OUI (manufacturer) picks which biome a device's Rift becomes. ---
# Each biome favors certain elements and has its own look/mood.
BIOMES = {
    "foundry":   {"name": "The Foundry",     "elements": ["Ferro", "Ember", "Volt"],
                  "mood": "clanking heat-haze server halls", "color": "#F0714A"},
    "reef":      {"name": "The Packet Reef",  "elements": ["Tide", "Frost", "Gale"],
                  "mood": "cool flowing datastreams",        "color": "#3FA9D6"},
    "grove":     {"name": "The Daemon Grove",  "elements": ["Loam", "Gale", "Lumen"],
                  "mood": "overgrown idle processes",        "color": "#8FD6B4"},
    "spire":     {"name": "The Signal Spire",  "elements": ["Volt", "Plasma", "Lumen"],
                  "mood": "crackling broadcast towers",      "color": "#E8C84D"},
    "hollow":    {"name": "The Null Hollow",   "elements": ["Umbra", "Ferro", "Frost"],
                  "mood": "dropped-packet darkness",         "color": "#8B7CF6"},
    "bazaar":    {"name": "The Port Bazaar",   "elements": ["Plasma", "Ember", "Tide"],
                  "mood": "noisy open-port marketplace",     "color": "#E86AD0"},
}
BIOME_KEYS = list(BIOMES.keys())

# A handful of well-known OUI prefixes get a hand-picked biome so real devices
# feel intentional. Everything else is seeded from the OUI deterministically.
OUI_BIOME = {
    "DC:A6:32": "grove",    # Raspberry Pi Foundation
    "B8:27:EB": "grove",    # Raspberry Pi Foundation (older)
    "E4:5F:01": "grove",    # Raspberry Pi
    "F0:18:98": "spire",    # Apple
    "AC:DE:48": "spire",    # Apple (private)
    "00:1A:11": "reef",     # Google
    "3C:5A:B4": "reef",     # Google
    "00:50:56": "foundry",  # VMware
    "52:54:00": "foundry",  # QEMU/KVM virtual
    "00:15:5D": "foundry",  # Microsoft Hyper-V
    "B0:4F:13": "bazaar",   # (example consumer IoT block)
}

# --- Name lexicon ------------------------------------------------------------
# Daemon names are built from seeded syllables + an element-tinted suffix so
# they feel like a family (e.g. "Voltkin", "Emberling", "Tidewraith").
NAME_HEADS = [
    "Byte", "Null", "Echo", "Volt", "Ember", "Tide", "Loam", "Gale", "Frost",
    "Lumen", "Umbra", "Ferro", "Grim", "Cache", "Ping", "Sync", "Hex", "Root",
    "Dae", "Pico", "Nano", "Quill", "Sable", "Zeph", "Crux", "Vane", "Mote",
]
NAME_TAILS_BY_STAGE = {
    "Egg": ["-ovo", "-seed", "-pod"],
    "Hatchling": ["ling", "let", "kin", "pip"],
    "Rookie": ["mon", "kit", "ward", "fang"],
    "Champion": ["maw", "claw", "reaver", "warden"],
    "Ultimate": ["reign", "scourge", "sovereign", "colossus"],
    "Mega": ["-Prime", "-Omega", "-Zero", "-Ur"],
}

WORLD_ADJ = ["Silent", "Fractal", "Humming", "Broken", "Gilded", "Buried",
             "Restless", "Cold", "Overclocked", "Forgotten", "Bright", "Deep"]
WORLD_NOUN = ["Subnet", "Expanse", "Lattice", "Reaches", "Verge", "Sprawl",
              "Threshold", "Cascade", "Domain", "Frontier"]
