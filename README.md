# AETHER

A self-hosted, LAN-native creature-raising game inspired by Digimon. Every
device on your network is a **Rift** into the subspace between your services —
and each device's **MAC address is the seed** for the entire world behind it:
its biome, habitats, wild daemons, and the chain of enemies you fight through.
Same network, same worlds, every time.

You raise **daemons** (unix pun fully intended) in **the Nest**, train their
stats, and send them to auto-battle through rifts. You never pick moves — you
raised them, now you watch them fight.

## Get it

```bash
git clone https://github.com/GrotesqueHarp/aether.git
cd aether
```

**Requirements:** Docker with the Compose plugin, *or* Python 3.9+. Nothing
else — the Python dependencies are vendored in `./vendor` (pure Python, x86 and
ARM), so there is no pip step, no virtualenv, and no network access needed to
install.

Fastest path, if you have Docker:

```bash
docker compose up -d --build
# open http://<host-ip>:8787 from any device on your LAN
```

Without Docker (Debian/Ubuntu, a Proxmox LXC, a Pi, a VM):

```bash
./install.sh          # checks for python3 / ping / ip — no pip, no venv
python3 app.py        # http://<host-ip>:8787
```

That's the whole install. Your save lives in the `aether_data` Docker volume
(or `./aether.db` for a bare install) and is never touched by updates.

> **A note if you fork this:** `aether.db` is gitignored on purpose — it
> contains the real MAC addresses of everything on your network. Don't commit
> it. The `vendor/` directory *is* committed intentionally, so a clone works
> with no package manager.

### Playing without LAN visibility

Real devices make the most characterful worlds, but they are not required. The
Array resolves rifts out of open subspace once your real devices run out, so
Docker Desktop users, VPS installs, and anyone on a locked-down network get the
full game — just with synthesised rifts instead of your printer. You can also
add any MAC by hand ("Add device" in the UI) and it generates its world
identically.

## Run it

Python dependencies are **bundled** in `./vendor` (pure Python — x86 and ARM
both fine), so nothing needs pip. On Debian/Ubuntu the installer just makes
sure the system tools exist (python3, iputils-ping, iproute2):

```bash
./install.sh          # check/install system tools only — no pip, no venv
python3 app.py        # start AETHER
```

`./install.sh --check` dry-runs without changing anything, and
`./install.sh --service` installs + enables a systemd unit so AETHER starts on
boot (logs: `journalctl -u aether -f`). Idempotent — re-run any time.

On any other OS with python3 ≥ 3.9: just `python3 app.py`. The app prefers
system-installed Flask if present and falls back to `./vendor` otherwise.

### Docker

```bash
docker compose up -d
# open http://<host-ip>:8787
```

**Host networking is required for real LAN scanning** (`network_mode: host`,
already set in the compose file): it gives the container your machine's actual
ARP table, and the UI binds straight to host port 8787 with no mapping. Game
state persists in the `aether_data` volume, so upgrades keep your daemons.

On Docker Desktop (macOS/Windows) host networking can't reach the LAN — use
the bridged fallback commented at the bottom of `docker-compose.yml`. The game
is fully playable that way: rifts never go dormant (presence tracking was
removed in v0.9), and the Array fills your capacity with deep-signal rifts
regardless of what it can see on the network.

### Updating

Recommended: make this directory a git repo (push it to Gitea/GitHub/wherever)
right after your first install. Then applying any update is:

```bash
./update.sh        # git pull + rebuild + restart + health-verify
```

If you've replaced files by hand instead (new zip drop), use
`./update.sh --local` to skip the pull and rebuild from what's on disk.

Your save is never at risk: game state lives in the `aether_data` volume, the
app stamps a `schema_version` into the DB, and `core/db.py` runs sequential
migrations at startup — an old save from any prior release upgrades in place.
The running version shows in the UI footer and in `/api/state`.

