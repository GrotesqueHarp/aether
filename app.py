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
from core import world as world_mod
from core.battle import simulate, simulate_team

app = Flask(__name__, static_folder="static", static_url_path="")

_VERSION_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "VERSION")
try:
    VERSION = open(_VERSION_FILE).read().strip()
except OSError:
    VERSION = "dev"


# ---- helpers ---------------------------------------------------------------
def _state_sig() -> str:
    """A fingerprint of everything STRUCTURAL — the things that change what the
    page should be drawing, rather than the numbers ticking up inside it.

    Deliberately excludes resource totals and harvest counters: those move
    every few seconds and live in the resource bar, which updates on its own
    without redrawing the view. Redrawing the whole page just because Bits went
    up is what made a fixed refresh interval feel intrusive.
    """
    parts = [str(len(db.list_daemons())),
             str(len(db.list_eggs())),
             str(len(db.list_harvests())),
             str(len(db.list_training())),
             str(len(db.list_expeditions())),
             str(len(db.list_incursions()))]
    for dev in db.list_devices():
        p = db.get_progress(dev["mac"])
        parts.append(f"{dev['mac']}:{p['cleared']}:{p['tier']}:{p['ward']}:"
                     f"{p['captures_taken']}:{1 if dev['online'] else 0}")
    for key, lvl in sorted(db.all_facility_levels().items()):
        parts.append(f"{key}{lvl}")
    return str(hash("|".join(parts)) & 0xFFFFFFFF)


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
    out["sell_value"] = economy.sell_value(d)
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
    """Battles BORROW a daemon. Harvesters and trainees are on your own
    network — they can step away for a fight and go straight back to work
    afterward. Only an expedition physically removes a daemon from reach.

    This matters more than it sounds: when working daemons were locked out of
    combat, the only daemon free to fight was whichever hatched most recently,
    so parties never formed and the whole 3v3 layer sat unused.
    """
    ex = db.get_expedition(d.id) if d.id else None
    if ex and ex["state"] == "active":
        return jsonify({"error": "on_expedition",
                        "message": f"{d.name} is away on an expedition. "
                                   "Recall it first."}), 400
    return None


def _guard_can_commit(d: Daemon):
    """Long-term postings are exclusive — a daemon can't harvest, train, and
    be on expedition at once."""
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


