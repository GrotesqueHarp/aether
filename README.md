# AETHER

A self-hosted, LAN-native creature-raising game inspired by Digimon. Every
device on your network is a **Rift** into the subspace between your services —
and each device's **MAC address is the seed** for the entire world behind it:
its biome, habitats, wild daemons, and the chain of enemies you fight through.
Same network, same worlds, every time.

You raise **daemons** (unix pun fully intended) in **the Nest**, train their
stats, and send them to auto-battle through rifts. You never pick moves — you
raised them, now you watch them fight.

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
the bridged fallback commented at the bottom of `docker-compose.yml`: the game
runs fine, you add devices manually by MAC, and a huge
`AETHER_PRESENCE_GRACE` keeps those rifts from going dormant.

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
