# AETHER — project context

Read this first when picking the project up. It is the orientation document:
what the game is, how it is built, what state it is in, and the conventions and
hard-won lessons that should shape further work.

- **Current version:** 0.25.2 · **Schema:** v11
- **Repo:** https://github.com/GrotesqueHarp/aether (public)
- **Runs on:** a Debian LXC under Proxmox, via Docker, at `:8787`
- **Scale:** ~1,250 lines of `app.py`, ~4,600 across `core/`, ~3,500 in the
  single-file frontend, 51 released versions

---

## What it is

A self-hosted, single-player, **years-long** idle game for homelabbers. Each
device on your network becomes a "rift" — a procedurally generated world seeded
deterministically from its MAC address, so the same hardware always produces
the same world. You raise creatures called **daemons**, send them down
hundred-layer shafts, post them on harvest shelves, and slowly build machinery
that plays the game while you are not looking.

### The design constraints — these matter more than any feature

1. **Automation is the goal, not a convenience.** Clicking is deliberately
   feeble; the game is about building systems that run without you. Anything
   that rewards frequent attention is working against the design.
2. **It should be leavable for weeks.** Nothing expires. Nothing punishes
   absence. No timers you must catch. The worst outcome of any event is a
   layer to re-dig.
3. **Watching is its own reward.** The aquarium, the music, the animations —
   none of it grants a bonus. There is deliberately no mechanical benefit to
   leaving the page open.
4. **Years, not weeks.** Pacing targets months per milestone. Cosmetics carry
   the long-run reward curve because multipliers dilute and palettes do not.
5. **Offline and dependency-free.** No CDN, no web fonts, no downloaded audio.
   Everything is vendored or synthesised. It must work on an air-gapped LXC.

---

## Architecture

Flask + SQLite + a single-file vanilla-JS frontend. No build step, no
framework, no package manager at runtime — Flask and its dependencies are
vendored into `./vendor` as pure Python.

```
app.py              ~50 HTTP routes; thin — logic lives in core/
core/
  seed.py           deterministic PRNG; everything world-related derives from it
  content.py        elements, attributes, biomes, name lexicon
  world.py          rift generation, 100-layer shafts, enemies per layer
  daemon.py         the creature: genome, stats, care, evolution, ascension
  battle.py         team combat simulation
  db.py             SQLite, schema, migrations  (largest module, ~920 lines)
  ticker.py         the heartbeat: drift, harvests, expeditions, all tick logic
  economy.py        resources, harvest rates, loot, hatchery, the Crucible
  bastion.py        facilities, training halls, the Shallows, the Waystation
  war.py            Overclock tiers, the Null, incursions
  mastery.py        per-rift 1-99 progression and global Resonance
  glyph.py          craftable equipment
  traits.py         per-daemon quirks, derived from seed
  affinity.py       preferences, bonds, wishes
  synergy.py        party composition bonuses
  reformat.py       global prestige
  awards.py         the unlock/cosmetic engine
  events.py         rift events — seams, collapses, strangers
  objectives.py     the Compass: chaptered objectives + reference topics
  scan.py           LAN discovery, deep-signal rift synthesis
static/index.html   the entire frontend: views, canvas rendering, audio
sim/                headless simulator (see below)
tools/audit.py      full-stack verification (see below)
```

### Key architectural decisions

- **Determinism everywhere.** `seed.py` drives world generation, traits,
  preferences, and hatching. The same MAC always yields the same rift; the same
  daemon always has the same quirks. This is why traits and preferences needed
  no migration when added — they were always latent in existing daemons.
- **Daemons are JSON blobs** in one column, so adding fields to the `Daemon`
  dataclass needs no schema change. Only new *tables* or *columns on other
  tables* require a migration.
- **`meta` is the key-value store** for anything that isn't a table: awards,
  cosmetics, lifetime counters, clocks, bonds, seams.
- **The ticker is the engine.** Almost nothing happens in request handlers;
  the background thread advances the world and the frontend reads it.
- **One canvas renderer, reused.** `drawCreature()` draws a daemon anywhere —
  the Nest tank, the Shallows pool, mini-tanks in halls and shelves, the battle
  stage. A rank-5 Mega looks like itself wherever it appears.

---

## The systems, and what each is for

| System | Role in the design |
|---|---|
| **Rifts / the descent** | 100 layers per device. Gatekeepers every 25, capture shelves every 10, harvest posts every 5. |
| **Harvesting** | *The* economy. A posted daemon out-earns a whole layer clear in ~16 minutes. |
| **The Bastion** | Facilities. Training halls, care automations, the Array, the Waystation, the Shallows. |
| **The Array** | Gates how many rifts you can hold resolved. Costs Cores and Aethercite, gated on lifetime layers dug — resolving the whole sky is a year's work. |
| **The Waystation** | Expedition slots. The valve that converts raw power into throughput. |
| **The Shallows** | Free XP pool for new arrivals. Its own tab. Upgradeable at great cost. |
| **The Null** | Incursions with 12–24h deadlines. Losing costs progress, never daemons. |
| **Overclock** | Push a fully dug rift a tier higher. Reversible via Downclock. |
| **Ascension** | Vertical prestige. +18% compounding per rank, keeps seed and name. |
| **Glyphs** | Horizontal prestige. Decides what a daemon is *for*. |
| **Rift Mastery** | Per-rift 1–99 plus global Resonance, which rewards *breadth*. |
| **Reformat** | Global prestige. Never required. |
| **Traits / affinity / synergy** | Make daemons individuals and party-building a decision. |
| **Awards / Wardrobe** | The long-run reward curve: themes, environments, decorations, adornments, titles. |

