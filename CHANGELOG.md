# Changelog

All notable changes to AETHER are recorded here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions are
`MAJOR.MINOR.PATCH` but pre-1.0, so minor bumps carry breaking changes.

Entries note **Schema vN** where a release migrates the database. Migrations
run automatically on start, in sequence, and are one-way — roll forward, not
back.

> **On the backfill:** entries before 0.10.3 were reconstructed from the README,
> the source, and development history after the fact. The contents are
> accurate; release *dates* were never recorded and have deliberately been left
> out rather than invented. Everything from 0.10.3 onward is written as it ships.

## [Unreleased]

### Added
- Poking: click a daemon in the Tank and it reacts.
- Traits, squad synergies, expedition orders, milestones, creature behaviours,
  and the shaft in cross-section.

## [0.12.0]

### Added
- **Ascension**, the first of the prestige systems. A daemon at Mega and level
  60 can be unmade back to a Hatchling, keeping its seed, name and record while
  gaining a permanent **lineage rank**: +18% to all stats, compounding per
  rank, with a rarity refinement at ranks 3 and 6. Costs Cores, rising per
  rank.
- Rank marks (✦) beside ascended daemons, and a warmer halo in the Tank that
  brightens with rank.

### Changed
- Ascension is deliberately the exponential channel the player lacked. Rift
  tiers scale enemies x1.6 each while levelling and halls add linearly, so
  without a compounding track of your own the curve eventually outruns any
  amount of grinding.
- No migration needed: daemons are stored as JSON blobs, so the new field
  defaults cleanly on old saves.

## [0.11.0] — Schema v8

### Added
- **Records.** Hourly samples of Bits, income, party power, lifetime layers,
  Cores, essence and roster size, drawn as inline SVG charts over 7/30/90/400
  days. Slow-burn progress is invisible in a resource bar; a month of
  harvesting needs a curve to be legible. Sampling starts when this ships —
  graphs can only ever show what was recorded, so there is no retroactive
  history.
- **While you were away.** A summary on page load after any gap over five
  minutes: what was harvested and dug, how the roster changed, and highlights
  pulled from the Pulse.

### Fixed
- The homecoming check was wired into the polling loop rather than page load,
  so `/api/visit` re-stamped the "last seen" time every ten seconds and you
  were never recorded as having been away.

## [0.10.4]

### Changed
- Backfilled every historical release with full detail. The first pass gave
  each version a one-line summary, which is no use for tracing when a
  particular behaviour changed.

## [0.10.3]

### Added
- **Changelog.** This file, a Changelog view in the sidebar, and
  `GET /api/changelog`, which parses the file into structured releases rather
  than serving it raw. The sidebar marks it when the running version has notes
  you haven't read; opening it clears the mark. The seen-version lives in
  `meta`, so it's per-instance rather than per-browser.
- `./update.sh` prints every entry between your old version and the new one,
  skipping `[Unreleased]`.

## [0.10.2]

### Added
- **Dashboard mode** — full-screen ambient status board for a spare monitor.
  Press `D`, use the sidebar, or open `/#dash` so a TV or kiosk boots straight
  into it; `Esc` leaves. Large resource totals, the Tank full-width, rift depth
  bars, and a "Needs you" column surfacing hungry or corrupting daemons,
  daemons ready to evolve, Null incursions with countdowns, shelves with
  captures waiting, Overclock-ready rifts, and daemons idle with no post and no
  hall. Says so plainly when there's nothing to do.

### Fixed
- Startup hook was spliced into the wrong `boot()` call, producing invalid
  JavaScript that would have broken the entire UI, not just the dashboard.
- Sidebar was hidden by the wrong selector (`nav.nav` rather than `nav.rail`),
  and its 216px grid track stayed behind, squeezing the board into a column.

## [0.10.1]

### Added
- **Rift ambience.** Working harvest posts show essence streaking up a dark
  conduit, tinted by what that post yields, with stream density following its
  real rate on a log scale so a deep shelf plainly runs harder than a shallow
  one. The depth bar carries a travelling current; cleared layers pulse in a
  slow wave down the shaft, staggered per layer.

### Changed
- Flow particles draw as short streaks rather than dots. As dots over a pale
  card they read as grey speckle; as streaks over a dark conduit the motion is
  legible even in a still frame.

## [0.10.0]

### Added
- **The Tank.** The Nest opens with a living canvas. Every daemon is drawn
  procedurally from its own genome — element sets the palette, stage the size,
  rarity the finnage and halo — so a creature matches its sigil. No image
  assets; the same maths approach as the sigils.
- Motion carries the care meters: hungry daemons sink and slow, exhausted ones
  half-close their eyes and drift, corrupted ones flicker with umbra static,
  and a one-word tag appears under anything that needs you.
- Rendering stops when the tab is hidden or you leave the Nest. Creature
  positions persist in memory so a live refresh doesn't teleport everyone back
  to the middle.

### Changed
- Creatures enlarged, opacity floor raised, and a personal-space force added
  after the first pass produced a small, washed-out pile with overlapping name
  labels.

## [0.9.4]

