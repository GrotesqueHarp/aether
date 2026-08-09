"""
AETHER — self-hosted daemon-raising game for your LAN.

Run:  python3 app.py
Then open the printed http://<lan-ip>:8787 from any device on your network.

v0.2 — The Pulse: a background ticker keeps the world alive. Care meters drift
in real time, devices leaving your network send their rifts dormant, and
daemons can be dispatched on idle expeditions that report to a journal.
"""

from __future__ import annotations

import os
import sys
import time

# Self-contained dependency resolution: prefer system/venv packages, but fall
# back to the bundled ./vendor directory so `python3 app.py` works on a fresh
# machine with nothing installed. Vendored packages are pure Python (no
# compiled extensions), so this works on x86 and ARM alike.
_VENDOR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor")
try:
    from flask import Flask, jsonify, request, send_from_directory
except ModuleNotFoundError:
    if os.path.isdir(_VENDOR):
        sys.path.insert(0, _VENDOR)
        from flask import Flask, jsonify, request, send_from_directory
    else:
        raise SystemExit(
            "Flask is not installed and the bundled ./vendor directory is "
            "missing. Either re-download the full AETHER package, or run: "
            "pip install flask")

from core import db, scan, ticker, economy, bastion, war
from core.daemon import Daemon, starter_daemon
from core.world import generate_rift
from core.battle import simulate, simulate_team

app = Flask(__name__, static_folder="static", static_url_path="")

_VERSION_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "VERSION")
try:
    VERSION = open(_VERSION_FILE).read().strip()
except OSError:
    VERSION = "dev"


# ---- helpers ---------------------------------------------------------------
def _daemon_payload(d: Daemon) -> dict:
    out = d.to_dict()
    ex = db.get_expedition(d.id) if d.id else None
    out["on_expedition"] = bool(ex and ex["state"] == "active")
    if out["on_expedition"]:
        out["expedition"] = {"mac": ex["mac"], "fights": ex["fights"],
                             "world": generate_rift(ex["mac"])["world_name"]}
    hv = db.get_harvest(d.id) if d.id else None
    out["harvesting"] = None
    if hv:
        rift = generate_rift(hv["mac"])
        out["harvesting"] = {
            "mac": hv["mac"], "node_index": hv["node_index"],
            "world": rift["world_name"],
            "lifetime_bits": round(hv["lifetime_bits"], 1),
            "rates": {k: round(v, 2) for k, v in economy.harvest_rates(
                d, rift, hv["node_index"], ticker.dormancy(hv["mac"])).items()},
        }
    tr = db.get_training(d.id) if d.id else None
    out["training"] = None
    if tr:
        out["training"] = {
            "hall": tr["hall"],
            "hall_name": bastion.FACILITIES[tr["hall"]]["name"],
            "stat": bastion.FACILITIES[tr["hall"]]["stat"],
            "gained": tr["gained"],
            "rate": round(bastion.hall_rate(db.facility_level(tr["hall"])), 2),
        }
    return out


def _guard_can_fight(d: Daemon):
    """Battles and expeditions need a free daemon. Care is always allowed —
    you can visit a harvester at its node or a trainee in its hall."""
    ex = db.get_expedition(d.id) if d.id else None
    if ex and ex["state"] == "active":
        return jsonify({"error": "on_expedition",
                        "message": f"{d.name} is away on an expedition. "
                                   "Recall it first."}), 400
    if d.id and db.get_harvest(d.id):
        return jsonify({"error": "harvesting",
                        "message": f"{d.name} is working a harvest node. "
                                   "Stop the harvest first."}), 400
    if d.id and db.get_training(d.id):
        return jsonify({"error": "training",
                        "message": f"{d.name} is training in a hall. "
                                   "Withdraw it first."}), 400
    return None


def _guard_available(d: Daemon):
    """Strictest guard: expedition only (kept for care/train/evolve)."""
    ex = db.get_expedition(d.id) if d.id else None
    if ex and ex["state"] == "active":
        return jsonify({"error": "on_expedition",
                        "message": f"{d.name} is away on an expedition. "
                                   "Recall it first."}), 400
    return None


