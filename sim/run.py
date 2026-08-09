"""CLI entry point: python3 -m sim.run --days 14"""
from __future__ import annotations
import argparse, sys
from .harness import Sim, IdlePolicy
from .agent import PlayerPolicy

POLICIES = {
    "idle": IdlePolicy,
    "player": lambda: PlayerPolicy(strategy="balanced"),
    "training": lambda: PlayerPolicy(strategy="training"),
    "harvest": lambda: PlayerPolicy(strategy="harvest"),
}

def _mk(args):
    if args.policy == "idle":
        return IdlePolicy()
    return PlayerPolicy(strategy={"player":"balanced"}.get(args.policy, args.policy),
                        sessions_per_day=args.sessions)

def main(argv=None):
    ap = argparse.ArgumentParser(description="Run AETHER headless at speed.")
    ap.add_argument("--days", type=float, default=7.0)
    ap.add_argument("--step-minutes", type=float, default=10.0)
    ap.add_argument("--snapshot-hours", type=float, default=12.0)
    ap.add_argument("--policy", default="player", choices=sorted(POLICIES))
    ap.add_argument("--sessions", type=float, default=3.0, help="check-ins per day")
    ap.add_argument("--econ-mult", default=None, help="AETHER_ECON_MULT override")
    ap.add_argument("--train-mult", default=None)
    ap.add_argument("--signal-rate", default=None)
    args = ap.parse_args(argv)

    env = {}
    if args.econ_mult:   env["AETHER_ECON_MULT"] = args.econ_mult
    if args.train_mult:  env["AETHER_TRAIN_MULT"] = args.train_mult
    if args.signal_rate: env["AETHER_SIGNAL_RATE"] = args.signal_rate

    sim = Sim(env=env)
    sim.run(days=args.days, step_minutes=args.step_minutes,
            policy=_mk(args), snapshot_hours=args.snapshot_hours)
    sim.report()
    sim.close()

if __name__ == "__main__":
    main(sys.argv[1:])
