# Changelog

All notable changes to AETHER are recorded here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions are
`MAJOR.MINOR.PATCH` but pre-1.0, so minor bumps carry breaking changes.

Entries note **Schema vN** where a release migrates the database. Migrations
run automatically on start and are one-way — roll forward, not back.

> Entries before 0.10.3 were reconstructed from the README and commit history
> after the fact, so their groupings are accurate but their dates are not
> recorded. Everything from 0.10.3 onward is written as it ships.

## [Unreleased]

### Added
- Poking: click a daemon in the Tank and it reacts.

## [0.10.3]

### Added
- **Changelog.** This file, plus a Changelog view in the sidebar and
  `GET /api/changelog`. The sidebar marks it when the running version has
  notes you haven't read; opening it clears the mark.

## [0.10.2]

### Added
- **Dashboard mode** — full-screen ambient status board for a spare monitor.
  Press `D`, use the sidebar, or open `/#dash` so a TV or kiosk boots straight
  into it; `Esc` leaves. Large resource totals, the Tank full-width, rift depth
  bars, and a "Needs you" column surfacing hungry daemons, incursions, waiting
  captures, Overclock-ready rifts and idle daemons.

### Fixed
- Startup hook was spliced into the wrong `boot()` call, producing invalid
  JavaScript that broke the whole UI rather than just the dashboard.
- Sidebar hid by the wrong selector, and its grid track stayed behind,
  squeezing the board into a narrow column.

## [0.10.1]

### Added
- **Rift ambience.** Working harvest posts show essence streaking up a dark
  conduit, tinted by what the post yields, with density following its real
  rate on a log scale. The depth bar carries a current; cleared layers pulse in
  a slow wave down the shaft.

### Changed
- Flow particles draw as streaks rather than dots — motion legible in a still
  frame instead of reading as grey speckle.

## [0.10.0]

### Added
- **The Tank.** The Nest opens with a living canvas: every daemon drawn
  procedurally from its genome (element sets palette, stage size, rarity
  finnage and halo). Motion carries the care meters — hungry daemons sink and
  slow, exhausted ones half-close their eyes, corrupted ones flicker with umbra
  static — with a one-word tag under anything that needs you. Purely cosmetic;
  watching earns nothing.

## [0.9.4]

### Added
- **Scoped resets.** `rifts` re-rolls worlds while keeping your roster and
  Bastion; `progress` wipes the save but keeps resolved rifts; `everything`
  returns to first boot.

## [0.9.3]

### Added
- Getting-started instructions for cloning the public repo, a note that
  `aether.db` is gitignored because it holds real MAC addresses, and a section
  on playing without LAN visibility.

### Fixed
- Documentation still told users to set `AETHER_PRESENCE_GRACE` against
  dormancy, which stopped existing in 0.9.

## [0.9.2] — Schema v7

### Added
- **Rifts found later are harder.** Each device records the Array level it was
  resolved at, feeding directly into rift depth.
- **The Array is gated on digging**, not money: each level needs a lifetime
  layer count dug network-wide, alongside a cost curve growing x2.35 per level
  that demands Cores from L2 and Aethercite from L6.

### Fixed
- Array gate counts *lifetime* layers. Summing live depth would have meant
  Overclocking erased progress toward the Array, and made the requirement
  unreachable once it exceeded rifts x 100.

## [0.9.1]

### Changed
- **Cores trickle from depth.** Previously Gatekeeper layers only, so the
  economy could jam behind one unbeatable fight.
- Training halls are staffed before harvest posts — harvest posts are
  effectively unlimited and were quietly consuming every daemon, so hall
  training never happened and party power flatlined.

## [0.9.0]

### Added
- **The Array.** Discovery is a facility: each level resolves more rifts. Real
  devices first, then **deep-signal rifts** synthesised from subspace, which
  spread across all six biomes and end the famine where a LAN without a Bazaar
  device could never produce Plasma.