### Added
- **Scoped resets.** `rifts` re-rolls worlds while keeping your roster,
  Bastion and resources; `progress` wipes the save but keeps resolved rifts;
  `everything` returns to first boot. Legacy `keep_devices` callers still work.
- `rifts` deliberately preserves lifetime layers dug, since that's the record
  the Array's gates are built on.

## [0.9.3]

### Added
- Getting-started instructions for cloning the public repo, stated
  requirements, and a section on playing without LAN visibility.
- A warning that `aether.db` is gitignored because it contains the real MAC
  addresses of every device on your network.

### Fixed
- README and `docker-compose.yml` still advised setting
  `AETHER_PRESENCE_GRACE` against dormancy, a mechanic removed in 0.9 — new
  users would have been configuring a variable that does nothing.

## [0.9.2] — Schema v7

### Added
- **Rifts found later are harder.** `devices.found_at` records the Array level
  a rift was resolved at, feeding directly into its depth rating, so discovery
  is a difficulty curve rather than only a content unlock.
- **The Array is gated on digging, not money.** Each level requires a lifetime
  layer count dug network-wide (~55 at L1, 1,490 at L5, 6,171 at L10) on top of
  a cost curve growing x2.35 per level, demanding Cores from L2 and Aethercite
  from L6 — which finally gives Aethercite a sink, since it only comes from
  repelling the Null.

### Fixed
- The Array gate counts *lifetime* layers rather than current depth. Summing
  live depth would have meant Overclocking erased progress toward the Array,
  and made the requirement unreachable once it exceeded rifts x 100.
- `upgrade_cost()` was left returning `None` for every non-Array facility after
  two functions were spliced into the middle of it.

## [0.9.1]

### Changed
- **Cores trickle from depth.** Previously they came only from Gatekeeper
  layers at 25/50/75/100, so the whole economy could jam behind one unbeatable
  fight — Cores gate every facility past level 4 and every Overclock. Every
  harvest post now yields them in proportion to depth, Gatekeeper shelves
  paying 2.5x.
- Crucible reclamation cheaper (600 Bits + 30 essence); Gatekeeper clears drop
  1.5 Cores.
- Training halls are staffed before harvest posts. Hall slots are few and
  bounded while harvest posts are effectively unlimited, so harvesting quietly
  consumed every daemon and hall training never happened at all.

## [0.9.0]

### Added
- **The Array.** Discovery became a facility: each level resolves more rifts.
  Real network devices are resolved first, then **deep-signal rifts**
  synthesised from subspace with locally-administered MACs.
- Deep-signal rifts spread across all six biomes, ending the hardware-dependent
  famine where a LAN without a Bazaar or Hollow device could never produce
  Plasma or Umbra — and therefore could never build four of the nine facilities.

### Changed
- **Harvesting is the economy.** Battle drops cut to roughly a sixth while
  harvest rates roughly doubled; a posted daemon out-earns an entire layer
  clear in about sixteen minutes.
- Harvest posts every 5 layers (captures stay every 10), and the first ten
  layers ramp in gently, so a lone starter daemon can reach its first post and
  fund its first egg without a party.

### Removed
- **Presence and dormancy.** Rifts no longer wink out when a device leaves the
  network. Once found, a rift stays found.

## [0.8.4]

### Changed
- Refresh is event-driven rather than timed: immediately after actions, and
  when the server's structural fingerprint changes. An idle view now issues no
  view requests at all.
- The fingerprint deliberately ignores resource totals and harvest counters —
  those tick constantly and live in the resource bar, which updates without
  redrawing the view.

### Removed
- The fixed 6-second redraw timer.

## [0.8.3]

### Added
- Live updates, so harvest totals, hatching eggs, expedition progress and
  incursion countdowns move without navigating away and back. Paused while a
  modal or battle is open, while a dropdown or field is focused, and while the
  tab is hidden; scroll position preserved.

## [0.8.2]

### Added
- Reset progression, with a typed confirmation and an option to keep discovered
  devices. Clears rows rather than dropping tables, so the schema stays put.

### Fixed
- Reset also clears the ticker's clocks; otherwise the first beat after a reset
  would bill the new save for every hour that passed under the old one.

## [0.8.1]

### Changed
- **Automation over clicking.** Manual training reduced to one stat point
  costing 35 energy — roughly four hours of idle recovery per click. A level-1
  hall beats it 4x, a level-10 hall ~500x.
- Training halls made multiplicative (x1.40/level). Upgrade costs grow ~1.55x
  per level, so a linear payoff meant every level bought less than the last and
  the halls quietly stopped mattering.
- Expeditions became the descent engine, since 100 layers across six rifts is
  not something anyone hand-fights.

### Fixed
- The Auto-Feeder now *restores* hunger rather than only slowing the drain.
  Slowing a drain still ends at zero, so clicking Feed remained mandatory
  forever.
- Posted daemons settle at an energy floor instead of bottoming out — flat
  drain meant assigning your best daemon to a shelf permanently disabled it for
  combat.

## [0.8.0] — Schema v6

