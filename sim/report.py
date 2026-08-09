"""
report.py — Turn a simulation into an answer.

Three questions this exists to answer:

  When did things happen?   milestones()  — the day each first-time event fired
  Where did it stop?        stalls()      — stretches with no real progress
  Why did it stop?          bottleneck()  — which resource or wall was binding

Plus compare(), which runs several tuning configs and puts them side by side,
so "does this fix actually help" stops being a matter of opinion.
"""

from __future__ import annotations

import sys

from .harness import Sim
from .agent import PlayerPolicy

# events worth calling out, in the order a player would meet them
MILESTONES = [
    ("harvest_start", "first harvester posted"),
    ("egg_laid", "first egg synthesized"),
    ("hatch", "first egg hatched"),
    ("build", "first facility built"),
    ("boss", "first Gatekeeper felled"),
    ("capture", "first signature daemon caught"),
    ("train_start", "first hall training"),
    ("overclock", "first Overclock (Tier 1)"),
    ("incursion_spawn", "first Null incursion"),
    ("incursion_win", "first incursion repelled"),
    ("incursion_fall", "first world lost"),
]

# progress = nodes cleared, with a tier counting as a full lap of the rift
def progress_score(snap: dict) -> float:
    return sum(v["cleared"] + v["tier"] * 8 for v in snap["rifts"].values())


def milestones(sim: Sim) -> list[tuple[str, str, float | None]]:
    out = []
    for kind, label in MILESTONES:
        out.append((kind, label, sim.milestone(kind)))
    return out


def tier_days(sim: Sim) -> list[tuple[str, float]]:
    """Elapsed day each rift reached each tier. Counted PER RIFT — six rifts
    hitting T1 is not one rift hitting T6."""
    per: dict[str, int] = {}
    out = []
    for e in sim.events(("overclock",)):
        mac = e.get("mac") or "?"
        per[mac] = per.get(mac, 0) + 1
        out.append((f"{mac[-8:]} -> T{per[mac]}",
                    round((e["ts"] - sim.clock.start) / 86400, 2)))
    return out


def stalls(sim: Sim, min_days: float = 2.0, power_tol: float = 0.03):
    """Stretches where neither progress nor power meaningfully moved."""
    snaps = sim.snapshots
    out, run_start = [], None
    for i in range(1, len(snaps)):
        a, b = snaps[i - 1], snaps[i]
        flat = (progress_score(b) <= progress_score(a)
                and b["party_power"] <= a["party_power"] * (1 + power_tol))
        if flat and run_start is None:
            run_start = a
        elif not flat and run_start is not None:
            if a["days"] - run_start["days"] >= min_days:
                out.append((run_start, a))
            run_start = None
    if run_start is not None and snaps[-1]["days"] - run_start["days"] >= min_days:
        out.append((run_start, snaps[-1]))
    return out


def bottleneck(sim: Sim, window: list[dict] | None = None) -> dict:
    """Which resource blocked the most purchases, and how close combat was."""
    window = window or sim.snapshots
    tally: dict[str, int] = {}
    for s in window:
        for res, n in (s.get("blocked_by") or {}).items():
            tally[res] = tally.get(res, 0) + n
    ranked = sorted(tally.items(), key=lambda kv: -kv[1])
    # `now` is what the player faces at the END of this window; `peak` is the
    # best it ever got. Conflating the two made every stall look economy-bound.
    odds_now = window[-1].get("best_frontier", 0.0)
    odds_peak = max((s.get("best_frontier", 0.0) for s in window), default=0.0)
    return {"blocking": ranked, "odds_now": odds_now, "odds_peak": odds_peak,
            "verdict": _verdict(ranked, odds_now, odds_peak)}


def _verdict(ranked, now, peak) -> str:
    top = ranked[0][0] if ranked else None
    if now >= 0.3:
        if not ranked:
            return f"not blocked — winnable at {now:.0%}, agent stopped pushing"
        return f"economy-bound: {top} blocks purchases; combat winnable at {now:.0%}"
    if peak - now > 0.35:
        return (f"outscaled: frontier fell {peak:.0%} -> {now:.0%} — enemies grew "
                f"faster than the party" + (f"; {top} starving upgrades" if top else ""))
    if now < 0.15:
        return (f"hard wall: best frontier only {now:.0%}"
                + (f", and {top} starves the upgrades that would fix it" if top else ""))
    return f"grind zone: frontier {now:.0%}, beatable on retries"