### Changed
- **Harvesting is the economy.** Battle drops cut to roughly a sixth, harvest
  rates roughly doubled; a posted daemon out-earns a layer clear in ~16 minutes.
- Harvest posts every 5 layers (captures stay every 10), and the first ten
  layers ramp in gently so a lone starter can reach its first post.

### Removed
- **Presence and dormancy.** Rifts no longer wink out when a device leaves the
  network; once found, a rift stays found.

## [0.8.4]

### Changed
- Refresh is event-driven: immediately after your actions, and when the
  server's structural fingerprint changes. The fixed redraw timer is gone, and
  an idle view issues no view requests at all.

## [0.8.3]

### Added
- Live updates, so harvest totals and countdowns move without navigating away
  and back. Paused while modals are open, inputs focused, or the tab hidden.

## [0.8.2]

### Added
- Reset progression, with a typed confirmation and an option to keep
  discovered devices.

## [0.8.1]

### Changed
- **Automation over clicking.** Manual training reduced to one stat point at
  35 energy; training halls made multiplicative (x1.40/level) to match their
  exponential cost curve; the Auto-Feeder now *restores* hunger rather than
  merely slowing it; posted daemons settle at an energy floor instead of
  bottoming out; expeditions became the descent engine.

## [0.8.0] — Schema v6

### Changed
- **Rifts are 100-layer shafts**, replacing 4–7 nodes. Gatekeepers every 25
  layers, a shelf every 10 for captures, foes per fight climbing 1 to 4, and
  harvest yields climbing steeply with depth. Overclock now needs a full
  descent. Layers generate on demand.

## [0.7.2] — Schema v5

### Added
- Selling daemons, priced mostly on rarity and stage, with guards against
  selling your last or one away on expedition.

### Fixed
- Signature capture had no once-only check, so a single cleared rift could mint
  unlimited daemons. Now one per rift per tier.

## [0.7.1]

### Added
- Jump to activity: status badges on daemon cards navigate to where that daemon
  is working, with the target highlighted.

### Fixed
- The battle party picker still hid harvesters and trainees, making 0.7's
  borrowable-workers change unreachable from the browser.

## [0.7.0]

### Added
- **Overclock guard rails**: it costs Cores, previews the next Gatekeeper's
  power, and **Downclock** lets you retreat from a tier you can't hold.
- **Borrowable workers** — harvesters and trainees can join a party and return
  to their post; only expeditions put a daemon out of reach.

### Fixed
- **Energy regenerates.** It drained at a flat -10/h whether or not a daemon
  was doing anything and was the only care meter with no automation, so a party
  could never be kept combat-ready without clicking Rest around the clock. In
  simulation this removed a 13.5-day dead stretch entirely.

## [0.6.1]

### Added
- **The Crucible** (backend only): lossy essence transmutation and Core
  reclamation, fixing the hardware-dependent softlock where facilities needing
  Plasma or Umbra were unbuildable on the wrong LAN.
- **The simulator** (`sim/`): runs the real game modules on a virtual clock
  through the actual HTTP routes, with milestone, stall and bottleneck
  reporting and A/B comparison.

## [0.6.0] — Schema v4

### Added
- **The Bastion**: nine facilities across training halls, support, care
  automations and war.
- **Parties** of up to three daemons, with higher-tier bosses bringing minions.
- **Overclock**: fully cleared rifts reset a tier higher for richer yields.
- **The Null**: incursions with forgiving real-time deadlines, garrisons, and
  permanent Wards for holding them off.

## [0.4.0] — Schema v3

### Added
- Resources, harvesting, battle loot and the Hatchery.

## [0.3.0]

### Added
- Update tooling and sequential schema migrations.

## [0.2.0] — Schema v2

### Added
- The living world: device presence, expeditions, and the Pulse journal.

## [0.1.0] — Schema v1

### Added
- Core game: MAC-seeded rift generation, daemons, care meters, the auto-battler,
  and the single-file web UI.