For active development, the override file bind-mounts the source and cranks
the world clocks:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d
# edit code, then:
docker compose restart aether     # ~2s, no rebuild
```

Dev state goes to ./dev-data so your real save is untouched.

### Managing the repo from Windows

`.gitattributes` forces LF line endings on all scripts, so files authored on
Windows still run on your Linux server (without it you'd hit
`bad interpreter: /bin/bash^M`). Set Git for Windows to store LF once:

```powershell
git config --global core.autocrlf input
```

The shell scripts also need their executable bit recorded, since Windows has
no concept of one:

```powershell
git update-index --chmod=+x install.sh update.sh
```

`.gitignore` keeps `aether.db` out of the repo — it contains the real MAC
addresses and hostnames of every device on your network.

Then open the printed `http://<your-lan-ip>:8787` from **any device on your
network** — phone, laptop, tablet. First run hatches your Anchor daemon, then
hit **Scan network**.

- **No root required.** Discovery does a concurrent ping sweep to warm the ARP
  cache, then reads the system ARP table (`ip neigh` / `arp -a`).
- If a scan finds nothing (locked-down host, container), it falls back to a
  sample network so the game is always playable, and you can **Add device** by
  MAC manually — any MAC seeds a full rift.

## How the seeding works

- **OUI → biome.** The first three octets of a MAC identify the manufacturer,
  so a Raspberry Pi grows a *Daemon Grove*, an Apple device a *Signal Spire*, a
  VM host a *Foundry*. Known vendors are hand-mapped; everything else is seeded
  from the OUI deterministically.
- **Full MAC → everything else.** A SplitMix64 PRNG (in `core/seed.py`) seeded
  from a SHA-256 of the MAC drives habitats, the node crawl, enemy daemons, and
  the rift's capturable signature daemon. `rng.sub("node", "3")` derives
  independent, reproducible child streams so concerns never bleed into each
  other.

## Layout

```
app.py              Flask server + JSON API + serves the dashboard
core/seed.py        Deterministic PRNG + MAC → seed
core/content.py     Attributes, elements, biomes, OUI map, name lexicon
core/daemon.py      Daemon model: stats, care, training, evolution
core/world.py       MAC → full Rift (biome, habitats, nodes, boss)
core/battle.py      Auto-battler (attribute triangle + element ring)
core/scan.py        Real LAN discovery (ping sweep + ARP parse)
core/db.py          SQLite (roster, progress, devices, journal, expeditions,
                    resources, harvests, eggs)
core/economy.py     Resources, harvest rates, loot tables, the Hatchery
core/bastion.py     Facilities, training halls, care automations
core/war.py         Overclock tiers, the Null, incursions, garrisons
sim/clock.py        Virtual clock (runs the game at any speed)
sim/harness.py      Headless world: scratch DB, fake LAN, tick loop
sim/agent.py        Win-odds forecasting + a policy that plays like a player
sim/report.py       Milestones, stall detection, bottleneck attribution, A/B
sim/diagnose.py     CLI for all of the above
core/ticker.py      Background heartbeat: drift, presence, expeditions
static/index.html   The dashboard (single-file vanilla SPA)
install.sh          Debian installer: system tools check/install, systemd unit
Dockerfile          Container image (host networking; see docker-compose.yml)
docker-compose.yml  Ready-made compose: host network + persistent volume
docker-compose.dev.yml  Dev override: bind-mounted source, fast clocks
update.sh           One-command update: pull, rebuild, restart, verify
VERSION             Deployed version (shown in UI footer + /api/state)
.gitattributes      Forces LF endings so Windows-authored scripts run on Linux
vendor/             Bundled Flask + deps (pure Python, no pip needed)
```

World generation is **never** persisted — only your roster and per-rift
progress are. Worlds are always regenerated from the MAC, which is the point.

## Game systems

- **Attributes:** Vaccine ▸ Virus ▸ Data ▸ Vaccine (1.5× triangle).
- **Elements:** a 10-element ring for a lighter 1.2× secondary matchup + biome
  flavor.
- **Care:** hunger, energy, happiness, discipline, corruption, weight — they
  drift in real time and modify battle stats. Neglect raises corruption and
  pushes evolution toward Virus forms; disciplined, happy daemons drift Vaccine.