# ---- routes ----------------------------------------------------------------
@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/api/state")
def state():
    ticker.apply_drift()
    roster = db.list_daemons()
    return jsonify({
        "bootstrapped": db.get_meta("bootstrapped") == "1",
        "version": VERSION,
        "schema": db.get_meta("schema_version"),
        "resources": db.res_all(),
        "rates": economy.total_rates(),
        "roster_count": len(roster),
        "local_ip": scan.local_ipv4(),
        "subnet": (str(scan.local_subnet()) if scan.local_subnet() else None),
        "active_expeditions": len(db.list_expeditions()),
    })


@app.route("/api/bootstrap", methods=["POST"])
def bootstrap():
    if db.get_meta("bootstrapped") == "1":
        return jsonify({"error": "already_bootstrapped"}), 400
    d = starter_daemon()
    db.add_daemon(d)
    db.set_meta("bootstrapped", "1")
    db.set_meta("last_tick", str(time.time()))
    db.add_event("hatch", f"{d.name} hatched from the Anchor egg. "
                          "The Nest is no longer empty.", daemon_id=d.id)
    return jsonify({"daemon": d.to_dict()})


# -- devices & scanning --
@app.route("/api/devices")
def devices():
    return jsonify({"devices": db.list_devices()})


@app.route("/api/scan")
def do_scan():
    if request.args.get("mock") == "1":
        devs = scan.mock_devices()
        meta = {"subnet": "192.168.1.0/24 (mock)", "swept": False, "mock": True}
    else:
        result = scan.discover(do_sweep=request.args.get("sweep", "1") == "1")
        devs, meta = result["devices"], result["meta"]
    for d in devs:
        known = db.get_device(d["mac"])
        db.upsert_device(d["mac"], d.get("hostname", ""), d.get("ip", ""),
                         d.get("vendor", ""), online=True)
        if not known:
            db.add_event("rift_found",
                         f"New rift discovered: {generate_rift(d['mac'])['world_name']} "
                         f"({d.get('hostname') or d['mac']}).", mac=d["mac"])
    return jsonify({"devices": db.list_devices(), "meta": meta})


@app.route("/api/device/manual", methods=["POST"])
def manual_device():
    body = request.get_json(force=True)
    mac = body.get("mac", "")
    try:
        rift = generate_rift(mac, body.get("hostname", ""), scan.vendor_for(mac))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    known = db.get_device(rift["mac"])
    db.upsert_device(rift["mac"], body.get("hostname", ""), "",
                     scan.vendor_for(mac), online=True)
    if not known:
        db.add_event("rift_found",
                     f"Rift opened by hand: {rift['world_name']} ({rift['mac']}).",
                     mac=rift["mac"])
    return jsonify({"rift": rift})


@app.route("/api/rift/<mac>")
def rift(mac):
    hostname = request.args.get("hostname", "")
    try:
        r = generate_rift(mac, hostname, scan.vendor_for(mac))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    dev = db.get_device(r["mac"])
    if dev and not hostname:
        r["hostname"] = dev["hostname"] or r["hostname"]
    r["progress"] = db.get_progress(r["mac"])
    r["online"] = (not dev) or bool(dev["online"])
    r["dormant"] = bool(dev) and not dev["online"]
    # scale displayed enemies for the rift's current tier
    if r["progress"]["tier"] > 0:
        for n in r["nodes"]:
            e = war.scale_enemy(Daemon.from_dict(n["enemy"]), r["progress"])
            n["enemy"] = e.to_dict()
            n["enemy_level"] = e.level
    r["fully_cleared"] = (r["progress"]["cleared"] >= len(r["nodes"])
                         and bool(r["progress"]["boss_down"]))
    inc = db.get_incursion(r["mac"])
    r["incursion"] = None
    if inc:
        r["incursion"] = {
            "deadline": inc["deadline"],
            "seconds_left": max(0, int(inc["deadline"] - time.time())),
            "strength": round(inc["strength"], 1),
            "garrison": [int(i) for i in inc["garrison"].split(",") if i],
            "nulls": [n.to_dict() for n in war.null_squad(
                r["mac"], inc, r["progress"], r["depth"])],
        }
    # which daemon (if any) is on expedition here
    r["expedition"] = next(
        ({"daemon_id": e["daemon_id"], "fights": e["fights"]}
         for e in db.list_expeditions() if e["mac"] == r["mac"]), None)
    # harvest assignments on this rift's nodes
    r["harvests"] = {}
    for h in db.list_harvests(r["mac"]):
        hd = db.get_daemon(h["daemon_id"])
        if hd:
            r["harvests"][str(h["node_index"])] = {
                "daemon_id": hd.id, "name": hd.name, "color":
                    hd.to_dict()["color"],
                "lifetime_bits": round(h["lifetime_bits"], 1),
                "rates": {k: round(v, 2) for k, v in economy.harvest_rates(
                    hd, r, h["node_index"], r["dormant"]).items()},
            }
    return jsonify(r)


