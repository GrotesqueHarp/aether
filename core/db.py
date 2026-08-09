"""
db.py — SQLite persistence.

v0.2 adds three tables to support the living-world systems:
  devices      — every device AETHER has ever seen, with online/last_seen so
                 rifts can go dormant when their device leaves the network
  events       — the journal: everything that happens while you're not looking
  expeditions  — idle dispatches: a daemon assigned to grind a rift on its own

World generation is still never stored — worlds regenerate from the MAC.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from typing import Optional

from .daemon import Daemon

DB_PATH = os.environ.get(
    "AETHER_DB", os.path.join(os.path.dirname(__file__), "..", "aether.db"))

# --- schema versioning -------------------------------------------------------
# Bump SCHEMA_VERSION whenever the shape of the DB changes, and add a matching
# entry to MIGRATIONS. Migrations run sequentially at startup (init_db), so an
# old volume from any previous release upgrades cleanly and save data survives.
#
# Rules of thumb:
#   * new TABLES need no migration — the CREATE TABLE IF NOT EXISTS statements
#     in init_db handle them; just bump the version.
#   * new COLUMNS need an ALTER TABLE here (SQLite can't add columns any other
#     way without rebuilding the table).
#   * data reshaping (e.g. renaming a care meter inside the daemons JSON blob)
#     gets a Python function.
SCHEMA_VERSION = 7


def _migrate_1_to_2(c: sqlite3.Connection):
    """v0.1 -> v0.2: devices/events/expeditions tables (created by init_db);
    nothing to reshape."""


def _migrate_2_to_3(c: sqlite3.Connection):
    """v0.2 -> v0.4: resources/harvests/eggs tables (created by init_db);
    nothing to reshape."""


def _migrate_3_to_4(c: sqlite3.Connection):
    """v0.4 -> v0.6: rift_progress gains tier/ward/signal (Overclock + the
    Null); facilities/training/incursions tables come from init_db."""
    cols = {r["name"] for r in c.execute("PRAGMA table_info(rift_progress)")}
    if "tier" not in cols:
        c.execute("ALTER TABLE rift_progress ADD COLUMN tier INTEGER NOT NULL DEFAULT 0")
    if "ward" not in cols:
        c.execute("ALTER TABLE rift_progress ADD COLUMN ward INTEGER NOT NULL DEFAULT 0")
    if "signal" not in cols:
        c.execute("ALTER TABLE rift_progress ADD COLUMN signal REAL NOT NULL DEFAULT 0")


def _migrate_4_to_5(c: sqlite3.Connection):
    """v0.7 -> v0.7.2: rift_progress.captured — the signature daemon was
    infinitely re-capturable, so one cleared rift could mint unlimited
    daemons."""
    cols = {r["name"] for r in c.execute("PRAGMA table_info(rift_progress)")}
    if "captured" not in cols:
        c.execute("ALTER TABLE rift_progress ADD COLUMN captured INTEGER NOT NULL DEFAULT 0")


def _migrate_5_to_6(c: sqlite3.Connection):
    """v0.7.2 -> v0.8: rifts became a 100-layer descent instead of 4-7 discrete
    nodes, so `cleared` changes meaning from 'nodes beaten' to 'deepest layer
    reached'. Old progress is converted approximately — a finished rift is
    credited with the full descent, otherwise ~12 layers per node cleared."""
    cols = {r["name"] for r in c.execute("PRAGMA table_info(rift_progress)")}
    if "captures_taken" not in cols:
        c.execute("ALTER TABLE rift_progress ADD COLUMN captures_taken "
                  "INTEGER NOT NULL DEFAULT 0")
    for row in c.execute("SELECT mac, cleared, boss_down, captured "
                         "FROM rift_progress").fetchall():
        layers = 100 if row["boss_down"] else min(100, row["cleared"] * 12)
        c.execute("UPDATE rift_progress SET cleared = ?, captures_taken = ? "
                  "WHERE mac = ?",
                  (layers, 1 if row["captured"] else 0, row["mac"]))


def _migrate_6_to_7(c: sqlite3.Connection):
    """v0.9.1 -> v0.9.2: devices.found_at — the Array level a rift was
    resolved at. Later discoveries are deeper and meaner, so this has to be
    remembered rather than recomputed."""
    cols = {r["name"] for r in c.execute("PRAGMA table_info(devices)")}
    if "found_at" not in cols:
        c.execute("ALTER TABLE devices ADD COLUMN found_at INTEGER NOT NULL DEFAULT 0")


MIGRATIONS = {
    1: _migrate_1_to_2,
    2: _migrate_2_to_3,
    3: _migrate_3_to_4,
    4: _migrate_4_to_5,
    5: _migrate_5_to_6,
    6: _migrate_6_to_7,
    # 7: _migrate_7_to_8,   <- next schema change goes here
}


def _conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def init_db():
    parent = os.path.dirname(os.path.abspath(DB_PATH))
    os.makedirs(parent, exist_ok=True)
    with _conn() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS daemons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                data TEXT NOT NULL,
                created REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS rift_progress (
                mac TEXT PRIMARY KEY,
                cleared INTEGER NOT NULL DEFAULT 0,
                boss_down INTEGER NOT NULL DEFAULT 0,
                updated REAL NOT NULL,
                tier INTEGER NOT NULL DEFAULT 0,
                ward INTEGER NOT NULL DEFAULT 0,
                signal REAL NOT NULL DEFAULT 0,
                captured INTEGER NOT NULL DEFAULT 0,
                captures_taken INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS devices (
                mac TEXT PRIMARY KEY,
                hostname TEXT DEFAULT '',
                ip TEXT DEFAULT '',
                vendor TEXT DEFAULT '',
                first_seen REAL NOT NULL,
                last_seen REAL NOT NULL,
                online INTEGER NOT NULL DEFAULT 1,
                found_at INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL NOT NULL,
                kind TEXT NOT NULL,
                text TEXT NOT NULL,
                mac TEXT DEFAULT '',
                daemon_id INTEGER
            );
            CREATE TABLE IF NOT EXISTS expeditions (
                daemon_id INTEGER PRIMARY KEY,
                mac TEXT NOT NULL,
                state TEXT NOT NULL DEFAULT 'active',
                started REAL NOT NULL,
                last_tick REAL NOT NULL,
                fights INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS resources (
                kind TEXT PRIMARY KEY,
                amount REAL NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS harvests (
                daemon_id INTEGER PRIMARY KEY,
                mac TEXT NOT NULL,
                node_index INTEGER NOT NULL,
                started REAL NOT NULL,
                last_tick REAL NOT NULL,
                lifetime_bits REAL NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS eggs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created REAL NOT NULL,
                hatch_at REAL NOT NULL,
                essence TEXT NOT NULL,
                state TEXT NOT NULL DEFAULT 'incubating'
            );
            CREATE TABLE IF NOT EXISTS facilities (
                key TEXT PRIMARY KEY,
                level INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS training (
                daemon_id INTEGER PRIMARY KEY,
                hall TEXT NOT NULL,
                started REAL NOT NULL,
                last_tick REAL NOT NULL,
                banked REAL NOT NULL DEFAULT 0,
                gained INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS incursions (
                mac TEXT PRIMARY KEY,
                spawned REAL NOT NULL,
                deadline REAL NOT NULL,
                strength REAL NOT NULL,
                garrison TEXT NOT NULL DEFAULT ''
            );
            """
        )
    _run_migrations()