- **Stages:** Egg → Hatchling → Rookie → Champion → Ultimate → Mega, gated by
  level; the branch you evolve into depends on how you raised it.
- **Capture:** beat a rift's Gatekeeper boss to stabilize it, then capture its
  signature daemon (only while its device is awake).

## The economy (v0.4)

Clearing a node drops **Bits** and biome **essence** (Ferro from Foundries,
Tide from Reefs...); bosses drop **Cores**. Every *cleared* node is a harvest
slot: assign a daemon and it generates resources continuously — rates scale
with node depth and the daemon's power, so harvesters are a real progression
track. Dormant rifts harvest slower but yield Umbra essence.

The **Hatchery** (in the Nest) turns Bits + essence into eggs: the essence
biases the element, a lucky roll raises rarity, and incubation takes real
hours. Each daemon you command raises the next egg's price — the classic
incremental cost curve.

Slow-burn pacing by design. Tuning knobs (env): `AETHER_ECON_MULT` (global
economy speed), `AETHER_HATCH_SECONDS` (incubation override).

## Rift Mastery (v0.13)

The third prestige loop, and the one that rewards breadth.

Every rift carries its own **1–99 mastery track**, earned by digging its layers
and by working its shelves. Each level adds +1% to that rift's yields, with
milestones at 10 (expeditions dig 25% faster), 25 (an extra capture per tier),
50 (enemies fight two levels lower), 75 (+50% Cores from posts) and 99 (yields
doubled, and layers dug count double toward the Array). Reaching 99 is roughly
250 days of working a rift — it's a landmark, not a checkbox.

**Resonance** is the global half: a multiplier drawn from the *sum* of mastery
across every rift you hold. Twenty rifts at mastery 25 give x1.72 where a single
rift at 99 gives x1.15 — so resolving more of the sky, and owning more hardware,
pays off in a way that grinding one shaft never does.

Knobs: `AETHER_MASTERY_K`, `AETHER_MASTERY_P`, `AETHER_MASTERY_YIELD`,
`AETHER_RESONANCE`.

## Glyphs (v0.12.1)

The second prestige loop, and the horizontal one. Seven kinds of craftable
equipment — ATK, DEF, HP, SPD, plus harvest yield, XP gain and training-hall
rate — at quality 1 to 5. Quality is chosen and paid for, never rolled; this
game doesn't ask you to gamble or to show up at the right moment.

Ascension makes a daemon flatly stronger. Glyphs decide what it's *for*: a
Harvest glyph is worthless in a fight and a Forge glyph is worthless on a
shelf, so your roster becomes a set of jobs rather than a power ranking.

Slots come from what a daemon has been through, not what you buy — 1 at
Hatchling, 2 at Champion, 3 at Mega, and one more at ascension ranks 3 and 6.
Cost scales roughly q^1.9 and demands Aethercite from Q3, which finally gives
Aethercite a second sink alongside the Array.

Struck at the Bastion. Knobs: `AETHER_GLYPH_CORES`, `AETHER_GLYPH_ESSENCE`,
`AETHER_GLYPH_BITS`.

> Called Glyphs rather than Sigils because `sigil` already means the
> procedurally drawn emblem in every daemon's genome.

## Ascension (v0.12)

The first prestige loop. A daemon that reaches **Mega at level 60** can be
**ascended**: it returns to a Hatchling at level 1, losing every level and
stage, and gains a permanent **lineage rank** worth +18% to all stats,
compounding with every rank it holds. At ranks 3 and 6 the lineage refines to a
higher rarity. It keeps its seed, name and record — it is recognisably the same
creature you raised, which is the point.

This exists for a mechanical reason as much as a sentimental one: rift tiers
scale enemies x1.6 each, while levelling and training halls add linearly. Without
a compounding channel of your own, the curve eventually outruns any amount of
grinding. Ascension is that channel.

Costs Cores, rising per rank. Knobs: `AETHER_ASCEND_MULT`,
`AETHER_ASCEND_LEVEL`, `AETHER_ASCEND_CORES`.

## Records & homecoming (v0.11)