def _settle_work(d: Daemon):
    """Pay out a borrowed worker's earnings up to now, so a fight can't
    retroactively change what it already earned."""
    hv = db.get_harvest(d.id) if d.id else None
    if hv:
        try:
            economy.accrue_harvest(d, generate_rift(hv["mac"]), hv,
                                   ticker.dormancy(hv["mac"]))
        except ValueError:
            pass


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
        "sig": _state_sig(),
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
    """Resolve rifts, up to what the Array can currently hold.

    Real devices on your network are resolved first — they make the most
    characterful worlds. Once they're exhausted, further Array levels pull
    rifts out of open subspace instead, so discovery is never capped by how
    much hardware you happen to own.
    """
    cap = bastion.array_capacity(db.facility_level("array"))
    known = {d["mac"] for d in db.list_devices()}
    found = []

    if len(known) < cap:
        if request.args.get("mock") == "1":
            devs = scan.mock_devices()
            meta = {"subnet": "192.168.1.0/24 (mock)", "swept": False, "mock": True}
        else:
            result = scan.discover(do_sweep=request.args.get("sweep", "1") == "1")
            devs, meta = result["devices"], result["meta"]
        for d in devs:
            if d["mac"] in known:
                db.upsert_device(d["mac"], d.get("hostname", ""), d.get("ip", ""),
                                 d.get("vendor", ""), online=True)
                continue
            if len(known) >= cap:
                break
            db.upsert_device(d["mac"], d.get("hostname", ""), d.get("ip", ""),
                             d.get("vendor", ""), online=True)
            db.set_found_at(d["mac"], db.facility_level("array"))
            known.add(d["mac"])
            found.append(d["mac"])
    else:
        meta = {"subnet": "", "swept": False, "at_capacity": True}

    # fill any remaining Array capacity from subspace
    idx = 0
    while len(known) < cap and idx < 500:
        d = scan.deep_signal(idx)
        idx += 1
        if d["mac"] in known:
            continue
        db.upsert_device(d["mac"], d["hostname"], d["ip"], d["vendor"], online=True)
        db.set_found_at(d["mac"], db.facility_level("array"))
        known.add(d["mac"])
        found.append(d["mac"])

    for mac in found:
        db.add_event("rift_found",
                     f"The Array resolved a new rift: "
                     f"{generate_rift(mac)['world_name']}.", mac=mac)

    meta["capacity"] = cap
    meta["resolved"] = len(known)
    meta["at_capacity"] = len(known) >= cap
    return jsonify({"devices": db.list_devices(), "meta": meta,
                    "found": len(found), "capacity": cap})


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
    r["dormant"] = False        # rifts stay resolved once the Array finds them
    prog = r["progress"]
    r["window"] = world_mod.layer_window(r["mac"], prog["cleared"], prog["tier"])
    for spec in r["window"]:
        spec["state"] = ("cleared" if spec["layer"] <= prog["cleared"]
                         else "frontier" if spec["layer"] == prog["cleared"] + 1
                         else "locked")
        spec["power"] = sum(f.power() for f in world_mod.layer_enemies(
            r["mac"], spec["layer"], prog["tier"]))
    r["captures_available"] = world_mod.captures_available(
        prog["cleared"], prog["captures_taken"])
    r["next_capture_layer"] = min(world_mod.LAYERS,
        (prog["captures_taken"] + 1) * world_mod.CAPTURE_EVERY)
    r["fully_cleared"] = prog["cleared"] >= world_mod.LAYERS
    r["harvest_every"] = world_mod.HARVEST_EVERY
    r["overclock_cost"] = war.overclock_cost(r["progress"]["tier"])
    r["next_tier_boss_power"] = war.next_tier_boss_power(r["mac"])
    r["can_downclock"] = r["progress"]["tier"] > 0
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