def full_report(sim: Sim, stream=sys.stdout):
    p = lambda *a: print(*a, file=stream)
    last = sim.snapshots[-1]
    p(f"\n{'='*66}\n  AETHER pacing report · {last['days']:.0f} days · "
      f"{getattr(sim, 'policy', None) and sim.policy.name}\n{'='*66}")

    p("\nMILESTONES")
    for kind, label, day in milestones(sim):
        p(f"  {label:32} {'day %5.2f' % day if day is not None else '     never':>12}")

    td = tier_days(sim)
    p("\nOVERCLOCK PACING" if td else "\nOVERCLOCK PACING\n  (no tier ever reached)")
    for name, day in td:
        p(f"  {name:32} day {day:6.2f}")
    if td:
        peak = {}
        for name, _ in td:
            mac, t = name.split(" -> T")
            peak[mac] = max(peak.get(mac, 0), int(t))
        p(f"  highest tier on any one rift: T{max(peak.values())}"
          f"   ({len(peak)} rifts overclocked)")

    p("\nFINAL STATE")
    p(f"  roster {last['roster']}   party power {last['party_power']}   "
      f"facilities {sum(last['facilities'].values())} levels")
    p(f"  wallet {last['resources']}")
    p(f"  frontier odds {last.get('frontier_odds')}")

    st = stalls(sim)
    p(f"\nSTALLS ({len(st)} found)")
    for a, b in st:
        window = [s for s in sim.snapshots if a["days"] <= s["days"] <= b["days"]]
        bn = bottleneck(sim, window)
        p(f"  day {a['days']:.1f} → {b['days']:.1f}  ({b['days']-a['days']:.1f}d frozen)")
        p(f"    power {a['party_power']} → {b['party_power']}   "
          f"progress {progress_score(a):.0f} → {progress_score(b):.0f}")
        p(f"    blocking: {', '.join(f'{r}×{n}' for r, n in bn['blocking'][:4]) or '—'}")
        p(f"    verdict:  {bn['verdict']}")
    if not st:
        p("  none — progression never froze for 2+ days")
    return sim


# ------------------------------------------------------------------- A/B ----
def run_config(name: str, days: float = 21, env: dict | None = None,
               policy_kw: dict | None = None, step_minutes: float = 15,
               snapshot_hours: float = 12) -> Sim:
    sim = Sim(env=env or {})
    sim.label = name
    sim.run(days=days, step_minutes=step_minutes,
            policy=PlayerPolicy(**(policy_kw or {})),
            snapshot_hours=snapshot_hours)
    return sim


def compare(runs: dict[str, Sim], stream=sys.stdout):
    """Side-by-side, so tuning arguments get settled with numbers."""
    p = lambda *a: print(*a, file=stream)
    names = list(runs)
    w = max(14, max(len(n) for n in names) + 2)
    p(f"\n{'='*(24 + w*len(names))}\n  A/B COMPARISON\n{'='*(24 + w*len(names))}")
    p(f"  {'metric':22}" + "".join(f"{n:>{w}}" for n in names))

    def row(label, fn):
        p(f"  {label:22}" + "".join(f"{fn(runs[n]):>{w}}" for n in names))

    row("days simulated", lambda s: f"{s.snapshots[-1]['days']:.0f}")
    row("party power", lambda s: s.snapshots[-1]["party_power"])
    row("roster", lambda s: s.snapshots[-1]["roster"])
    row("progress score", lambda s: f"{progress_score(s.snapshots[-1]):.0f}")
    row("overclocks", lambda s: len(tier_days(s)))
    row("first boss (day)", lambda s: _fmt(s.milestone("boss")))
    row("first tier (day)", lambda s: _fmt(s.milestone("overclock")))
    row("first hall (day)", lambda s: _fmt(s.milestone("train_start")))
    row("first incursion", lambda s: _fmt(s.milestone("incursion_spawn")))
    row("bits (final)", lambda s: f"{s.snapshots[-1]['resources'].get('bits',0):,.0f}")
    row("cores (final)", lambda s: f"{s.snapshots[-1]['resources'].get('cores',0):.0f}")
    row("facility levels", lambda s: sum(s.snapshots[-1]["facilities"].values()))
    row("stalled days", lambda s: f"{sum(b['days']-a['days'] for a,b in stalls(s)):.0f}")
    row("frontier odds (end)", lambda s: f"{s.snapshots[-1].get('best_frontier',0):.0%}")
    row("frontier odds (peak)", lambda s: f"{bottleneck(s)['odds_peak']:.0%}")
    p("")
    for n in names:
        p(f"  {n}: {bottleneck(runs[n])['verdict']}")
    return runs


def _fmt(v):
    return "never" if v is None else f"{v:.2f}"
