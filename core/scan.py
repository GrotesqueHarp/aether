"""
scan.py — Real LAN discovery, no root required on most systems.

Strategy: figure out the local /24, fire a quick concurrent ping sweep to
populate the OS ARP cache, then read the ARP table to harvest MAC addresses.
This avoids raw sockets (which need privileges) and works on Linux/macOS/Windows
by shelling out to the platform's tools. A vendor lookup maps the OUI to a
manufacturer name when an offline prefix table is available.

If scanning finds nothing (locked-down container, permissions), the caller can
fall back to manual device entry — the game only needs a MAC + a name.
"""

from __future__ import annotations

import concurrent.futures
import ipaddress
import platform
import re
import socket
import subprocess
from typing import Optional

_MAC_LINE = re.compile(
    r"(?P<ip>\d+\.\d+\.\d+\.\d+).*?(?P<mac>(?:[0-9a-fA-F]{2}[:-]){5}[0-9a-fA-F]{2})"
)


def local_ipv4() -> Optional[str]:
    """Best-effort primary LAN IP (no traffic actually sent)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return None
    finally:
        s.close()


def local_subnet() -> Optional[ipaddress.IPv4Network]:
    ip = local_ipv4()
    if not ip:
        return None
    return ipaddress.ip_network(ip + "/24", strict=False)


def _ping(host: str) -> None:
    system = platform.system().lower()
    if system == "windows":
        cmd = ["ping", "-n", "1", "-w", "400", host]
    else:
        cmd = ["ping", "-c", "1", "-W", "1", host]
    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, timeout=2)
    except (subprocess.TimeoutExpired, OSError):
        pass


def ping_sweep(net: ipaddress.IPv4Network, workers: int = 64) -> None:
    hosts = [str(h) for h in net.hosts()]
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(_ping, hosts))


def read_arp_table() -> list[dict]:
    system = platform.system().lower()
    cmd = ["arp", "-a"] if system != "linux" else ["ip", "neigh"]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=6).stdout
    except (OSError, subprocess.TimeoutExpired):
        # fall back to arp -a on linux if `ip` missing
        try:
            out = subprocess.run(["arp", "-a"], capture_output=True,
                                 text=True, timeout=6).stdout
        except (OSError, subprocess.TimeoutExpired):
            return []
    devices = []
    seen = set()
    for line in out.splitlines():
        m = _MAC_LINE.search(line)
        if not m:
            continue
        mac = m.group("mac").upper().replace("-", ":")
        if mac in seen or mac == "FF:FF:FF:FF:FF:FF" or mac.startswith("00:00:00"):
            continue
        seen.add(mac)
        ip = m.group("ip")
        host = ""
        try:
            host = socket.gethostbyaddr(ip)[0]
        except OSError:
            pass
        devices.append({"ip": ip, "mac": mac, "hostname": host})
    return devices


def discover(do_sweep: bool = True) -> dict:
    """Full discovery pass. Returns devices + metadata about the scan."""
    net = local_subnet()
    meta = {"subnet": str(net) if net else None,
            "local_ip": local_ipv4(),
            "swept": False}
    if net and do_sweep:
        try:
            ping_sweep(net)
            meta["swept"] = True
        except Exception:  # noqa: BLE001 - never let a scan crash the server
            pass
    devices = read_arp_table()
    for d in devices:
        d["vendor"] = vendor_for(d["mac"])
    return {"devices": devices, "meta": meta}


# --- tiny built-in OUI table (extend or swap for a full ieee file) ----------
_VENDORS = {
    "DC:A6:32": "Raspberry Pi", "B8:27:EB": "Raspberry Pi", "E4:5F:01": "Raspberry Pi",
    "F0:18:98": "Apple", "AC:DE:48": "Apple", "3C:5A:B4": "Google",
    "00:1A:11": "Google", "00:50:56": "VMware", "52:54:00": "QEMU/KVM",
    "00:15:5D": "Microsoft Hyper-V",
}


def vendor_for(mac: str) -> str:
    return _VENDORS.get(":".join(mac.upper().split(":")[:3]), "")


# --- deterministic mock network for demos / dev without a real LAN ----------
def mock_devices() -> list[dict]:
    sample = [
        ("DC:A6:32:1F:44:9A", "raspberrypi.local", "192.168.1.20"),
        ("F0:18:98:5C:22:01", "living-room-tv", "192.168.1.31"),
        ("52:54:00:AB:CD:12", "vm-media-server", "192.168.1.40"),
        ("3C:5A:B4:77:19:EE", "nest-hub", "192.168.1.55"),
        ("A4:83:E7:9B:02:C1", "someones-laptop", "192.168.1.66"),
        ("00:15:5D:0A:1B:2C", "hyperv-host", "192.168.1.10"),
    ]
    return [{"mac": m, "hostname": h, "ip": ip, "vendor": vendor_for(m)}
            for m, h, ip in sample]