@app.route("/api/daemon/<int:did>/sell", methods=["POST"])
@app.route("/api/daemon/<int:did>/release", methods=["POST"])
def sell(did):
    d = db.get_daemon(did)
    if not d:
        return jsonify({"error": "not_found"}), 404
    if len(db.list_daemons()) <= 1:
        return jsonify({"error": "last_daemon",
                        "message": "This is your only daemon — you can't let it "
                                   "go."}), 400
    ex = db.get_expedition(did)
    if ex and ex["state"] == "active":
        return jsonify({"error": "on_expedition",
                        "message": f"{d.name} is away on an expedition. Recall "
                                   "it first."}), 400
    payout = economy.sell_value(d)
    for kind, amt in payout.items():
        db.res_add(kind, amt)
    db.end_harvest(did)          # vacate any posting it held
    db.end_training(did)
    db.release_daemon(did)
    db.add_event("sell",
                 f"{d.name} ({'★' * d.rarity} {d.stage}) was released back into "
                 f"the aether, leaving "
                 + ", ".join(f"{v:g} {k.replace('essence.', '')}"
                             for k, v in payout.items()) + ".",
                 daemon_id=did)
    return jsonify({"ok": True, "payout": payout, "name": d.name})


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
        _settle_work(d)
        party.append(d)
    if not party:
        return jsonify({"error": "no_daemon"}), 404

    mac = body.get("mac")
    layer = int(body.get("layer", body.get("node_index", 0)) or 0)
    try:
        r = generate_rift(mac, body.get("hostname", ""), scan.vendor_for(mac))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    prog = db.get_progress(r["mac"])
    if layer < 1 or layer > world_mod.LAYERS:
        return jsonify({"error": "bad_layer"}), 400
    if layer > prog["cleared"] + 1:
        return jsonify({"error": "layer_locked",
                        "message": "Dig through the layers above this one "
                                   "first."}), 400

    spec = world_mod.layer_spec(r["mac"], layer, prog["tier"])
    foes = world_mod.layer_enemies(r["mac"], layer, prog["tier"])
    dim = ticker.dormancy(r["mac"])
    if dim:
        foes = [ticker.dormant_enemy(f) for f in foes]

    result = simulate_team(
        party, foes,
        seed_extra=f"{mac}:{layer}:{sum(d.wins + d.losses for d in party)}")
    won = result["winner"] == "a"

    reward = {"xp": 0, "levels": 0, "cleared_layer": False, "layer": layer,
              "gatekeeper": spec["is_gatekeeper"], "dormant_bonus": dim,
              "loot": {}, "tier": prog["tier"], "capture_unlocked": False}
    if won:
        xp_total = int(spec["reward_xp"] * (ticker.DORMANT_XP_MULT if dim else 1.0))
        xp_each = max(1, xp_total // len(party))
        levels = 0
        for d in party:
            d.wins += 1
            levels += d.gain_xp(xp_each)["levels"]
            d.care["energy"] = max(0, d.care["energy"] - 5)
            db.save_daemon(d)
        reward["xp"] = xp_each
        reward["levels"] = levels
        if layer == prog["cleared"] + 1:          # frontier: real progress
            db.set_progress(r["mac"], layer, layer >= world_mod.LAYERS)
            db.bump_layers_dug()
            reward["cleared_layer"] = True
            loot = economy.node_loot(r, layer, dim, prog)
            economy.grant(loot)
            reward["loot"] = loot
            if layer % world_mod.CAPTURE_EVERY == 0:
                reward["capture_unlocked"] = True
                db.add_event("capture_ready",
                             f"Layer {layer} of {r['world_name']} opens — a "
                             f"daemon can be drawn out here.", mac=r["mac"])
            if spec["is_gatekeeper"]:
                names = ", ".join(d.name for d in party)
                tier_note = f" (Tier {prog['tier']})" if prog["tier"] else ""
                db.add_event("boss",
                             f"{names} broke the Gatekeeper at layer {layer} "
                             f"of {r['world_name']}{tier_note}.",
                             mac=r["mac"], daemon_id=party[0].id)
    else:
        for d in party:
            d.losses += 1
            d.care["happiness"] = max(0, d.care["happiness"] - 6)
            d.care["energy"] = max(0, d.care["energy"] - 12)
            db.save_daemon(d)

    return jsonify({
        "won": won, "battle": result, "reward": reward, "dormant": dim,
        "party": [_daemon_payload(d) for d in party],
        "foes": [f.to_dict() for f in foes],
        "progress": db.get_progress(r["mac"]),
    })


@app.route("/api/capture", methods=["POST"])
def capture():
    body = request.get_json(force=True)
    try:
        r = generate_rift(body.get("mac"), body.get("hostname", ""),
                          scan.vendor_for(body.get("mac")))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    if False:
        return jsonify({"error": "rift_dormant",
                        "message": "The rift is dormant — its device is off "
                                   "the network. Nothing can be drawn out "
                                   "until it returns."}), 400
    prog = db.get_progress(r["mac"])
    if world_mod.captures_available(prog["cleared"], prog["captures_taken"]) <= 0:
        nxt = (prog["captures_taken"] + 1) * world_mod.CAPTURE_EVERY
        return jsonify({"error": "no_capture",
                        "message": f"Dig to layer {nxt} to draw out another "
                                   f"daemon."}), 400
    milestone = prog["captures_taken"] + 1
    wild = world_mod.capture_daemon(r["mac"], milestone, prog["tier"])
    wild.id = None
    db.add_daemon(wild)
    db.set_progress_fields(r["mac"], captures_taken=milestone)
    db.add_event("capture",
                 f"{wild.name} was drawn out of {r['world_name']} at layer "
                 f"{milestone * world_mod.CAPTURE_EVERY} and settles into "
                 f"the Nest.", mac=r["mac"], daemon_id=wild.id)
    return jsonify({"daemon": wild.to_dict(),
                    "captures_available": world_mod.captures_available(
                        prog["cleared"], milestone)})


# -- expeditions & journal --
@app.route("/api/expedition", methods=["POST"])
def expedition_start():
    body = request.get_json(force=True)
    d = db.get_daemon(body.get("daemon_id") or -1)
    if not d:
        return jsonify({"error": "no_daemon"}), 404
    guard = _guard_can_commit(d)
    if guard:
        return guard
    mac = body.get("mac")
    try:
        r = generate_rift(mac)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    if db.get_progress(r["mac"])["cleared"] >= world_mod.LAYERS:
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
    guard = _guard_can_commit(d)
    if guard:
        return guard
    mac = body.get("mac")
    node_index = int(body.get("node_index", -1))
    try:
        r = generate_rift(mac)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    prog = db.get_progress(r["mac"])
    if node_index < 1 or node_index > world_mod.LAYERS:
        return jsonify({"error": "bad_layer"}), 400
    if node_index > prog["cleared"]:
        return jsonify({"error": "layer_not_cleared",
                        "message": "Only cleared layers can be harvested."}), 400
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


# -- danger zone --
@app.route("/api/reset", methods=["POST"])
def reset():
    """Wipe progression and start over. Requires an explicit confirmation
    string so a stray POST can't nuke a save."""
    body = request.get_json(force=True, silent=True) or {}
    if body.get("confirm") != "RESET":
        return jsonify({"error": "not_confirmed",
                        "message": 'Send {"confirm": "RESET"} to proceed.'}), 400
    keep = bool(body.get("keep_devices", True))
    cleared = db.reset_all(keep_devices=keep)
    ticker.reset_clocks()
    db.add_daemon(starter_daemon())
    db.set_meta("bootstrapped", "1")
    db.add_event("reset", "The aether was reformatted. Everything begins again.")
    return jsonify({"ok": True, "cleared": cleared, "kept_devices": keep})


# -- the crucible --
@app.route("/api/crucible")
def crucible():
    return jsonify({
        "essence_kinds": economy.ESSENCE_KINDS,
        "ratio": economy.TRANSMUTE_RATIO,
        "bits_per": economy.TRANSMUTE_BITS_PER,
        "reclaim_cost": economy.reclaim_cost(1),
        "resources": db.res_all(),
    })


@app.route("/api/crucible/transmute", methods=["POST"])
def crucible_transmute():
    b = request.get_json(force=True)
    src, dst = b.get("from", ""), b.get("to", "")
    res = economy.transmute(src, dst, b.get("amount", 10))
    if not res.get("ok"):
        return jsonify(res), 400
    spent = res["cost"].get("essence." + src, 0)
    db.add_event("transmute",
                 f"The Crucible renders {spent:.0f} {src} into "
                 f"{res['gained']:.0f} {dst}.")
    return jsonify(res)


@app.route("/api/crucible/reclaim", methods=["POST"])
def crucible_reclaim():
    b = request.get_json(force=True)
    res = economy.reclaim(b.get("essence", ""), b.get("count", 1))
    if not res.get("ok"):
        return jsonify(res), 400
    db.add_event("reclaim",
                 f"The Crucible compresses raw essence into "
                 f"{res['gained']:.0f} Core(s).")
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
    guard = _guard_can_commit(d)
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
    res = war.overclock(r["mac"], world_mod.LAYERS)
    if not res.get("ok"):
        return jsonify(res), 400
    db.set_progress_fields(r["mac"], captured=0, captures_taken=0)
    db.add_event("overclock",
                 f"{r['world_name']} has been OVERCLOCKED to Tier {res['tier']} — "
                 f"the rift reboots hungrier and richer.", mac=r["mac"])
    return jsonify(res)


@app.route("/api/downclock", methods=["POST"])
def downclock():
    body = request.get_json(force=True)
    try:
        r = generate_rift(body.get("mac"))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    res = war.downclock(r["mac"])
    if not res.get("ok"):
        return jsonify(res), 400
    db.set_progress_fields(r["mac"], captured=0, captures_taken=0)
    db.add_event("downclock",
                 f"{r['world_name']} powers down to Tier {res['tier']} — "
                 f"the rift cools and must be retaken.", mac=r["mac"])
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
