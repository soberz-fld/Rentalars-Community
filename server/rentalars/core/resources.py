# SPDX-License-Identifier: GPL-3.0-or-later
"""What the server has and what it uses: processors, memory, network, running time (ADM-008).

Read for the self-check (page, API and ``rentalars selfcheck``) straight from
``/proc`` of Linux – no extra library, no command to start, a few
milliseconds. Everything is optional: on another system, or where a file
cannot be read, the value is simply missing and the self-check leaves the
line out.

=====================  ==================================================
Processors             number of usable cores; load over 1, 5, 15 minutes
                       (``/proc/loadavg``)
Memory                 total and available (``/proc/meminfo``)
Memory of Rentalars    this process – under gunicorn the master with all
                       its workers, counted proportionally (``Pss`` of
                       ``smaps_rollup``) so that shared pages count once
Network                host name; per interface its addresses and the bytes
                       received and sent since the start (``/proc/net/dev``,
                       ``/proc/net/if_inet6``)
Running time           since the start of the server (``/proc/uptime``)
=====================  ==================================================

The free space of the data folder is a check of its own (``selfcheck._space``).
"""

from __future__ import annotations

import ipaddress
import os
import socket
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

#: Where Linux shows its processes and counters; tests point it elsewhere.
PROC = Path("/proc")

#: At most this many network interfaces are listed (a host with containers has dozens).
MAX_INTERFACES = 8

#: ``/proc/net/if_inet6``: scope of addresses that only mean something on one link or on the host itself.
_LINK_SCOPE = 0x20
_HOST_SCOPE = 0x10


@dataclass
class NetworkInterface:
    """One network interface with its addresses and traffic since the start."""

    name: str
    addresses: list[str] = field(default_factory=list)
    received_bytes: int | None = None
    sent_bytes: int | None = None


@dataclass
class Resources:
    """The resources of the server; ``None`` where they could not be read."""

    cores: int | None = None
    #: Load average over 1, 5 and 15 minutes.
    load: tuple[float, float, float] | None = None
    memory_total: int | None = None
    memory_available: int | None = None
    #: Bytes used by Rentalars itself, and in how many processes.
    own_memory: int | None = None
    own_processes: int = 0
    hostname: str = ""
    interfaces: list[NetworkInterface] = field(default_factory=list)
    uptime_seconds: float | None = None

    def as_dict(self) -> dict[str, Any]:
        """The values for the API: bytes and seconds as numbers."""
        data = asdict(self)
        data["load"] = list(self.load) if self.load is not None else None
        return data


def read_resources(proc: Path = PROC, ipv4: Callable[[str], list[str]] | None = None) -> Resources:
    """Read what the server has and uses; never raises.

    Args:
        proc: The ``/proc`` folder to read.
        ipv4: Finds the IPv4 addresses of an interface by its name; by
            default the operating system is asked (:func:`ipv4_addresses`).
    """
    resources = Resources(cores=_cores(), hostname=_hostname())
    resources.load = _load(proc)
    resources.memory_total, resources.memory_available = _memory(proc)
    resources.own_memory, resources.own_processes = _own_memory(proc)
    resources.interfaces = _interfaces(proc, ipv4 or ipv4_addresses)
    resources.uptime_seconds = _uptime(proc)
    return resources


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _cores() -> int | None:
    """The cores this process may use; a container or ``taskset`` can grant fewer than the machine has."""
    try:
        return len(os.sched_getaffinity(0)) or None
    except (AttributeError, OSError):
        return os.cpu_count()


def _hostname() -> str:
    try:
        return socket.gethostname()
    except OSError:
        return ""


def _load(proc: Path) -> tuple[float, float, float] | None:
    text = _read(proc / "loadavg")
    try:
        one, five, fifteen = (float(value) for value in (text or "").split()[:3])
    except ValueError:
        return None
    return one, five, fifteen


def _key_values(text: str | None) -> dict[str, str]:
    """``Name:   value`` lines (``meminfo``, ``status``, ``smaps_rollup``) as a mapping."""
    values: dict[str, str] = {}
    for line in (text or "").splitlines():
        name, separator, value = line.partition(":")
        if separator:
            values[name.strip()] = value.strip()
    return values