**Records** (sidebar) charts Bits, income, party power, lifetime layers, Cores,
essence and roster size over 7 / 30 / 90 / 400 days, drawn as inline SVG from
hourly samples. A year-long game needs a curve to make its progress legible —
a resource bar can't show you that last month was better than the one before.

History accumulates from v0.11 onward and **is not retroactive**: nothing in an
older save records what your party power was three weeks ago. Sample interval
is `AETHER_HISTORY_EVERY` (default 3600s); roughly 400 days are retained.

**While you were away** greets you after any gap over five minutes with what
the machine did in your absence — harvested, dug, hatched, captured, defended —
plus highlights from the Pulse. It fires once per page load, never on the
polling loop.

## Learning the game

**Compass** (sidebar) is the tutorial, and it teaches by pointing at what you
should do next rather than by lecturing up front. Twenty-one objectives across
five chapters — First Light, The Work, The Bastion, Deeper, The Long Game —
each with why it matters and where to do it. They tick off against your actual
save as you play, nothing blocks you, and completions are journalled to the
Pulse.

Below them sits **Reference**: twelve topics covering every system, from what
Aethercite is for to why breadth beats depth. Objectives go stale once you've
done them; reference is what you want after a fortnight away.

## Auditing a build

```bash
python3 tools/audit.py --seed      # seeds a save, then checks everything
python3 tools/audit.py --no-ui     # API + Docker context only
```

Three passes: the Dockerfile's `COPY` sources cross-checked against
`.dockerignore`, then every endpoint against a seeded save, then every view in
a real browser — checking each rendered what it should, that the nav highlights the
right item, and that the console stayed clean.

The browser pass is the one that matters. Nearly every bug that has reached a
release here was invisible server-side: a button defined but never rendered, a
nav item whose handler was overwritten by a later binding, a file missing from
the Docker image. The API can be perfect while the page is broken.

## Changelog

Release notes live in [CHANGELOG.md](CHANGELOG.md), following
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Entries are grouped
Added / Changed / Fixed / Removed, and any release that migrates the database
is marked **Schema vN**.

You can read it in-app too — **Changelog** in the sidebar, backed by
`GET /api/changelog`. The sidebar shows a dot when the running version has
notes you haven't read; opening the view clears it. `./update.sh` also prints
everything that changed between your old version and the new one.

**Contributing?** Add your entry under `## [Unreleased]` in the appropriate
group. Move it into a versioned heading when you bump `VERSION`.

## Dashboard mode (v0.10.2)

AETHER on a spare monitor. Press **D** anywhere, click Dashboard in the
sidebar, or open **`http://<host>:8787/#dash`** directly so a TV or Pi kiosk
boots straight into it. **Esc** or **D** leaves.

No chrome and nothing to click — resource totals at a size you can read across
a room, the Tank running full width underneath, every rift's depth as a bar,
and a **Needs you** column that surfaces anything actually wanting attention:
hungry or corrupting daemons, daemons ready to evolve, Null incursions with
their countdown, shelves with captures waiting, rifts fully dug and ready to
Overclock, and daemons sitting idle with no post and no hall. When there's
nothing to do it says so.

Live updates come from the same fingerprint check as the rest of the app, so
an idle board issues no redraws, and the Tank stops rendering when the tab is
hidden.

## Rift ambience (v0.10.1)

Rifts move now too. Three quiet layers:

- **Harvest posts run visibly.** A working shelf shows essence streaking up a
  dark conduit, tinted by whatever that post actually pulls (Loam brown, Volt
  yellow, Umbra violet). Stream density follows the post's real yield on a log
  scale, so a deep shelf plainly runs harder than a shallow one without a
  hundredfold shelf becoming a solid wall of light.
- **The depth bar carries a current** — a shimmer travelling the resolved
  portion of the shaft.
- **Cleared layers pulse** in a slow wave down the shaft, staggered by layer,
  so the ground you've taken feels alive rather than greyed out.

Same rules as the Tank: purely cosmetic, no mechanical effect, and everything
stops dead when the tab is hidden or you navigate away, so a dashboard left
open overnight costs nothing.

## The Tank (v0.10)