# -- the nest --
@app.route("/api/nest")
def nest():
    ticker.apply_drift()
    return jsonify({"daemons": [_daemon_payload(d) for d in db.list_daemons()]})


@app.route("/api/daemon/<int:did>/care", methods=["POST"])
def care(did):
    d = db.get_daemon(did)
    if not d:
        return jsonify({"error": "not_found"}), 404
    guard = _guard_available(d)
    if guard:
        return guard
    action = request.get_json(force=True).get("action")
    fn = {"feed": lambda: d.feed(), "rich": lambda: d.feed(rich=True),
          "rest": d.rest, "play": d.play, "cleanse": d.cleanse}.get(action)
    if not fn:
        return jsonify({"error": "bad_action"}), 400
    fn()
    db.save_daemon(d)
    return jsonify({"daemon": _daemon_payload(d)})


@app.route("/api/daemon/<int:did>/train", methods=["POST"])
def train(did):
    d = db.get_daemon(did)
    if not d:
        return jsonify({"error": "not_found"}), 404
    guard = _guard_available(d)
    if guard:
        return guard
    stat = request.get_json(force=True).get("stat")
    res = d.train(stat)
    if res.get("ok"):
        db.save_daemon(d)
    return jsonify({"result": res, "daemon": _daemon_payload(d)})


@app.route("/api/daemon/<int:did>/evolve", methods=["POST"])
def evolve(did):
    d = db.get_daemon(did)
    if not d:
        return jsonify({"error": "not_found"}), 404
    guard = _guard_available(d)
    if guard:
        return guard
    res = d.evolve()
    if res.get("ok"):
        db.save_daemon(d)
        txt = f"{d.name} evolved to {res['to']}"
        if res["attr_from"] != res["attr_to"]:
            txt += f" — its nature shifted to {res['attr_to']}"
        db.add_event("evolve", txt + ".", daemon_id=d.id)
    return jsonify({"result": res, "daemon": _daemon_payload(d)})


@app.route("/api/daemon/<int:did>/release", methods=["POST"])
def release(did):
    db.release_daemon(did)
    return jsonify({"ok": True})


