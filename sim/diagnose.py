"""
diagnose.py — The command line for asking the simulation questions.

    python3 -m sim.diagnose report  --days 21
    python3 -m sim.diagnose log     --days 7  --phase combat
    python3 -m sim.diagnose compare baseline crucible --days 21
    python3 -m sim.diagnose configs

Everything runs headless against a scratch database. Nothing here touches your
real save or the container.
"""

from __future__ import annotations

import argparse
import sys

from .harness import Sim
from .agent import PlayerPolicy
from .report import full_report, compare, run_config, bottleneck, stalls

# Named tuning presets. Add your own — anything in `env` is an AETHER_* knob
# the shipped game already reads, and `policy` is how the simulated player
# behaves.
CONFIGS = {
    "baseline":    {"env": {}, "policy": {}},
    "no-crucible": {"env": {}, "policy": {"use_crucible": False}},
    "crucible":    {"env": {}, "policy": {"use_crucible": True}},
    "econ3":       {"env": {"AETHER_ECON_MULT": "3"}, "policy": {}},
    "fast-train":  {"env": {"AETHER_TRAIN_MULT": "3"}, "policy": {}},
    "casual":      {"env": {}, "policy": {"sessions_per_day": 1}},
    "normal":      {"env": {}, "policy": {"sessions_per_day": 3}},
    "obsessive":   {"env": {}, "policy": {"sessions_per_day": 8}},
    "hands-off":   {"env": {}, "policy": {"sessions_per_day": 1,
                                          "use_expeditions": True}},
}


def _run(name: str, days: float, step: float, snap: float) -> Sim:
    cfg = CONFIGS.get(name)
    if cfg is None:
        sys.exit(f"unknown config '{name}'. Try: {', '.join(CONFIGS)}")
    return run_config(name, days=days, env=cfg["env"], policy_kw=cfg["policy"],
                      step_minutes=step, snapshot_hours=snap)


def cmd_report(a):
    sim = _run(a.config, a.days, a.step_minutes, a.snapshot_hours)
    full_report(sim)
    sim.close()


def cmd_log(a):
    sim = _run(a.config, a.days, a.step_minutes, a.snapshot_hours)
    entries = sim.policy.log
    if a.phase:
        entries = [e for e in entries if e["phase"] in a.phase]
    if a.day_limit:
        entries = [e for e in entries if e["day"] <= a.day_limit]
    print(f"\n{'day':>7} {'sess':>5}  {'phase':10} {'what':38} detail")
    print("-" * 108)
    for e in entries[:a.max_lines]:
        print(f"{e['day']:>7.2f} {e['session']:>5}  {e['phase']:10} "
              f"{e['what'][:38]:38} {e['detail'][:44]}")
    print(f"\n({len(entries)} entries; showing {min(len(entries), a.max_lines)})")
    b = bottleneck(sim)
    print(f"\nverdict: {b['verdict']}")
    print(f"stalled: {sum(y['days']-x['days'] for x, y in stalls(sim)):.1f} "
          f"of {a.days:.0f} days")
    sim.close()


def cmd_compare(a):
    runs = {n: _run(n, a.days, a.step_minutes, a.snapshot_hours)
            for n in a.configs}
    compare(runs)
    for s in runs.values():
        s.close()


def cmd_configs(a):
    print("\navailable configs:\n")
    for name, cfg in CONFIGS.items():
        bits = []
        if cfg["env"]:
            bits.append(" ".join(f"{k.replace('AETHER_','')}={v}"
                                 for k, v in cfg["env"].items()))
        if cfg["policy"]:
            bits.append(" ".join(f"{k}={v}" for k, v in cfg["policy"].items()))
        print(f"  {name:14} {'; '.join(bits) or 'shipped defaults'}")
    print()


def main(argv=None):
    # shared flags, accepted before OR after the subcommand
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--days", type=float, default=21)
    common.add_argument("--step-minutes", type=float, default=15)
    common.add_argument("--snapshot-hours", type=float, default=12)

    ap = argparse.ArgumentParser(prog="sim.diagnose", parents=[common])
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("report", parents=[common],
                       help="milestones, stalls, bottlenecks")
    r.add_argument("config", nargs="?", default="baseline")
    r.set_defaults(fn=cmd_report)

    l = sub.add_parser("log", parents=[common],
                       help="session-by-session decisions")
    l.add_argument("config", nargs="?", default="baseline")
    l.add_argument("--phase", nargs="*",
                   help="filter: session combat build crucible hatch assign war overclock")
    l.add_argument("--day-limit", type=float, default=None)
    l.add_argument("--max-lines", type=int, default=200)
    l.set_defaults(fn=cmd_log)

    c = sub.add_parser("compare", parents=[common],
                       help="A/B two or more configs")
    c.add_argument("configs", nargs="+")
    c.set_defaults(fn=cmd_compare)

    g = sub.add_parser("configs", parents=[common],
                       help="list available presets")
    g.set_defaults(fn=cmd_configs)

    a = ap.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main(sys.argv[1:])