The Nest opens with a living tank. Every daemon is drawn procedurally from its
own genome — element sets the palette, stage the size, rarity the finnage and
halo — so a creature looks like itself and like its sigil. No image assets;
it's all maths, same as the sigils.

**Motion carries the care meters.** Hungry daemons sink and slow, exhausted
ones half-close their eyes and drift, lonely ones keep to themselves, corrupted
ones flicker with umbra static. A one-word tag appears under anything that
needs you. The intent is that you can tell your Nest wants attention without
reading a single bar.

It changes nothing mechanically. Watching is its own reward, never a bonus —
there is no benefit to leaving the page open.

Rendering pauses when the tab is hidden or when you navigate away from the
Nest, so an always-open dashboard doesn't cook your server. Creature positions
persist in memory, so the live refresh redrawing the Nest doesn't teleport
everyone back to the middle.

## The long sky (v0.9.2)

Resolving every rift is meant to be the work of a year or more, not a weekend.

**Rifts found later are harder.** Each device records the Array level it was
resolved at, and that adds directly to the rift's depth rating — so a rift
found at Array L8 is markedly deeper and meaner than one found at L0, all the
way down its hundred layers. Discovery is a difficulty curve, not just a
content unlock.

**The Array is gated on digging, not money.** Each level requires a lifetime
layer count dug network-wide (~55 at L1, 1,490 at L5, 6,171 at L10), on top of
a cost curve that grows ×2.35 per level and starts demanding Cores at L2 and
Aethercite at L6 — and Aethercite only comes from holding off the Null, so the
deep sky opens only to someone who can defend what they already have.

The layer count is **lifetime** rather than current depth: Overclocking resets
a rift to layer 0, and summing live depth would mean pushing a tier erased your
progress toward the Array — and would cap you below the requirement entirely
once it exceeded rifts x 100.

At the digging rate observed in simulation, Array L5 is ~5 months and L10 is
well over a year; even at triple that rate L12 is ~325 days. Knobs:
`AETHER_ARRAY_GATE_BASE`, `AETHER_ARRAY_GATE_POWER`,
`AETHER_ARRAY_COST_GROWTH`, `AETHER_DISCOVERY_DEPTH`.

## Core supply and hall staffing (v0.9.1)

**Cores trickle from depth.** They used to come only from Gatekeeper layers,
which sit at 25/50/75/100 — so the entire economy could jam behind one
unbeatable fight, since Cores gate every facility past level 4 and every
Overclock. Now every harvest post yields Cores in proportion to its depth: a
shelf at layer 5 gives ~0.3/day, layer 50 gives ~8, layer 100 gives ~17.
Gatekeeper shelves still pay 2.5x. Breaking a Gatekeeper drops 1.5 Cores, and
Crucible reclamation is cheaper (600 Bits + 30 essence).

**Fill training halls before harvest posts.** Hall slots are few and bounded;
harvest posts are effectively unlimited, so harvesting quietly ate every
daemon and party power stopped growing. Halls first, harvest with the rest.

Over 21 simulated days this took party power from 1,372 to 10,559, started
hall training on day 0.7 instead of never, and removed the last stall.

## The Array, and where resources come from (v0.9)

**Presence is gone.** Rifts no longer wink out when a device leaves your
network — nothing goes dormant, and a rift you've found stays found forever.

**Discovery is a facility.** The Array is a listening tower: each level
resolves more rifts out of the noise. Real devices on your LAN are resolved
first, since they make the most characterful worlds; once they're exhausted,
further levels pull **deep-signal rifts** out of open subspace. Those get
synthesised MACs, so they're seeded exactly like device rifts and spread across
all six biomes — which permanently fixes the old problem where a LAN without a
Bazaar device could never produce Plasma. The Array costs Bits only at low
levels, since it's the thing that gets you the essences you're missing.

**Harvesting is the economy.** Clearing a layer is progress, not payday —
battle drops were cut to roughly a sixth, while harvest rates roughly doubled.
A posted daemon out-earns an entire layer clear in about sixteen minutes, and
keeps doing it while you're away.