def _run_migrations():
    """Bring an existing DB from whatever version it's at up to SCHEMA_VERSION."""
    with _conn() as c:
        row = c.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
        if row is None:
            # Either a brand-new DB (already current by construction) or a
            # pre-versioning v0.1/v0.2 DB. Distinguish by whether game data
            # exists: bootstrapped -> old DB at version 1; empty -> current.
            booted = c.execute("SELECT 1 FROM meta WHERE key='bootstrapped'").fetchone()
            current = 1 if booted else SCHEMA_VERSION
        else:
            current = int(row["value"])
        while current < SCHEMA_VERSION:
            MIGRATIONS[current](c)
            current += 1
        c.execute("INSERT INTO meta (key, value) VALUES ('schema_version', ?) "
                  "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                  (str(current),))


# --- daemons ----------------------------------------------------------------
def add_daemon(d: Daemon) -> int:
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO daemons (data, created) VALUES (?, ?)",
            (json.dumps(d.to_dict()), time.time()),
        )
        d.id = cur.lastrowid
        return d.id


def save_daemon(d: Daemon):
    if d.id is None:
        add_daemon(d)
        return
    with _conn() as c:
        c.execute("UPDATE daemons SET data = ? WHERE id = ?",
                  (json.dumps(d.to_dict()), d.id))


