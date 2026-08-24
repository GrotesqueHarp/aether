"""
updates.py — "there's a new version" and "please install it".

Two deliberately separate halves, because they have very different risk:

  CHECKING   asks github.com for one line of text: the VERSION file on main.
             Sends nothing about your save, your LAN, or you. Off by default
             anyway — design constraint #5 says AETHER runs air-gapped, so an
             install that never asked to phone home never does.

  APPLYING   does NOT happen here. The app runs inside a container with no
             git, no docker CLI, and no docker socket — by design. Instead
             this writes a request file onto the /data volume and a small
             helper on the HOST notices it and runs update.sh. See
             tools/aether-update-watch.sh.

             The container therefore never executes the update, and never
             needs host access to do it. That matters: docker-compose.yml uses
             host networking with no authentication, so anything on your LAN
             can reach this API. Wiping a save is recoverable; handing out
             root on the LXC is not.
"""

from __future__ import annotations

import json
import os
import time
import urllib.request

from . import db

VERSION_URL = os.environ.get(
    "AETHER_VERSION_URL",
    "https://raw.githubusercontent.com/GrotesqueHarp/aether/main/VERSION")
CHECK_TIMEOUT = float(os.environ.get("AETHER_UPDATE_TIMEOUT", "4"))
CHECK_EVERY_H = float(os.environ.get("AETHER_UPDATE_CHECK_HOURS", "24"))

# Both live on the mounted volume, which is the only thing the container and
# the host reliably share.
_DATA_DIR = os.path.dirname(os.environ.get("AETHER_DB", "/data/aether.db")) or "."
REQUEST_FILE = os.path.join(_DATA_DIR, "update-request")
STATUS_FILE = os.path.join(_DATA_DIR, "update-status.json")
HELPER_STALE_S = float(os.environ.get("AETHER_UPDATE_HELPER_STALE", "900"))


def _repo_version() -> str:
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "VERSION")
    try:
        return open(path).read().strip()
    except OSError:
        return "dev"


def parse(v: str) -> tuple:
    """'0.25.3' -> (0, 25, 3). Unparseable parts sort as -1 so a garbage
    version never claims to be newer than a real one."""
    out = []
    for part in str(v).strip().lstrip("v").split("."):
        try:
            out.append(int(part))
        except ValueError:
            out.append(-1)
    return tuple(out) or (-1,)


def is_newer(candidate: str, current: str) -> bool:
    if not candidate or candidate in ("dev", "?"):
        return False
    return parse(candidate) > parse(current)


# ------------------------------------------------------------------ settings --
def check_enabled() -> bool:
    return db.get_meta("update_check_enabled") == "1"


def set_check_enabled(on: bool):
    db.set_meta("update_check_enabled", "1" if on else "0")
    if not on:                       # forget what we learned while it was on
        db.set_meta("update_latest", "")
        db.set_meta("update_checked_at", "")


# ------------------------------------------------------------------ checking --
def check_now(force: bool = False) -> dict:
    """Ask for the latest VERSION. Never raises: a failed check is a
    non-event, not an error the player has to deal with."""
    if not (force or check_enabled()):
        return {"ok": False, "reason": "disabled"}
    try:
        req = urllib.request.Request(
            VERSION_URL, headers={"User-Agent": "aether-update-check"})
        with urllib.request.urlopen(req, timeout=CHECK_TIMEOUT) as r:
            latest = r.read(64).decode("utf-8", "replace").strip()
    except Exception as e:
        db.set_meta("update_checked_at", str(time.time()))
        db.set_meta("update_error", type(e).__name__)
        return {"ok": False, "reason": "unreachable",
                "error": type(e).__name__}
    if not latest or len(latest) > 32:
        return {"ok": False, "reason": "bad_response"}
    db.set_meta("update_latest", latest)
    db.set_meta("update_checked_at", str(time.time()))
    db.set_meta("update_error", "")
    return {"ok": True, "latest": latest,
            "available": is_newer(latest, _repo_version())}


def maybe_check(now: float | None = None):
    """Called from the ticker. Silent, rate-limited, opt-in."""
    if not check_enabled():
        return
    now = now or time.time()
    try:
        last = float(db.get_meta("update_checked_at") or 0)
    except ValueError:
        last = 0.0
    if now - last < CHECK_EVERY_H * 3600:
        return
    check_now()


# ------------------------------------------------------------------ applying --
def _read_status() -> dict:
    try:
        with open(STATUS_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def helper_state(status: dict | None = None) -> str:
    """absent | idle | working — is anything on the host listening?"""
    status = _read_status() if status is None else status
    if not status:
        return "absent"
    try:
        beat = float(status.get("heartbeat", 0))
    except (TypeError, ValueError):
        return "absent"
    if time.time() - beat > HELPER_STALE_S:
        return "absent"
    return "working" if status.get("state") == "working" else "idle"


def request_update() -> dict:
    """Ask the host helper to run update.sh. Writes a file; runs nothing."""
    status = _read_status()
    state = helper_state(status)
    if state == "absent":
        return {"ok": False, "reason": "helper_absent"}
    if state == "working":
        return {"ok": False, "reason": "already_running"}
    if os.path.exists(REQUEST_FILE):
        return {"ok": False, "reason": "already_requested"}
    try:
        with open(REQUEST_FILE, "w") as f:
            f.write(json.dumps({"requested_at": time.time(),
                                "from_version": _repo_version()}))
    except OSError as e:
        return {"ok": False, "reason": "cannot_write", "error": str(e)}
    db.add_event("build", "Update requested — the host helper will apply it "
                          "and restart AETHER shortly.")
    return {"ok": True, "requested": True}


def snapshot() -> dict:
    current = _repo_version()
    latest = db.get_meta("update_latest") or ""
    status = _read_status()
    try:
        checked = float(db.get_meta("update_checked_at") or 0)
    except ValueError:
        checked = 0.0
    return {
        "current": current,
        "latest": latest,
        "available": bool(latest) and is_newer(latest, current),
        "check_enabled": check_enabled(),
        "checked_at": checked or None,
        "check_error": db.get_meta("update_error") or "",
        "helper": helper_state(status),
        "requested": os.path.exists(REQUEST_FILE),
        "last_run": {k: status.get(k) for k in
                     ("state", "ok", "message", "finished", "from", "to")}
        if status else None,
    }