# -- battle (party) --
@app.route("/api/battle", methods=["POST"])
def battle():
    body = request.get_json(force=True)
    ids = body.get("daemon_ids") or ([body["daemon_id"]] if body.get("daemon_id") else [])
    party = []
    for did in ids[:3]:
        d = db.get_daemon(did)
        if not d:
            return jsonify({"error": "no_daemon"}), 404
        guard = _guard_can_fight(d)
        if guard:
            return guard
        party.append(d)
    if not party:
        return jsonify({"error": "no_daemon"}), 404

    mac = body.get("mac")
    node_index = int(body.get("node_index", 0))
    try:
        r = generate_rift(mac, body.get("hostname", ""), scan.vendor_for(mac))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    if node_index >= len(r["nodes"]):
        return jsonify({"error": "bad_node"}), 400

    prog = db.get_progress(r["mac"])
    node = r["nodes"][node_index]
    enemy = Daemon.from_dict(node["enemy"])
    dim = ticker.dormancy(r["mac"])
    if dim:
        enemy = ticker.dormant_enemy(enemy)
    enemy = war.scale_enemy(enemy, prog)
    foes = [enemy]
    if node["is_boss"]:
        foes += war.boss_minions(enemy, r, prog)

    result = simulate_team(
        party, foes,
        seed_extra=f"{mac}:{node_index}:{sum(d.wins + d.losses for d in party)}")
    won = result["winner"] == "a"

    mults = war.tier_mults(prog)
    reward = {"xp": 0, "levels": 0, "cleared_node": False,
              "boss_down": False, "dormant_bonus": dim, "loot": {},
              "tier": prog["tier"]}
    if won:
        xp_total = int(node["reward_xp"] * mults["xp"]
                       * (ticker.DORMANT_XP_MULT if dim else 1.0))
        xp_each = max(1, xp_total // len(party))
        levels = 0
        for d in party:
            d.wins += 1
            ev = d.gain_xp(xp_each)
            levels += ev["levels"]
            d.care["energy"] = max(0, d.care["energy"] - 8)
            db.save_daemon(d)
        reward["xp"] = xp_each
        reward["levels"] = levels
        if node_index == prog["cleared"]:
            db.set_progress(r["mac"], node_index + 1,
                            prog["boss_down"] or node["is_boss"])
            reward["cleared_node"] = True
            reward["boss_down"] = bool(node["is_boss"])
            loot = economy.node_loot(r, node_index, dim, prog)
            economy.grant(loot)
            reward["loot"] = loot
            if node["is_boss"]:
                db.add_event("boss",
                             f"{', '.join(d.name for d in party)} defeated "
                             f"{enemy.name} — {r['world_name']} is stabilized"
                             f"{f' at Tier {prog['tier']}' if prog['tier'] else ''}.",
                             mac=r["mac"], daemon_id=party[0].id)
    else:
        for d in party:
            d.losses += 1
            d.care["happiness"] = max(0, d.care["happiness"] - 6)
            d.care["energy"] = max(0, d.care["energy"] - 12)
            db.save_daemon(d)

    return jsonify({
        "won": won,
        "battle": result,
        "reward": reward,
        "dormant": dim,
        "party": [_daemon_payload(d) for d in party],
        "foes": [f.to_dict() for f in foes],
        "progress": db.get_progress(r["mac"]),
    })


@app.route("/api/capture", methods=["POST"])
def capture():
    body = request.get_json(force=True)
    mac = body.get("mac")
    try:
        r = generate_rift(mac, body.get("hostname", ""), scan.vendor_for(mac))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    if ticker.dormancy(r["mac"]):
        return jsonify({"error": "rift_dormant",
                        "message": "The rift is dormant — its device is off the "
                                   "network. The signature daemon can't be "
                                   "reached until it returns."}), 400
    prog = db.get_progress(r["mac"])
    if not prog["boss_down"]:
        return jsonify({"error": "boss_not_defeated",
                        "message": "Defeat the rift's Gatekeeper to stabilize it "
                                   "before capturing its signature daemon."}), 400
    wild = Daemon.from_dict(r["signature_daemon"])
    wild.id = None
    db.add_daemon(wild)
    db.add_event("capture", f"{wild.name} was captured from {r['world_name']} "
                            "and settles into the Nest.",
                 mac=r["mac"], daemon_id=wild.id)
    return jsonify({"daemon": wild.to_dict()})


# -- expeditions & journal --
@app.route("/api/expedition", methods=["POST"])
def expedition_start():
    body = request.get_json(force=True)
    d = db.get_daemon(body.get("daemon_id") or -1)
    if not d:
        return jsonify({"error": "no_daemon"}), 404
    guard = _guard_can_fight(d)
    if guard:
        return guard
    mac = body.get("mac")
    try:
        r = generate_rift(mac)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    if db.get_progress(r["mac"])["cleared"] >= len(r["nodes"]):
        return jsonify({"error": "already_cleared",
                        "message": "Every node in this rift is already cleared."}), 400
    if any(e["mac"] == r["mac"] for e in db.list_expeditions()):
        return jsonify({"error": "rift_busy",
                        "message": "A daemon is already working this rift."}), 400
    db.start_expedition(d.id, r["mac"])
    db.add_event("exped_start",
                 f"{d.name} sets out on an expedition into {r['world_name']}.",
                 mac=r["mac"], daemon_id=d.id)
    return jsonify({"ok": True, "daemon": _daemon_payload(d)})


@app.route("/api/expedition/recall", methods=["POST"])
def expedition_recall():
    body = request.get_json(force=True)
    did = body.get("daemon_id") or -1
    d = db.get_daemon(did)
    ex = db.get_expedition(did)
    if not d or not ex:
        return jsonify({"error": "not_found"}), 404
    db.end_expedition(did)
    db.add_event("exped_recall",
                 f"{d.name} was recalled to the Nest "
                 f"({ex['fights']} battle(s) fought).", daemon_id=did)
    return jsonify({"ok": True, "daemon": _daemon_payload(d)})


@app.route("/api/journal")
def journal():
    limit = min(int(request.args.get("limit", "60")), 200)
    return jsonify({"events": db.list_events(limit)})


# -- harvesting --
@app.route("/api/harvest", methods=["POST"])
def harvest_start():
    body = request.get_json(force=True)
    d = db.get_daemon(body.get("daemon_id") or -1)
    if not d:
        return jsonify({"error": "no_daemon"}), 404
    guard = _guard_can_fight(d)
    if guard:
        return guard
    mac = body.get("mac")
    node_index = int(body.get("node_index", -1))
    try:
        r = generate_rift(mac)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    prog = db.get_progress(r["mac"])
    if node_index < 0 or node_index >= len(r["nodes"]):
        return jsonify({"error": "bad_node"}), 400
    if node_index >= prog["cleared"]:
        return jsonify({"error": "node_not_cleared",
                        "message": "Only cleared nodes can be harvested."}), 400
    if any(h["node_index"] == node_index for h in db.list_harvests(r["mac"])):
        return jsonify({"error": "node_busy",
                        "message": "A daemon is already harvesting that node."}), 400
    db.start_harvest(d.id, r["mac"], node_index)
    db.add_event("harvest_start",
                 f"{d.name} begins harvesting node {node_index + 1} of "
                 f"{r['world_name']}.", mac=r["mac"], daemon_id=d.id)
    return jsonify({"ok": True, "daemon": _daemon_payload(d)})


@app.route("/api/harvest/stop", methods=["POST"])
def harvest_stop():
    body = request.get_json(force=True)
    did = body.get("daemon_id") or -1
    d = db.get_daemon(did)
    h = db.get_harvest(did)
    if not d or not h:
        return jsonify({"error": "not_found"}), 404
    # pay out the final stretch before releasing
    try:
        rift = generate_rift(h["mac"])
        economy.accrue_harvest(d, rift, h, ticker.dormancy(h["mac"]))
    except ValueError:
        pass
    db.end_harvest(did)
    db.add_event("harvest_stop",
                 f"{d.name} returns from its harvest node "
                 f"({round(h['lifetime_bits'])} Bits gathered over the stint).",
                 daemon_id=did)
    return jsonify({"ok": True, "daemon": _daemon_payload(d)})


# -- hatchery --
@app.route("/api/hatchery")
def hatchery():
    eggs = db.list_eggs(incubating_only=True)
    now = time.time()
    for e in eggs:
        e["seconds_left"] = max(0, int(e["hatch_at"] - now))
        e["total_seconds"] = int(economy.HATCH_SECONDS)
    return jsonify({
        "eggs": eggs,
        "essence_kinds": economy.ESSENCE_KINDS,
        "element_for": economy.ELEMENT_FOR_ESSENCE,
        "next_cost": {k: economy.egg_cost(k) for k in economy.ESSENCE_KINDS},
    })


@app.route("/api/hatchery/synthesize", methods=["POST"])
def hatchery_synthesize():
    body = request.get_json(force=True)
    res = economy.synthesize_egg(body.get("essence", ""))
    if not res.get("ok"):
        return jsonify(res), 400
    db.add_event("egg_laid",
                 f"A new egg settles into the Hatchery, humming with "
                 f"{body['essence']} essence.")
    return jsonify(res)


# -- the bastion --
@app.route("/api/bastion")
def bastion_view():
    return jsonify({"facilities": bastion.snapshot(),
                    "resources": db.res_all()})


@app.route("/api/bastion/upgrade", methods=["POST"])
def bastion_upgrade():
    body = request.get_json(force=True)
    res = bastion.upgrade(body.get("key", ""))
    if not res.get("ok"):
        return jsonify(res), 400
    f = bastion.FACILITIES[body["key"]]
    msg = (f"{f['name']} rises in the Bastion." if res["level"] == 1
           else f"{f['name']} reaches level {res['level']}.")
    db.add_event("build", msg)
    return jsonify(res)


@app.route("/api/bastion/train", methods=["POST"])
def bastion_train():
    body = request.get_json(force=True)
    d = db.get_daemon(body.get("daemon_id") or -1)
    if not d:
        return jsonify({"error": "no_daemon"}), 404
    guard = _guard_can_fight(d)
    if guard:
        return guard
    res = bastion.assign(d.id, body.get("hall", ""))
    if not res.get("ok"):
        return jsonify(res), 400
    hall = bastion.FACILITIES[body["hall"]]
    db.add_event("train_start",
                 f"{d.name} enters {hall['name']} to train its "
                 f"{hall['stat'].upper()}.", daemon_id=d.id)
    return jsonify({"ok": True, "daemon": _daemon_payload(d)})


@app.route("/api/bastion/withdraw", methods=["POST"])
def bastion_withdraw():
    body = request.get_json(force=True)
    did = body.get("daemon_id") or -1
    d = db.get_daemon(did)
    t = db.get_training(did)
    if not d or not t:
        return jsonify({"error": "not_found"}), 404
    bastion.tick_training()          # bank the final stretch
    t = db.get_training(did) or t
    db.end_training(did)
    db.add_event("train_stop",
                 f"{d.name} leaves {bastion.FACILITIES[t['hall']]['name']} "
                 f"(+{t['gained']} {bastion.FACILITIES[t['hall']]['stat'].upper()} "
                 f"over the stay).", daemon_id=did)
    return jsonify({"ok": True, "daemon": _daemon_payload(db.get_daemon(did))})


# -- overclock & incursions --
@app.route("/api/overclock", methods=["POST"])
def overclock():
    body = request.get_json(force=True)
    mac = body.get("mac")
    try:
        r = generate_rift(mac)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    res = war.overclock(r["mac"], len(r["nodes"]))
    if not res.get("ok"):
        return jsonify(res), 400
    db.add_event("overclock",
                 f"{r['world_name']} has been OVERCLOCKED to Tier {res['tier']} — "
                 f"the rift reboots hungrier and richer.", mac=r["mac"])
    return jsonify(res)


@app.route("/api/incursion/garrison", methods=["POST"])
def incursion_garrison():
    body = request.get_json(force=True)
    mac = body.get("mac", "")
    from core.seed import normalize_mac
    try:
        mac = normalize_mac(mac)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    if not db.get_incursion(mac):
        return jsonify({"error": "no_incursion"}), 404
    ids = [int(i) for i in (body.get("daemon_ids") or [])][:3]
    db.set_garrison(mac, ids)
    names = [db.get_daemon(i).name for i in ids if db.get_daemon(i)]
    if names:
        db.add_event("garrison",
                     f"{', '.join(names)} take up garrison duty at "
                     f"{generate_rift(mac)['world_name']}.", mac=mac)
    return jsonify({"ok": True, "garrison": ids})


@app.route("/api/incursion/repel", methods=["POST"])
def incursion_repel():
    body = request.get_json(force=True)
    mac = body.get("mac", "")
    from core.seed import normalize_mac
    try:
        mac = normalize_mac(mac)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    defenders = []
    for did in (body.get("daemon_ids") or [])[:3]:
        d = db.get_daemon(int(did))
        if not d:
            continue
        if db.get_expedition(d.id) or db.get_training(d.id):
            return jsonify({"error": "busy",
                            "message": f"{d.name} can't fight right now."}), 400
        defenders.append(d)
    if not defenders:
        return jsonify({"error": "no_defenders"}), 400
    res = war.resolve_incursion(mac, defenders, manual=True)
    if not res.get("ok"):
        return jsonify(res), 400
    return jsonify(res)


if __name__ == "__main__":
    db.init_db()
    ticker.start()
    ip = scan.local_ipv4() or "127.0.0.1"
    port = int(os.environ.get("AETHER_PORT", "8787"))
    print("\n  AETHER is live on your network")
    print(f"    Local:   http://127.0.0.1:{port}")
    print(f"    Network: http://{ip}:{port}   <- open this on any device\n")
    app.run(host="0.0.0.0", port=port, debug=False)