**Harvest posts every 5 layers** (captures stay every 10), and the first ten
layers ramp in gently, so a lone starter daemon can reach its first post and
fund its first egg without a party.

## Refreshing (v0.8.4)

The page updates on two triggers, and there is no blind redraw timer:

1. **Right after anything you do** — dismissing a battle result, drawing a
   daemon from a shelf, posting a garrison, building, selling. Closing a dialog
   is treated as a refresh point, since the world behind it just changed.
2. **When the server's structural fingerprint changes** — an egg hatched, an
   expedition dug a layer, the Null arrived, a device went dormant. This is
   what keeps an idle game honest: most of what goes stale happens with no
   action at all.

The fingerprint deliberately ignores resource totals and harvest counters.
Those tick constantly and live in the resource bar, which updates on its own
without redrawing anything — redrawing the whole page because Bits went up is
what made a fixed interval feel intrusive. Sitting on an unchanged rift view
now issues no view requests at all.

Care and training use targeted per-card updates rather than a redraw, so
clicking Feed doesn't rebuild the page.

Redraws still pause while a modal or battle is open, while a dropdown or text
field is focused, and while the tab is hidden; scroll position is preserved.

## Resetting (v0.9.4)

**Reset** sits at the bottom of the sidebar and asks you to type RESET. Three
scopes:

| scope | wipes | keeps |
|---|---|---|
| `rifts` | rift depth, tiers, wards, captures, harvest posts, expeditions, incursions | daemons, Bastion, resources, discovered rifts, lifetime layers |
| `progress` | daemons, resources, facilities, eggs, all depth, the Pulse | the rifts you've already resolved |
| `everything` | all of the above plus discovered rifts and your Array level | nothing — identical to first boot |

`rifts` is the one you want when the world model changes under you and you'd
like fresh nodes without surrendering your roster. It deliberately preserves
lifetime layers dug, since that's a record of what you did and the Array's
gates are built on it.

From a shell:

```bash
curl -X POST localhost:8787/api/reset -H 'Content-Type: application/json' \
     -d '{"confirm": "RESET", "scope": "rifts"}'

curl -X POST localhost:8787/api/reset -H 'Content-Type: application/json' \
     -d '{"confirm": "RESET", "scope": "everything"}'
```

Omitting `scope` defaults to `progress`. The confirmation string is required —
a bare POST is refused, as is an unrecognised scope.

Resets clear rows rather than dropping tables, so the schema stays at its
current version and no migration reruns. The ticker's clocks are reset too;
otherwise the first beat after a reset would bill the new save for every hour
that passed under the old one.

## Automation over clicking (v0.8.1)

The point of the game is building machines that play it, not tapping buttons.

- **Manual training is deliberately marginal.** One stat point, costing 35
  energy — roughly four hours of idle recovery per click. A level-1 training
  hall already beats it 4×; a level-10 hall beats it ~500×.
- **Training halls compound.** Rates went multiplicative (×1.40/level) instead
  of additive. Upgrade costs grow ~1.55×/level, so a linear payoff meant every
  level bought less than the last and the halls quietly stopped mattering.
  L1 ≈ 24 stat points/day, L10 ≈ 500.
- **Care maintains itself.** The Auto-Feeder now *restores* hunger rather than
  merely slowing the drain — slowing a drain still ends at zero, so clicking
  Feed was mandatory forever. With the Playroom floor, the Cleansing Font, and
  passive energy recovery, all four meters can be fully automated.
- **Posted daemons settle at an energy floor** instead of bottoming out. Flat
  drain meant assigning your best daemon to a shelf permanently disabled it
  for combat.
- **Expeditions are the descent engine.** 100 layers across six rifts is not
  something you hand-fight; expeditions dig continuously while you're away.

Simulated over 21 days this removed every stall (20 frozen days → 0), took
party power from 1,077 to 7,030, and moved first hall training from day 10.7
to day 1.3.

## The descent (v0.8) — rifts are shafts, not corridors

A rift used to be 4–7 nodes ending in a Gatekeeper. It's now **100 layers**
you dig down through, which replaces nodes entirely.