def get_daemon(did: int) -> Optional[Daemon]:
    with _conn() as c:
        row = c.execute("SELECT * FROM daemons WHERE id = ?", (did,)).fetchone()
    if not row:
        return None
    d = Daemon.from_dict(json.loads(row["data"]))
    d.id = row["id"]
    return d


def list_daemons() -> list[Daemon]:
    with _conn() as c:
        rows = c.execute("SELECT * FROM daemons ORDER BY id").fetchall()
    out = []
    for row in rows:
        d = Daemon.from_dict(json.loads(row["data"]))
        d.id = row["id"]
        out.append(d)
    return out


def release_daemon(did: int):
    with _conn() as c:
        c.execute("DELETE FROM daemons WHERE id = ?", (did,))
        c.execute("DELETE FROM expeditions WHERE daemon_id = ?", (did,))


# --- rift progress ----------------------------------------------------------
def get_progress(mac: str) -> dict:
    with _conn() as c:
        row = c.execute("SELECT * FROM rift_progress WHERE mac = ?", (mac,)).fetchone()
    if not row:
        return {"mac": mac, "cleared": 0, "boss_down": 0,
                "tier": 0, "ward": 0, "signal": 0.0, "captured": 0,
                "captures_taken": 0}
    return {"mac": row["mac"], "cleared": row["cleared"],
            "boss_down": row["boss_down"], "tier": row["tier"],
            "ward": row["ward"], "signal": row["signal"],
            "captured": row["captured"],
            "captures_taken": row["captures_taken"]}


def set_progress(mac: str, cleared: int, boss_down: bool):
    with _conn() as c:
        c.execute(
            """INSERT INTO rift_progress (mac, cleared, boss_down, updated)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(mac) DO UPDATE SET
                 cleared=excluded.cleared,
                 boss_down=excluded.boss_down,
                 updated=excluded.updated""",
            (mac, cleared, 1 if boss_down else 0, time.time()),
        )


def set_progress_fields(mac: str, **fields):
    """Update any subset of rift_progress columns (row must exist or is made)."""
    with _conn() as c:
        c.execute("INSERT OR IGNORE INTO rift_progress (mac, updated) VALUES (?, ?)",
                  (mac, time.time()))
        keys = ", ".join(f"{k} = ?" for k in fields)
        c.execute(f"UPDATE rift_progress SET {keys}, updated = ? WHERE mac = ?",
                  (*fields.values(), time.time(), mac))


# --- facilities (the Bastion) ------------------------------------------------
def facility_level(key: str) -> int:
    with _conn() as c:
        row = c.execute("SELECT level FROM facilities WHERE key = ?", (key,)).fetchone()
    return row["level"] if row else 0


def all_facility_levels() -> dict:
    with _conn() as c:
        rows = c.execute("SELECT key, level FROM facilities").fetchall()
    return {r["key"]: r["level"] for r in rows}


def set_facility_level(key: str, level: int):
    with _conn() as c:
        c.execute("INSERT INTO facilities (key, level) VALUES (?, ?) "
                  "ON CONFLICT(key) DO UPDATE SET level=excluded.level",
                  (key, level))


