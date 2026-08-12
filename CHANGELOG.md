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
- A steeper progression curve to match the years-long pacing. The award
  thresholds assume it; against today's numbers they arrive early.
- Teach the simulator about Ascension, Glyphs and Mastery — it currently
  measures a game without prestige.
- Reformat: global prestige. Needs the above first.

## [0.18.2]

### Changed
- **Creatures are drawn per stage.** Every stage previously shared one
  silhouette — an ellipse with a single tapering sine tail — which at
  Hatchling size read as something other than a creature. Now the shape itself
  carries the stage: Hatchlings are compact and round with stubby paddles and
  a crest, Rookies gain side fins and a swept tail, Champions become broad
  rays with beating wings, Ultimates trail a mane of streamers, and Megas add
  a crown of spines rooted along the back.
- Rarity adds limbs on top of the stage silhouette rather than replacing it,
  so a rare Rookie still reads as a Rookie.
- Eyes gained a highlight and moved with the head; Eggs have none, since they
  haven't opened one yet.

## [0.18.1]

### Added
- **The cosmetics themselves.** Six theme palettes (Ferrous, Resonant, The Long
  Dark, Verdant, Year One, Mastered) that recolour the entire interface —
  chrome, charts and the Tank's own water — by swapping CSS variables, so no
  component needs to know a theme exists.
- Four **environments** that repaint the tank: The Deep, The Choir, The Garden,
  Folded.
- Five **tank decorations**, all procedural: Shaftlight falling from above,
  Deep Current banding through the water, Slow Water motes, Fronds rooted along
  the floor, and a Constellation with one star per rift you hold.
- Three **daemon adornments**: Well-Kept haloes contented creatures, Starlit
  circles five-star Megas, and Lineage trails a mark per ascension rank.
- **The Wardrobe** — every award with its colour swatch, what's worn, and what
  it takes to earn the rest. Trinkets show live progress; landmarks stay `???`.

## [0.18.0]

### Added
- **Awards**, the substrate for long-run rewards. Every other reward here is a
  multiplier, and multipliers dilute: the tenth x1.12 is invisible. Cosmetics
  don't — a palette earned at ten thousand layers reads exactly as vividly in
  month thirty as month three, and it says what you did every time you see it.
- Twenty-three awards across five earning axes: depth, breadth, time, care and
  rare feats. Two tiers — **trinkets** are frequent and show their requirements
  as goals; **landmarks** are rare and stay hidden behind `???` until earned,
  so they read as discoveries.
- Time-based awards always carry a second condition, so someone who finds the
  game late doesn't receive a year of backlogged rewards at once.
- Awards and worn cosmetics **survive Reformat** — they're the record of
  everything the instance has ever done. `daemons_raised`, `layers_dug` and the
  instance's birthday now survive resets for the same reason.
- Nothing auto-applies: `POST /api/awards/wear` puts something on, and the
  engine refuses anything unearned.

## [0.17.0]

### Added
- **Reformat**, the fourth and outermost prestige loop. Fold the whole run and
  begin again with a permanent multiplier on everything the world produces.
  Measured on what you *did* — layers dug, mastery earned, tiers pushed,
  lineage ranks — rather than what you happen to be holding, so it rewards
  using the economy instead of hoarding it. Each cycle asks 1.6x more than the
  last. It is never required; the game is complete without ever folding.
- What survives a fold is chosen so it reads as carrying something forward
  rather than starting over: Aethercite, the Array's level, every lifetime
  layer dug, the Records history, and one daemon of your choosing — returned
  to a Hatchling but keeping its lineage rank and traits.
- Knobs: `AETHER_REFORMAT_THRESHOLD`, `AETHER_REFORMAT_GAIN`,
  `AETHER_REFORMAT_SCALE`.