def _kilobytes(value: str | None) -> int | None:
    """``"16314240 kB"`` → bytes."""
    try:
        return int((value or "").split()[0]) * 1024
    except (IndexError, ValueError):
        return None


def _memory(proc: Path) -> tuple[int | None, int | None]:
    values = _key_values(_read(proc / "meminfo"))
    return _kilobytes(values.get("MemTotal")), _kilobytes(values.get("MemAvailable"))


def _memory_of(process: Path) -> int | None:
    """Memory of one process: its proportional share if the kernel says it, else its resident size."""
    rollup = _kilobytes(_key_values(_read(process / "smaps_rollup")).get("Pss"))
    if rollup is not None:
        return rollup
    return _kilobytes(_key_values(_read(process / "status")).get("VmRSS"))


def _own_memory(proc: Path) -> tuple[int | None, int]:
    """Memory of Rentalars: the gunicorn master and all its workers, or else this process alone."""
    own = proc / "self"
    parent = _key_values(_read(own / "status")).get("PPid", "")
    family = [own]
    if parent.isdigit() and parent != "0":
        command = _read(proc / parent / "cmdline") or ""
        if "gunicorn" in command:
            family = [proc / parent]
            for entry in _process_folders(proc):
                if _key_values(_read(entry / "status")).get("PPid") == parent:
                    family.append(entry)
    sizes = [size for size in (_memory_of(process) for process in family) if size is not None]
    if not sizes:
        return None, 0
    return sum(sizes), len(sizes)


def _process_folders(proc: Path) -> list[Path]:
    try:
        return [entry for entry in proc.iterdir() if entry.name.isdigit()]
    except OSError:
        return []


def _traffic(proc: Path) -> dict[str, tuple[int, int]]:
    """Bytes received and sent per interface since the start (``/proc/net/dev``)."""
    counters: dict[str, tuple[int, int]] = {}
    for line in (_read(proc / "net" / "dev") or "").splitlines()[2:]:
        name, separator, rest = line.partition(":")
        fields = rest.split()
        if separator and len(fields) >= 9:
            try:
                counters[name.strip()] = (int(fields[0]), int(fields[8]))
            except ValueError:
                continue
    return counters


def _ipv6_addresses(proc: Path) -> dict[str, list[str]]:
    """The IPv6 addresses per interface, without those valid on one link or the host only."""
    addresses: dict[str, list[str]] = {}
    for line in (_read(proc / "net" / "if_inet6") or "").splitlines():
        fields = line.split()
        if len(fields) < 6:
            continue
        try:
            scope = int(fields[3], 16)
            address = ipaddress.IPv6Address(bytes.fromhex(fields[0]))
        except ValueError:
            continue
        if scope in {_LINK_SCOPE, _HOST_SCOPE}:
            continue
        addresses.setdefault(fields[5], []).append(str(address))
    return addresses


def ipv4_addresses(name: str) -> list[str]:
    """The IPv4 address of an interface, asked from the kernel (Linux); empty if it has none."""
    try:
        import fcntl
        import struct

        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            # SIOCGIFADDR: the (first) address of the interface; works without any rights.
            packed = fcntl.ioctl(probe.fileno(), 0x8915, struct.pack("256s", name[:15].encode()))
    except (ImportError, OSError, ValueError):
        return []
    return [socket.inet_ntoa(packed[20:24])]


def _interfaces(proc: Path, ipv4: Callable[[str], list[str]]) -> list[NetworkInterface]:
    traffic = _traffic(proc)
    ipv6 = _ipv6_addresses(proc)
    interfaces = []
    for name in sorted(set(traffic) | set(ipv6)):
        if name == "lo":
            continue
        addresses = [*ipv4(name), *ipv6.get(name, [])]
        if not addresses:
            # Bridges and links of containers without an address of their own say nothing about the server.
            continue
        received, sent = traffic.get(name, (None, None))
        interfaces.append(NetworkInterface(name, addresses, received, sent))
    return interfaces[:MAX_INTERFACES]


def _uptime(proc: Path) -> float | None:
    try:
        return float((_read(proc / "uptime") or "").split()[0])
    except (IndexError, ValueError):
        return None