# --- training halls ----------------------------------------------------------
def start_training(daemon_id: int, hall: str):
    now = time.time()
    with _conn() as c:
        c.execute(
            """INSERT INTO training (daemon_id, hall, started, last_tick)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(daemon_id) DO UPDATE SET
                 hall=excluded.hall, started=excluded.started,
                 last_tick=excluded.last_tick, banked=0, gained=0""",
            (daemon_id, hall, now, now))


def get_training(daemon_id: int) -> Optional[dict]:
    with _conn() as c:
        row = c.execute("SELECT * FROM training WHERE daemon_id = ?",
                        (daemon_id,)).fetchone()
    return dict(row) if row else None


def list_training(hall: Optional[str] = None) -> list[dict]:
    q, args = "SELECT * FROM training", ()
    if hall:
        q += " WHERE hall = ?"; args = (hall,)
    with _conn() as c:
        rows = c.execute(q, args).fetchall()
    return [dict(r) for r in rows]


def update_training(daemon_id: int, **fields):
    keys = ", ".join(f"{k} = ?" for k in fields)
    with _conn() as c:
        c.execute(f"UPDATE training SET {keys} WHERE daemon_id = ?",
                  (*fields.values(), daemon_id))


def end_training(daemon_id: int):
    with _conn() as c:
        c.execute("DELETE FROM training WHERE daemon_id = ?", (daemon_id,))


# --- incursions (the Null) ---------------------------------------------------
def spawn_incursion(mac: str, deadline: float, strength: float):
    with _conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO incursions (mac, spawned, deadline, strength, garrison) "
            "VALUES (?, ?, ?, ?, '')",
            (mac, time.time(), deadline, strength))


def get_incursion(mac: str) -> Optional[dict]:
    with _conn() as c:
        row = c.execute("SELECT * FROM incursions WHERE mac = ?", (mac,)).fetchone()
    return dict(row) if row else None


def list_incursions() -> list[dict]:
    with _conn() as c:
        rows = c.execute("SELECT * FROM incursions").fetchall()
    return [dict(r) for r in rows]


def set_garrison(mac: str, daemon_ids: list[int]):
    with _conn() as c:
        c.execute("UPDATE incursions SET garrison = ? WHERE mac = ?",
                  (",".join(str(i) for i in daemon_ids), mac))


def end_incursion(mac: str):
    with _conn() as c:
        c.execute("DELETE FROM incursions WHERE mac = ?", (mac,))


# --- devices (presence) ------------------------------------------------------
def upsert_device(mac: str, hostname: str = "", ip: str = "", vendor: str = "",
                  online: bool = True):
    now = time.time()
    with _conn() as c:
        c.execute(
            """INSERT INTO devices (mac, hostname, ip, vendor, first_seen, last_seen, online)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(mac) DO UPDATE SET
                 hostname=CASE WHEN excluded.hostname!='' THEN excluded.hostname ELSE devices.hostname END,
                 ip=CASE WHEN excluded.ip!='' THEN excluded.ip ELSE devices.ip END,
                 vendor=CASE WHEN excluded.vendor!='' THEN excluded.vendor ELSE devices.vendor END,
                 last_seen=excluded.last_seen,
                 online=excluded.online""",
            (mac, hostname, ip, vendor, now, now, 1 if online else 0),
        )


def touch_device(mac: str):
    with _conn() as c:
        c.execute("UPDATE devices SET last_seen = ?, online = 1 WHERE mac = ?",
                  (time.time(), mac))


def set_device_online(mac: str, online: bool):
    with _conn() as c:
        c.execute("UPDATE devices SET online = ? WHERE mac = ?",
                  (1 if online else 0, mac))


def get_device(mac: str) -> Optional[dict]:
    with _conn() as c:
        row = c.execute("SELECT * FROM devices WHERE mac = ?", (mac,)).fetchone()
    return dict(row) if row else None


def list_devices() -> list[dict]:
    with _conn() as c:
        rows = c.execute("SELECT * FROM devices ORDER BY last_seen DESC").fetchall()
    return [dict(r) for r in rows]


