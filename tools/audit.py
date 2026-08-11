#!/usr/bin/env python3
"""
audit.py — Does the whole app actually work?

Two passes:

  API   every endpoint, against a seeded save, checking status codes and the
        shape of what comes back.
  UI    every navigation target in a real browser, checking each view rendered
        the elements it's supposed to and that the console stayed clean.

The UI pass is the important half. Nearly every bug that has reached a release
here was invisible server-side: a button defined but never rendered, a nav item
whose click handler was overwritten, a file missing from the Docker image. The
API can be perfect while the page is broken.

    python3 tools/audit.py                 # assumes a server on :8787
    python3 tools/audit.py --seed          # populate a save first
    python3 tools/audit.py --no-ui         # skip the browser pass
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

BASE = "http://localhost:8787"
OK, BAD = [], []


def call(method: str, path: str, body=None, expect=(200,)):
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            payload = r.read().decode()
            code = r.status
    except urllib.error.HTTPError as e:
        payload, code = e.read().decode(), e.code
    except Exception as e:
        BAD.append((f"{method} {path}", f"unreachable: {e}"))
        return None
    if code not in expect:
        BAD.append((f"{method} {path}", f"HTTP {code}: {payload[:120]}"))
        return None
    OK.append(f"{method} {path}")
    try:
        return json.loads(payload)
    except ValueError:
        return payload


def check(label: str, cond: bool, detail: str = ""):
    (OK.append(label) if cond else BAD.append((label, detail or "failed")))


# ----------------------------------------------------------- docker context --
def audit_docker():
    """Would `docker build` actually find everything the Dockerfile COPYs?

    This exists because a COPY of a file excluded by .dockerignore fails the
    build with an opaque "failed to compute cache key ... not found" — and it
    cannot be caught by running the app, only by building the image. Which is
    easy to skip.
    """
    import fnmatch
    import os
    try:
        with open("Dockerfile", encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    except OSError:
        BAD.append(("Dockerfile", "not found"))
        return
    try:
        with open(".dockerignore", encoding="utf-8") as fh:
            patterns = [l.strip() for l in fh
                        if l.strip() and not l.startswith("#")]
    except OSError:
        patterns = []

    def ignored(path: str) -> bool:
        for pat in patterns:
            p = pat.rstrip("/")
            if fnmatch.fnmatch(path, p) or fnmatch.fnmatch(os.path.basename(path), p):
                return True
            if path.startswith(p + "/"):
                return True
        return False

    for line in lines:
        line = line.strip()
        if not line.upper().startswith("COPY "):
            continue
        parts = line[5:].split()
        if len(parts) < 2:
            continue
        for src in parts[:-1]:
            if src.startswith("--"):
                continue
            exists = os.path.exists(src.rstrip("/"))
            check(f"docker COPY {src} exists", exists, "no such file in the repo")
            if exists:
                check(f"docker COPY {src} in context", not ignored(src.rstrip("/")),
                      "excluded by .dockerignore — the build will fail here")


# ------------------------------------------------------------------ seeding --
def seed():
    call("POST", "/api/bootstrap", {}, expect=(200, 400))
    call("GET", "/api/scan?mock=1")
    import os
    os.environ.setdefault("AETHER_DB", "aether.db")
    sys.path.insert(0, ".")
    from core import db
    db.res_add("bits", 500000); db.res_add("cores", 400)
    db.res_add("aethercite", 25)
    for k in ("ferro", "loam", "tide", "volt", "umbra", "plasma"):
        db.res_add("essence." + k, 6000)
    devs = db.list_devices()
    if devs:
        mac = devs[0]["mac"]
        db.set_progress_fields(mac, cleared=40, mastery_xp=60000)
        db.add_mastery_xp(mac, 0)
    d = db.list_daemons()
    if d:
        d[0].stage = "Champion"; d[0].level = 30
        db.save_daemon(d[0])
    print("  seeded a save for the audit")


# ---------------------------------------------------------------- API pass --
def audit_api():
    st = call("GET", "/api/state")
    if st:
        for key in ("version", "schema", "resources", "rates", "sig"):
            check(f"state.{key}", key in st, f"missing from /api/state")

    devs = call("GET", "/api/devices") or {}
    macs = [d["mac"] for d in devs.get("devices", [])]
    check("devices resolved", bool(macs), "no rifts — run with --seed")

    if macs:
        mac = macs[0]
        r = call("GET", f"/api/rift/{mac}")
        if r:
            for key in ("layers", "window", "mastery", "resonance", "harvests",
                        "captures_available", "overclock_cost", "harvest_every"):
                check(f"rift.{key}", key in r, "missing from rift payload")
            check("rift.mastery.level", isinstance(r.get("mastery", {}).get("level"), int))

    nest = call("GET", "/api/nest")
    if nest and nest.get("daemons"):
        d = nest["daemons"][0]
        for key in ("battle_stats", "power", "equipped", "glyph_slots",
                    "ascensions", "can_ascend", "sell_value"):
            check(f"daemon.{key}", key in d, "missing from daemon payload")

    for path in ("/api/journal", "/api/hatchery", "/api/bastion", "/api/crucible",
                 "/api/objectives",
                 "/api/glyphs", "/api/records?days=30", "/api/changelog"):
        call("GET", path)

    cl = call("GET", "/api/changelog")
    if cl is not None:
        check("changelog has releases", bool(cl.get("releases")),
              "CHANGELOG.md missing — not copied into the Docker image?")

    gl = call("GET", "/api/glyphs")
    if gl is not None:
        check("glyph catalogue", len(gl.get("catalogue", [])) >= 7)

    ba = call("GET", "/api/bastion")
    if ba is not None:
        facs = ba.get("facilities", {})
        check("bastion facilities", len(facs) >= 9)
        check("array present", "array" in facs)
        for key, f in facs.items():
            check(f"facility {key} cost", isinstance(f.get("next_cost"), dict),
                  "upgrade_cost returned nothing")

    # guarded endpoints must refuse cleanly rather than 500
    call("POST", "/api/reset", {}, expect=(400,))
    call("POST", "/api/reset", {"confirm": "RESET", "scope": "bogus"}, expect=(400,))
    call("POST", "/api/glyphs/craft", {"kind": "nope", "quality": 1}, expect=(400,))
    call("POST", "/api/daemon/999999/ascend", {}, expect=(404,))
    call("POST", "/api/battle", {"daemon_ids": [], "mac": "x", "layer": 1},
         expect=(400, 404))


# ----------------------------------------------------------------- UI pass --
UI_VIEWS = [
    ("Rifts",     "scan",      ".rift, .empty"),
    ("The Nest",  "nest",      "#tank"),
    ("Bastion",   "bastion",   ".fac"),
    ("Pulse",     "pulse",     ".jrow, .empty"),
    ("Compass",   "compass",   ".obj, .empty"),
    ("Records",   "records",   ".rec, .empty"),
    ("Changelog", "changelog", ".clrel, .empty"),
]


def audit_ui():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("  (playwright not installed — skipping UI pass)")
        return
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1280, "height": 900})
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        # record which request failed, not just that one did
        pg.on("response", lambda r: errors.append(f"HTTP {r.status} {r.url}")
              if r.status >= 400 else None)
        pg.goto(BASE, wait_until="networkidle")
        pg.wait_for_timeout(2500)
        # dismiss the homecoming dialog if it appears
        if pg.query_selector(".awaygrid"):
            pg.click("text=Continue"); pg.wait_for_timeout(400)

        for label, view, selector in UI_VIEWS:
            pg.click(f"text={label}")
            pg.wait_for_timeout(1600)
            found = pg.query_selector(selector)
            check(f"view {label}", found is not None,
                  f"nothing matching '{selector}' rendered")
            active = pg.evaluate(
                "v=>{const n=document.querySelector('.navitem.active');"
                "return n?n.dataset.view:null}", view)
            check(f"nav highlights {label}", active == view,
                  f"active nav is '{active}', expected '{view}'")

        # the dashboard is special: it hides the chrome
        pg.click("text=Dashboard")
        pg.wait_for_timeout(2500)
        check("dashboard opens", pg.evaluate(
            "()=>document.body.classList.contains('dashmode')"),
            "clicking Dashboard did not enter dash mode")
        check("dashboard renders tiles", len(pg.query_selector_all(".dtile")) > 0)
        pg.keyboard.press("Escape"); pg.wait_for_timeout(1200)
        check("dashboard exits", not pg.evaluate(
            "()=>document.body.classList.contains('dashmode')"))

        # a rift detail view
        pg.click("text=Rifts"); pg.wait_for_timeout(1500)
        card = pg.query_selector(".rift")
        if card:
            card.click(); pg.wait_for_timeout(2000)
            for sel, name in ((".mastery", "mastery panel"),
                              (".depthbar", "depth bar"),
                              (".layer", "layer rows")):
                check(f"rift detail: {name}", pg.query_selector(sel) is not None)

        check("no console errors", not errors, "; ".join(errors[:3]))
        b.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", action="store_true", help="populate a save first")
    ap.add_argument("--no-ui", action="store_true")
    ap.add_argument("--base", default=BASE)
    a = ap.parse_args()
    globals()["BASE"] = a.base

    print(f"auditing {a.base}\n")
    if a.seed:
        seed()
    print("Docker context pass...")
    audit_docker()
    print("API pass...")
    audit_api()
    if not a.no_ui:
        print("UI pass...")
        audit_ui()

    print(f"\n{'='*60}")
    print(f"  {len(OK)} passed, {len(BAD)} failed")
    print(f"{'='*60}")
    for label, why in BAD:
        print(f"  FAIL  {label}\n        {why}")
    return 1 if BAD else 0


if __name__ == "__main__":
    sys.exit(main())