---

## Tooling — use these

### The simulator (`sim/`)

Runs the **real game modules** on a virtual clock, driving the actual HTTP
routes through Flask's test client. A simulated month takes seconds. It cannot
drift from the shipped game because it *is* the shipped game.

```bash
python3 -m sim.diagnose configs
python3 -m sim.diagnose report  baseline --days 21
python3 -m sim.diagnose log     baseline --days 8 --phase combat
python3 -m sim.diagnose compare casual normal obsessive --days 14
```

It has repeatedly overturned confident assumptions. The Waystation exists
because the simulator showed digging *decelerating* while party power grew
exponentially — the opposite of what everyone assumed. **Do not tune by
instinct when this can measure it.**

Caveat: the agent's competence is a confound. Several "the game is broken"
findings turned out to be "the simulated player is playing badly." Always read
`sim.diagnose log` before trusting a pacing conclusion.

### The audit (`tools/audit.py`)

```bash
python3 tools/audit.py --seed     # server must be running
```

Three passes: Dockerfile `COPY` sources cross-checked against `.dockerignore`,
every endpoint against a seeded save, then **every view in a real browser** —
checking each rendered, the nav highlighted, and the console stayed clean.
Currently 93 passing.

The browser pass is the one that matters. Nearly every bug that reached a
release was invisible server-side.

---

## Lessons learned the hard way

These are not general advice; each one cost a real bug in this project.

1. **Grep before building.** I twice rebuilt features that already existed
   (a tutorial duplicating the Compass, an equipment module duplicating
   Glyphs). `ls core/` takes two seconds. The repo is the record; memory is not.
2. **Verify edits landed on disk.** Multi-edit scripts with `assert` between
   steps abort *before writing*, silently discarding earlier successful edits.
   Write first, then re-read the file and assert against what is actually there.
3. **Test the browser, not the payload.** A button defined but never rendered,
   a nav handler overwritten by a later binding, a null field crashing
   `.toUpperCase()` — the API was correct in every case.
4. **Restart the server after editing modules.** More than once a "bug" was a
   stale process running pre-fix code.
5. **Beware colons in delimiters.** MAC addresses contain them; a
   colon-delimited record containing a MAC can never be parsed back.
6. **Check `.dockerignore` before adding a `COPY`.** It fails the build with an
   opaque cache-key error that no amount of running the app reveals.
7. **Units must match.** Training granted raw stat points while levels granted
   ~4 of them, so a hall out-paced levelling 40x. Always express a new system
   in terms of the thing it competes with.

---

## Current state

**Working and shipped:** everything in the table above, plus the Compass
tutorial, Records charts, the offline summary, the battle stage, rift events,
generated music and UI sound effects, drag-and-drop, and the full cosmetic
system.

**Known open items:**

- **Award thresholds need retuning** against the measured curve. They were
  written assuming a steeper curve than exists — `Ferrous` at 5,000 layers is
  roughly six months at current rates, and the 25,000-layer landmark is years.
  The trinket tier may be too sparse.
- **Music is structurally correct but untested by ear at length.** Tempo,
  lead/bass balance, and motif re-roll frequency are taste calls.
- **Expedition reports** were discussed but not built — expeditions run for
  hours and produce a single Pulse line.
- **A daemon detail page** would help; cards are crowded with stats, care,
  traits, affinity, bonds, biography and glyphs.

**Explicitly rejected:** anything competitive or social — no leaderboards, no
trading, no multiplayer. It is a self-hosted single-player aquarium and that
constraint is a feature.

---

## Operating it

```bash
# deploy
git clone https://github.com/GrotesqueHarp/aether.git && cd aether
docker compose up -d --build        # or: ./install.sh && python3 app.py

# update
./update.sh                          # pulls, rebuilds, prints the changelog diff

# reset — three scopes
curl -X POST localhost:8787/api/reset -H 'Content-Type: application/json' \
     -d '{"confirm":"RESET","scope":"everything"}'
```

`rifts` re-rolls worlds and keeps your roster; `progress` wipes the save but
keeps resolved rifts; `everything` is a genuine first boot including awards and
Reformat cycles.

**~60 environment knobs** tune pacing without code changes — `AETHER_ECON_MULT`,
`AETHER_HALL_LEVELS_PER_DAY`, `AETHER_MASTERY_K`, `AETHER_REFORMAT_THRESHOLD`
and so on. Grep `os.environ.get` in `core/` for the full list with defaults.

**`aether.db` is gitignored on purpose** — it contains the real MAC addresses
of every device on the network.

---

## Conventions

- **Every change gets a CHANGELOG.md entry** under `[Unreleased]`, moved to a
  version heading on release. Format follows Keep a Changelog. Releases that
  migrate the database are marked **Schema vN**.
- **Bump `VERSION`** on every release; `update.sh` prints the changelog between
  the old and new versions.
- **Comments explain *why*, not *what*.** The codebase is full of notes about
  why a number is what it is, and what went wrong before. Preserve that.
- **Run the audit before packaging.** It has caught real regressions.