def forget_device(mac: str):
    with _conn() as c:
        c.execute("DELETE FROM devices WHERE mac = ?", (mac,))


# --- events (the journal) ----------------------------------------------------
def add_event(kind: str, text: str, mac: str = "", daemon_id: Optional[int] = None):
    with _conn() as c:
        c.execute("INSERT INTO events (ts, kind, text, mac, daemon_id) VALUES (?, ?, ?, ?, ?)",
                  (time.time(), kind, text, mac, daemon_id))


def list_events(limit: int = 60) -> list[dict]:
    with _conn() as c:
        rows = c.execute("SELECT * FROM events ORDER BY id DESC LIMIT ?",
                         (limit,)).fetchall()
    return [dict(r) for r in rows]


# --- expeditions -------------------------------------------------------------
def start_expedition(daemon_id: int, mac: str):
    now = time.time()
    with _conn() as c:
        c.execute(
            """INSERT INTO expeditions (daemon_id, mac, state, started, last_tick, fights)
               VALUES (?, ?, 'active', ?, ?, 0)
               ON CONFLICT(daemon_id) DO UPDATE SET
                 mac=excluded.mac, state='active', started=excluded.started,
                 last_tick=excluded.last_tick, fights=0""",
            (daemon_id, mac, now, now),
        )


def get_expedition(daemon_id: int) -> Optional[dict]:
    with _conn() as c:
        row = c.execute("SELECT * FROM expeditions WHERE daemon_id = ?",
                        (daemon_id,)).fetchone()
    return dict(row) if row else None


def list_expeditions(active_only: bool = True) -> list[dict]:
    q = "SELECT * FROM expeditions"
    if active_only:
        q += " WHERE state = 'active'"
    with _conn() as c:
        rows = c.execute(q).fetchall()
    return [dict(r) for r in rows]


def update_expedition(daemon_id: int, **fields):
    keys = ", ".join(f"{k} = ?" for k in fields)
    with _conn() as c:
        c.execute(f"UPDATE expeditions SET {keys} WHERE daemon_id = ?",
                  (*fields.values(), daemon_id))


def end_expedition(daemon_id: int):
    with _conn() as c:
        c.execute("DELETE FROM expeditions WHERE daemon_id = ?", (daemon_id,))


# --- resources (the wallet) --------------------------------------------------
def res_all() -> dict:
    with _conn() as c:
        rows = c.execute("SELECT kind, amount FROM resources").fetchall()
    return {r["kind"]: r["amount"] for r in rows}


def res_add(kind: str, amount: float):
    if amount == 0:
        return
    with _conn() as c:
        c.execute(
            "INSERT INTO resources (kind, amount) VALUES (?, ?) "
            "ON CONFLICT(kind) DO UPDATE SET amount = amount + excluded.amount",
            (kind, amount),
        )


def res_spend(costs: dict) -> bool:
    """Atomically spend a {kind: amount} basket. False if anything's short."""
    with _conn() as c:
        wallet = {r["kind"]: r["amount"] for r in
                  c.execute("SELECT kind, amount FROM resources").fetchall()}
        for kind, amt in costs.items():
            if wallet.get(kind, 0) < amt - 1e-9:
                return False
        for kind, amt in costs.items():
            c.execute("UPDATE resources SET amount = amount - ? WHERE kind = ?",
                      (amt, kind))
    return True


# --- harvest assignments -----------------------------------------------------
def start_harvest(daemon_id: int, mac: str, node_index: int):
    now = time.time()
    with _conn() as c:
        c.execute(
            """INSERT INTO harvests (daemon_id, mac, node_index, started, last_tick)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(daemon_id) DO UPDATE SET
                 mac=excluded.mac, node_index=excluded.node_index,
                 started=excluded.started, last_tick=excluded.last_tick,
                 lifetime_bits=0""",
            (daemon_id, mac, node_index, now, now),
        )


