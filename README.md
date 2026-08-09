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