### Changed
- **The simulator can see the whole game.** Its agent now ascends daemons at
  the cap, strikes and fits glyphs by the job a daemon actually does, and
  weighs rift mastery when choosing where to post harvesters. It was measuring
  a game without four of its systems: with prestige enabled, 21-day party power
  reads 37,648 against the 10,559 it previously reported, and the first
  Overclock lands on day 16 rather than never.

### Fixed
- Two function declarations in the UI were left as `async async function` and
  a bare `function` by an edit that split an anchor, breaking the whole script.

## [0.16.1]

### Added
- **The shaft in cross-section.** A vertical cut through all 100 layers beside
  the descent list: strata darkening with depth, Gatekeeper bands at 25/50/75/
  100 that light gold once passed, every shelf you've reached, your posted
  daemons drawn in their own colours at the depth they're standing, and the
  frontier with the unexplored rock below it. The list shows the handful of
  layers you can act on; this shows where they sit in the whole descent.
- Hidden below 900px wide, where there isn't room for it.

## [0.16.0] — Schema v11

### Added
- **Traits.** Every daemon has one quirk, or two if it's rare — Tunneler digs
  faster, Prospector pulls more Cores, Stoic corrupts half as slowly, Warden
  defends harder, Homebody harvests well but travels badly. Most carry a cost
  as well as a benefit, so they're a character rather than a second rarity
  roll. Derived from the daemon's seed rather than stored, so no migration was
  needed and every daemon you already own has always had its traits.
- Traits reach into combat stats, XP, harvest yields, hall training, care
  drift, expedition speed and incursion defence.
- **Expedition orders.** Dispatch with intent: **Dig** pushes deeper layer by
  layer, **Farm** reworks the deepest layer already taken for loot without
  advancing, and **Scout** maps the ground ahead without fighting, earning rift
  mastery and reporting what waits below.

## [0.15.0]

### Added
- **Squad synergies.** A party earns bonuses for its composition: Spectrum
  (three different elements, +10% ATK), Closed Triangle (Vaccine, Virus and
  Data together, +10% HP), Phalanx (one shared attribute, +12% DEF) and Shared
  Lineage (every member ascended, +8% SPD). Shown live in the party picker and
  on the victory screen. Applied to clones, so a one-fight bonus can never be
  written back into stored stats. Magnitudes are deliberately modest — a
  considered party should feel smart, not make an unconsidered one unviable.
- **Creature behaviours** in the Tank: exhausted daemons sink to the floor and
  sleep with their eyes shut, happy ones chase each other, hungry and corrupted
  ones read as before. One behaviour at a time, most urgent first.
- **Poking.** Click a daemon and it flares, darts off, and says how it's doing.
  Entirely cosmetic, as the aquarium always has been.
- **Day/night tint** — the Tank warms and cools with your local clock.

### Removed
- "Milestones" from the backlog: the Compass's 21 chaptered objectives already
  are that feature.

## [0.14.0]

### Added
- **Reference** section in the Compass: twelve plain-language topics covering
  the Array, the descent, where resources come from, automating care, the
  Bastion, the Crucible, Glyphs, Ascension, Mastery and Resonance, the Null,
  Overclock, and what happens while you're away. Objectives tell you what to do
  next; reference tells you how the machine works, and stays useful when you
  come back after a fortnight.

### Removed
- `core/guide.py` and its view — a duplicate tutorial built without noticing
  the Compass already existed. Its objectives checklist was strictly worse than
  the Compass's chaptered version, which persists completions and journals them
  to the Pulse; only its reference text was worth keeping, and that has been
  folded in.
- `core/sigils.py` — an unwired parallel implementation of what shipped as
  Glyphs in 0.12.1. Nothing imported it and the UI never called it.

### Changed
- `tools/audit.py` now covers the Compass view and `/api/objectives`. It was
  absent from the audit, which is why a whole working tab went unnoticed.

## [0.13.2]