- **Gatekeepers every 25 layers** (25/50/75/100).
- **A shelf every 10 layers.** Each shelf is both a capture milestone —
  one daemon, once, deeper shelves giving better ones — and a harvest post.
  Ten shelves per rift, so the UI stays readable where 100 slots wouldn't.
- **Deeper is harder and richer.** Foes per fight climb from 1 to 4 (capped
  there, since parties max at 3), while harvest yields climb steeply — layer 30
  pays roughly 3× layer 10.
- **Overclock now needs a full descent** to layer 100, and refreshes every
  shelf for another pass at ×1.6 difficulty and ×2 yields.

Layers generate on demand rather than up front — building 100 enemies per rift
per API call would be pure waste when only a handful are ever on screen.
Schema v6 migrates existing saves, mapping old node progress onto layer depth.

## Capture limits & selling (v0.7.2)

**Signature daemons can only be captured once.** The capture button had no
once-only check, so a single cleared rift could mint unlimited daemons.
Each rift now yields one signature daemon per tier — Overclocking (or
Downclocking) refreshes it, so pushing a rift deeper is also how you earn
another shot at its signature creature. Schema v5 adds `rift_progress.captured`.

**Selling.** Daemon cards have a Sell button that shows exactly what you'll get
before you confirm. Value scales mostly on rarity and stage rather than level,
so a 5-star Mega is worth keeping. Bits always; its element's essence when that
element has one; Cores only for rare, well-grown daemons. Guards: you can't
sell your only daemon or one away on expedition, and selling vacates any
harvest node or training hall it held. The old `/release` endpoint now pays out
too, rather than silently deleting.

## Jump to activity (v0.7.1)

Daemon cards in the Nest show what each one is doing — AWAY, HARVESTING,
TRAINING. Those badges are now clickable: tap one and you land on the exact
place that daemon is working, with the target highlighted. A harvester takes
you to its rift with its node flashing; a trainee takes you to the Bastion with
its hall flashing; an expedition takes you to the rift it's exploring.

Also fixed here: the battle party picker still hid harvesters and trainees,
so the borrowable-workers change in v0.7 wasn't actually reachable from the
browser. The picker now offers them, labelled with the job they'll be pulled
from and returned to.

## Rest, and the Overclock trap (v0.7)

**Energy now regenerates.** It used to drain at a flat -10/h whether or not a
daemon was doing anything, and it was the only care meter with no automation —
so the only way to keep a party combat-ready was clicking Rest around the
clock. Now a daemon that isn't posted to a job recovers on its own (+9/h) while
working daemons burn it slowly (-3.5/h). Idling is how you recover. In
simulation this removed a 13.5-day dead stretch entirely and tripled party
power over three weeks. Knobs: `AETHER_ENERGY_REGEN`, `AETHER_ENERGY_WORK`.

**Overclock is no longer a trap.** It costs Cores (rising with tier), the rift
view previews the Gatekeeper you'd face and warns when your party is
outmatched, and — most importantly — **Downclock** steps a rift back down.
Overclocking every clean rift on sight used to leave you with nothing you could
beat and no way back. Now you can always retreat; Cores just aren't refunded.
Knob: `AETHER_OVERCLOCK_CORES` (0 = free).

**Borrowable workers.** Harvesters and trainees can join a battle party and
return to their post afterward — only daemons away on expedition are truly
unavailable. Previously any daemon assigned to a job was locked out of combat,
so the only daemon free to fight was whichever hatched most recently: parties
never formed and the entire 3v3 layer went unused.

## The Crucible (v0.6.1, backend only)

Which essences you can earn depends on what hardware you own — a LAN with no
Bazaar device could never produce Plasma, which made four facilities
permanently unbuildable. The Crucible fixes that: lossy conversion between
essence types, plus Cores reclaimed from essence + Bits so a failed boss can't
lock you out of the upgrades that would let you beat it. It also gives the
late-game Bits pile-up a sink.

API: `GET /api/crucible`, `POST /api/crucible/transmute {from,to,amount}`,
`POST /api/crucible/reclaim {essence,count}`. Knobs: `AETHER_TRANSMUTE_RATIO`
(0 disables), `AETHER_TRANSMUTE_BITS`, `AETHER_RECLAIM_ESSENCE`,
`AETHER_RECLAIM_BITS`.