### Changed
- **Rifts are 100-layer shafts**, replacing the old 4–7 node chain.
  Gatekeepers every 25 layers, a shelf every 10 for captures, foes per fight
  climbing from 1 to 4, and harvest yields climbing steeply with depth
  (layer 30 pays roughly 3x layer 10). Overclock now requires a full descent.
- Layers generate on demand rather than up front — building 100 enemies per
  rift per API call would be waste when only a handful are ever on screen.

### Fixed
- The ticker ejected harvesters standing on their own shelf (off-by-one:
  `<=` where `>` was needed).
- The descent rendered inside the old node grid container, squashing the
  layout into columns.

## [0.7.2] — Schema v5

### Added
- **Selling daemons**, priced mostly on rarity and stage rather than level, so
  a 5-star Mega is worth keeping. Guards against selling your last daemon or
  one away on expedition; selling vacates any post or hall it held.

### Fixed
- Signature capture had no once-only check, so a single cleared rift could mint
  unlimited daemons. Now one per rift per tier, refreshed by Overclocking.
- `/release` previously deleted a daemon silently, with no payout and no guards.

## [0.7.1]

### Added
- Jump to activity: the AWAY / HARVESTING / TRAINING badges on daemon cards
  navigate to exactly where that daemon is working, with the target
  highlighted.

### Fixed
- The battle party picker still filtered out harvesters and trainees, making
  0.7's borrowable-workers change unreachable from the browser. The simulator
  drives the HTTP API directly, so it never exercised the UI path.

## [0.7.0]

### Added
- **Overclock guard rails**: it costs Cores (rising per tier), the rift view
  previews the next Gatekeeper's power and warns when your party is outmatched,
  and **Downclock** steps a rift back down. Overclocking every clean rift on
  sight used to leave nothing beatable and no way back.
- **Borrowable workers** — harvesters and trainees can join a battle party and
  return to their post afterward. Only expeditions put a daemon out of reach.

### Fixed
- **Energy regenerates.** It drained at a flat -10/h whether or not a daemon
  was doing anything, and was the only care meter with no automation, so a
  party could never be kept combat-ready without clicking Rest around the
  clock. In simulation this removed a 13.5-day dead stretch entirely and took
  21-day party power from 1,400 to 4,444.
- Working daemons being locked out of combat meant the only free fighter was
  whichever daemon hatched most recently — parties never formed and the whole
  3v3 layer sat unused.

## [0.6.1]

### Added
- **The Crucible** (backend only): lossy essence transmutation and Core
  reclamation from essence and Bits, fixing the hardware-dependent softlock
  where facilities needing Plasma or Umbra were unbuildable on the wrong LAN.
- **The simulator** (`sim/`): a virtual clock, a headless world, an agent that
  plays through the real HTTP routes, and milestone / stall / bottleneck
  reporting with A/B comparison via `python3 -m sim.diagnose`.

### Fixed
- A nested same-quote f-string in the Crucible route parsed only on Python
  3.12+, which would have been a syntax error on the 3.9+ the installer
  advertises.

## [0.6.0] — Schema v4

### Added
- **The Bastion**: nine facilities across four families — training halls
  (Forge/Bulwark/Circuit/Core Chamber), the Hatchery Wing, care automations
  (Auto-Feeder, Playroom, Cleansing Font) and the Aegis.
- **Parties** of up to three daemons with a team battle simulator, global speed
  order and random targeting; higher-tier bosses bring minions.
- **Overclock**: a fully cleared rift resets a tier higher — enemies x1.6,
  yields x2, repeatable.
- **The Null**: incursions with forgiving 12–24h real-time deadlines, garrisons
  that can be drawn from harvesters, and permanent Wards for holding them off.
  Losing costs progress, never daemons.

## [0.4.0] — Schema v3

### Added
- Resources: Bits, six biome essences, and Cores.
- Harvesting — every cleared node became a post generating resources
  continuously.
- Battle loot on first clears, and the **Hatchery**: essence-biased eggs with
  real incubation time and costs scaling per daemon owned.
- A live resource bar with income rates.

## [0.3.0]

### Added
- `install.sh` and `update.sh`, sequential schema migrations, and Docker with
  Compose using host networking for real ARP visibility.

### Changed
- Python dependencies vendored into `./vendor` (pure Python, x86 and ARM), so
  there is no pip and no virtualenv. A minimal LXC without `ensurepip` had made
  venv-based installs fail outright.

## [0.2.0] — Schema v2

### Added
- **The Pulse**, a journal of everything that happens while you're away.
- Device presence tracking, with rifts going dormant when a device left the
  network — harder enemies, drifting Umbra, and bonus XP.
- **Expeditions**: dispatch a daemon to fight through a rift on its own,
  reporting back to the Pulse.
- A background ticker applying care drift in real time.

## [0.1.0] — Schema v1

### Added
- Core game: deterministic MAC-seeded rift generation (biome, habitats, wild
  daemons, node chain), the daemon genome (attribute, element, rarity, base
  stats, growth), care meters, evolution stages gated on level and care, and a
  1v1 auto-battler with an attribute triangle and elemental ring.
- The single-file web UI with procedurally generated SVG sigils for every rift
  and daemon.
- LAN discovery without root, via ping sweep and the ARP table.