### Fixed
- **Docker build failed** with `failed to compute cache key: "/README.md": not
  found`. 0.13.1 added `README.md` to a `COPY`, but `.dockerignore` excludes it
  from the build context on purpose. The README is documentation, not runtime
  data — only `CHANGELOG.md` is actually read (by `/api/changelog`), so the
  COPY now takes just that.

### Added
- `tools/audit.py` gained a Docker context pass: it cross-checks every
  `COPY` source in the Dockerfile against `.dockerignore` and the filesystem.
  A COPY of an excluded file fails the build with an opaque cache-key error
  that no amount of running the app will reveal — only building the image
  will, which is easy to skip.

## [0.13.1]

### Fixed
- **Dashboard opened the Rifts view.** `boot()` rebinds every `.navitem` click
  to `go(dataset.view)`, which overwrote the Dashboard's inline handler; with
  no `data-view` it called `go(undefined)` and fell through to Rifts.
- **Changelog was blank in Docker.** The Dockerfile never copied `CHANGELOG.md`
  into the image, so it worked locally and was empty in the container. It now
  ships `CHANGELOG.md` and `README.md`, and the view says so plainly if the
  file is absent rather than rendering nothing.
- **No more web fonts.** The UI pulled three families from Google Fonts on
  every page load — which fails on an LXC with no internet, and sent a request
  to a CDN each time you opened your own dashboard. Replaced with system font
  stacks; the app is now genuinely offline.

### Added
- `tools/audit.py` — exercises every endpoint and every view in a real browser,
  checking that each view rendered, the nav highlights correctly, and the
  console stayed clean. Run `python3 tools/audit.py --seed`.

## [0.13.0] — Schema v10

### Added
- **Rift Mastery**, the third prestige system. Every rift carries its own
  1–99 track, earned by digging its layers and by working its shelves.
  Each level adds +1% to that rift's yields; milestones land at 10
  (expeditions dig 25% faster), 25 (an extra capture per tier), 50 (enemies
  fight two levels lower), 75 (+50% Cores from posts) and 99 (yields doubled,
  and layers dug count double toward the Array).
- **Resonance**, a global multiplier drawn from the *sum* of mastery across
  every rift you hold. This is the half that rewards breadth: twenty rifts at
  25 give x1.72 where a single rift at 99 gives x1.15, so finding more of the
  sky pays off in a way grinding one shaft never does.
- Reaching 99 takes roughly 1.05M XP — about 250 days of working a rift's
  shelves. Knobs: `AETHER_MASTERY_K`, `AETHER_MASTERY_P`,
  `AETHER_MASTERY_YIELD`, `AETHER_RESONANCE`.

### Fixed
- `rift_progress` gained `mastery_xp` in the migration but not in the
  fresh-database `CREATE TABLE`, so new saves crashed on every rift view while
  migrated ones worked. `get_progress()` likewise omitted the field from both
  its row and default dictionaries.

## [0.12.1] — Schema v9

### Added
- **Glyphs**, the second prestige system: craftable equipment in seven kinds —
  ATK / DEF / HP / SPD, plus harvest yield, XP gain and training-hall rate.
  Quality 1–5 is chosen and paid for, never rolled, with cost scaling ~q^1.9
  and Aethercite required from Q3, giving it a second sink.
- Slots come from what a daemon has been through rather than what you buy:
  1 at Hatchling, 2 at Champion, 3 at Mega, +1 at ascension ranks 3 and 6.
- Where Ascension makes a daemon flatly stronger, glyphs decide what it's *for*
  — a Harvest glyph is worthless in a fight and a Forge glyph is worthless on a
  shelf, so a roster becomes a set of jobs rather than a power ranking.

### Fixed
- `db.get_daemon()` called an undefined `_attach_mods()`, raising `NameError`
  on **every** daemon fetch. Now defined as the hook that attaches equipped
  glyphs, and applied to `list_daemons()` too.

### Changed
- Equipment is called Glyphs, not Sigils: `sigil` already names the procedural
  emblem in every daemon's genome, and overloading it would have made the code
  ambiguous.

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