**There is no UI for this yet** — the endpoints work and the simulator uses
them, but nothing in the browser exposes it. That lands with the v0.8 tuning
pass.

## The simulator (dev tooling)

Milestones in this game are days apart, so they can't be felt by playing.
`sim/` runs the real game modules — same economy, same battle sim, same ticker
functions the container calls — on a virtual clock, driving the actual HTTP
routes through Flask's test client. A simulated month takes seconds, and it
can't drift from the shipped game because it *is* the shipped game.

```bash
python3 -m sim.diagnose configs                       # list tuning presets
python3 -m sim.diagnose report  baseline --days 21    # milestones, stalls, verdicts
python3 -m sim.diagnose log     baseline --days 8     # session-by-session decisions
python3 -m sim.diagnose log     baseline --phase combat --day-limit 5
python3 -m sim.diagnose compare casual normal obsessive --days 14
```

The simulated player only acts during *sessions* — a few check-ins a day with
a limited action budget — because an always-on optimizer would report pacing
no human will ever experience. Everything is deterministic: identical configs
produce identical timelines, so A/B comparisons are honest.

Scratch databases go to a temp dir; nothing here touches your real save.

## The Bastion & the war (v0.6)

**The Bastion** (new view) is base-building on your Anchor: four training
halls (Forge/Bulwark/Circuit/Core Chamber) where daemons gain permanent stats
over real hours — click-training naturally obsoletes as they level; a
Hatchery Wing (faster incubation); Nest automations (Auto-Feeder, Playroom,
Cleansing Font) that soften care drift; and the Aegis, which empowers
defenders. Facility costs follow the incremental curve and Cores join the
bill from level 5 — they finally have a sink.

**Parties.** Battles now take up to 3 daemons (global speed order, random
targeting). Higher-tier bosses bring minions, so squads stop being optional.

**Overclock.** A fully stabilized rift can be pushed to Tier+1: same world,
reset progress, enemies ×1.6/tier, all yields ×2/tier. The infinite loop.

**The Null.** Harvesting stabilized worlds builds signal; at threshold an
incursion spawns with a forgiving 12–24h real-time deadline. Post a garrison
(harvesters can serve where they stand) or repel it early. Hold: Cores +
Aethercite and a permanent Ward (+10% yields each, but the Null returns
angrier). Fall: the world reverts to unconquered at its tier — wards
shatter, harvesters limp home, nothing dies. Tuning (env):
`AETHER_TRAIN_MULT`, `AETHER_SIGNAL_RATE`, `AETHER_INCURSION_MIN_H/MAX_H`.

## The living world (v0.2)

A background ticker (`core/ticker.py`) runs while the server is up:

- **Presence.** Every few minutes AETHER re-reads the ARP table (cheap, no
  sweep). Devices that leave your network send their rifts **dormant**: enemies
  gain +3 levels and drift to Umbra, XP pays ×1.35, and signature capture locks
  until the device returns. Your household's real rhythm becomes the game's
  day/night cycle.
- **Expeditions.** Dispatch a daemon to a rift from the rift screen; it fights
  the next node every couple of minutes on its own, rests when exhausted, and
  comes home if routed. One daemon per rift.
- **The Pulse.** A journal of everything that happened — discoveries, presence
  changes, expedition victories/routs, care warnings, evolutions.

Clock tuning via env (great for testing):
`AETHER_TICK`, `AETHER_PRESENCE_EVERY`, `AETHER_PRESENCE_GRACE`,
`AETHER_FIGHT_EVERY` (all seconds).

## Notes / knobs

- Battle balance lives in `core/battle.py` and the stat formulas in
  `core/daemon.py`. Early fights resolve fast by design; tune `budget`,
  `growth`, and the `_hit` variance to taste.
- To use a full IEEE OUI vendor list, replace the small `_VENDORS` /
  `OUI_BIOME` tables — the lookups are keyed by the `AA:BB:CC` prefix.