def get_harvest(daemon_id: int) -> Optional[dict]:
    with _conn() as c:
        row = c.execute("SELECT * FROM harvests WHERE daemon_id = ?",
                        (daemon_id,)).fetchone()
    return dict(row) if row else None


def list_harvests(mac: Optional[str] = None) -> list[dict]:
    q, args = "SELECT * FROM harvests", ()
    if mac:
        q += " WHERE mac = ?"; args = (mac,)
    with _conn() as c:
        rows = c.execute(q, args).fetchall()
    return [dict(r) for r in rows]


def update_harvest(daemon_id: int, **fields):
    keys = ", ".join(f"{k} = ?" for k in fields)
    with _conn() as c:
        c.execute(f"UPDATE harvests SET {keys} WHERE daemon_id = ?",
                  (*fields.values(), daemon_id))


def end_harvest(daemon_id: int):
    with _conn() as c:
        c.execute("DELETE FROM harvests WHERE daemon_id = ?", (daemon_id,))


# --- eggs --------------------------------------------------------------------
def add_egg(essence: str, hatch_at: float) -> int:
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO eggs (created, hatch_at, essence) VALUES (?, ?, ?)",
            (time.time(), hatch_at, essence))
        return cur.lastrowid


def list_eggs(incubating_only: bool = True) -> list[dict]:
    q = "SELECT * FROM eggs"
    if incubating_only:
        q += " WHERE state = 'incubating'"
    with _conn() as c:
        rows = c.execute(q + " ORDER BY hatch_at").fetchall()
    return [dict(r) for r in rows]


def hatch_egg_row(egg_id: int):
    with _conn() as c:
        c.execute("UPDATE eggs SET state = 'hatched' WHERE id = ?", (egg_id,))


def total_layers_cleared() -> int:
    """LIFETIME layers dug across every rift.

    Counted cumulatively rather than summed from current depth, because
    Overclocking resets a rift to layer 0 — summing live depth would mean
    pushing a tier erased your progress toward the Array, and the requirement
    would be unreachable once it exceeded (rifts x 100).
    """
    return int(float(get_meta("layers_dug", "0") or 0))


def bump_layers_dug(n: int = 1):
    set_meta("layers_dug", str(total_layers_cleared() + n))


def set_found_at(mac: str, level: int):
    with _conn() as c:
        c.execute("UPDATE devices SET found_at = ? WHERE mac = ?", (level, mac))


# --- reset ------------------------------------------------------------------
# Everything the game accumulates, in the order it's safe to clear.
RESETTABLE = ["daemons", "rift_progress", "events", "expeditions", "resources",
              "harvests", "eggs", "facilities", "training", "incursions"]


def reset_all(keep_devices: bool = True) -> dict:
    """Wipe progression back to a clean save.

    The schema itself is left alone — this clears rows, it does not drop
    tables, so the DB stays at its current version and no migration reruns.
    Discovered devices are kept by default: they're just the result of a LAN
    scan, and rescanning them is busywork rather than progress.

    The ticker's clock keys MUST go too. They store the last time drift was
    applied, and leaving them behind would make the first tick after a reset
    apply every hour that passed since the old save's last beat.
    """
    counts = {}
    with _conn() as c:
        for table in RESETTABLE:
            counts[table] = c.execute(f"SELECT COUNT(*) n FROM {table}").fetchone()["n"]
            c.execute(f"DELETE FROM {table}")
        if not keep_devices:
            counts["devices"] = c.execute("SELECT COUNT(*) n FROM devices").fetchone()["n"]
            c.execute("DELETE FROM devices")
        else:
            # a fresh save shouldn't inherit stale presence state
            c.execute("UPDATE devices SET online = 1")
        # keep schema_version; drop everything else, clocks included
        c.execute("DELETE FROM meta WHERE key != 'schema_version'")
    return counts


# --- meta -------------------------------------------------------------------
def get_meta(key: str, default=None):
    with _conn() as c:
        row = c.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_meta(key: str, value: str):
    with _conn() as c:
        c.execute(
            "INSERT INTO meta (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
