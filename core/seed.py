"""
seed.py — The deterministic heart of AETHER.

A MAC address is a stable, semi-random 48-bit identifier that every network
device already has. We treat it as the seed for an entire generated world (a
"Rift"). Same MAC -> same world, forever. The OUI (first 3 bytes = the
manufacturer block) is pulled out separately so a device's *maker* can flavor
the biome, while the full address drives everything else.

Nothing in here uses Python's global random state, so worlds never interfere
with each other and generation is reproducible across runs and machines.
"""

from __future__ import annotations

import hashlib
import re


_MAC_RE = re.compile(r"[0-9a-fA-F]{2}")


def normalize_mac(mac: str) -> str:
    """Turn any reasonable MAC spelling into AA:BB:CC:DD:EE:FF (uppercase)."""
    parts = _MAC_RE.findall(mac or "")
    if len(parts) < 6:
        raise ValueError(f"Not a MAC address: {mac!r}")
    return ":".join(p.upper() for p in parts[:6])


def oui(mac: str) -> str:
    """Manufacturer block: the first three octets, e.g. 'DC:A6:32'."""
    return ":".join(normalize_mac(mac).split(":")[:3])


def _digest(*parts: str) -> bytes:
    """Stable 32-byte digest of the given namespaced parts."""
    h = hashlib.sha256()
    h.update("\x1f".join(parts).encode("utf-8"))
    return h.digest()


class Rng:
    """
    A tiny, dependency-free, fully deterministic PRNG (SplitMix64).

    We deliberately avoid Python's `random` so that world generation can later
    be reproduced byte-for-byte in another language (a JS client, say) if we
    ever move generation to the browser. Seeded from a SHA-256 digest.
    """

    __slots__ = ("_s",)

    def __init__(self, seed_bytes: bytes):
        self._s = int.from_bytes(seed_bytes[:8], "big") & 0xFFFFFFFFFFFFFFFF

    def _next(self) -> int:
        self._s = (self._s + 0x9E3779B97F4A7C15) & 0xFFFFFFFFFFFFFFFF
        z = self._s
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & 0xFFFFFFFFFFFFFFFF
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & 0xFFFFFFFFFFFFFFFF
        return z ^ (z >> 31)

    def random(self) -> float:
        """Float in [0, 1)."""
        return (self._next() >> 11) / (1 << 53)

    def randint(self, lo: int, hi: int) -> int:
        """Inclusive integer in [lo, hi]."""
        if hi < lo:
            lo, hi = hi, lo
        return lo + self._next() % (hi - lo + 1)

    def chance(self, p: float) -> bool:
        return self.random() < p

    def choice(self, seq):
        return seq[self._next() % len(seq)]

    def weighted(self, choices):
        """choices: list of (item, weight). Returns one item."""
        total = sum(w for _, w in choices)
        roll = self.random() * total
        acc = 0.0
        for item, w in choices:
            acc += w
            if roll < acc:
                return item
        return choices[-1][0]

    def shuffle(self, seq):
        seq = list(seq)
        for i in range(len(seq) - 1, 0, -1):
            j = self._next() % (i + 1)
            seq[i], seq[j] = seq[j], seq[i]
        return seq

    def sub(self, *label: str) -> "Rng":
        """
        Derive an independent child stream keyed by a label. This is how we
        keep concerns separated: rng.sub('habitat', '2') is stable and
        unrelated to rng.sub('boss'). Order-independent, which matters.
        """
        mixed = self._next().to_bytes(8, "big")
        return Rng(_digest(mixed.hex(), *label))


def rift_rng(mac: str, *label: str) -> Rng:
    """Top-level RNG for a device's world, optionally namespaced by label."""
    return Rng(_digest("aether.rift", normalize_mac(mac), *label))
