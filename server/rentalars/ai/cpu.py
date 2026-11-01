# SPDX-License-Identifier: GPL-3.0-or-later
"""What the processor of this server can do for the local AI (EML-040).

A language model on the processor is fast only with the vector instructions
AVX2 and FMA (x86-64). A virtual machine often hides them: Proxmox, for
example, gives new machines a generic processor type ("x86-64-v2-AES",
earlier "kvm64") that has neither – the model then runs several times
slower. The remedy is the processor type "host" in the settings of the
virtual machine.

The model works best with one thread per *physical* core: a second thread on
the same core (hyper-threading) does not make it faster. ``rentalars ai
install`` sets the threads that way (``deploy/ai.sh``); this module tells the
settings page the same from ``/proc/cpuinfo``.
"""

from __future__ import annotations

import platform
from dataclasses import dataclass, field
from pathlib import Path

from django.conf import settings

CPUINFO = Path("/proc/cpuinfo")


@dataclass(frozen=True)
class CpuReport:
    """The processor as ``/proc/cpuinfo`` describes it."""

    model: str = ""
    logical: int = 0
    physical: int = 0
    flags: frozenset[str] = field(default_factory=frozenset)
    #: x86-64, where AVX2 and FMA matter; on ARM (Raspberry Pi) NEON is always there.
    is_x86: bool = True
    #: The kernel says it runs in a virtual machine (flag "hypervisor").
    in_vm: bool = False

    @property
    def missing(self) -> list[str]:
        """The vector instructions the model needs that the processor does not report (x86 only)."""
        if not self.is_x86 or not self.flags:
            return []
        return [name.upper() for name in ("avx2", "fma") if name not in self.flags]

    @property
    def threads(self) -> int:
        """The threads the local AI should use: one per physical core."""
        return max(1, self.physical or self.logical or 1)


def read_cpuinfo(path: Path | None = None) -> CpuReport:
    """Read ``/proc/cpuinfo`` (or the file the settings name for tests); an empty report if it cannot be read."""
    path = path or Path(getattr(settings, "RENTALARS_AI_CPUINFO", "") or CPUINFO)
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return CpuReport()
    return parse_cpuinfo(text, machine=platform.machine())


def parse_cpuinfo(text: str, *, machine: str = "") -> CpuReport:
    """Count logical and physical cores and read the flags of the first processor."""
    logical = 0
    cores: set[tuple[str, str]] = set()
    model = ""
    flags: frozenset[str] = frozenset()
    is_x86: bool | None = None
    current: dict[str, str] = {}

    def finish(block: dict[str, str]) -> None:
        if "core id" in block:
            cores.add((block.get("physical id", "0"), block["core id"]))

    for line in [*text.splitlines(), ""]:
        if not line.strip():
            if current:
                finish(current)
            current = {}
            continue
        key, _sep, value = line.partition(":")
        key, value = key.strip().lower(), value.strip()
        current[key] = value
        if key == "processor":
            logical += 1
        elif key == "model name" and not model:
            model = value
        elif key == "model" and not model and not value.isdigit():
            model = value  # Raspberry Pi: "Raspberry Pi 5 Model B Rev 1.0"
        elif key == "flags" and not flags:
            flags = frozenset(value.split())
            is_x86 = True
        elif key == "features" and not flags:
            flags = frozenset(value.split())
            is_x86 = False
    if is_x86 is None:
        is_x86 = machine.lower() in {"x86_64", "amd64", "i686", "i386"} or not machine
    return CpuReport(
        model=model,
        logical=logical,
        physical=len(cores) or logical,
        flags=flags,
        is_x86=is_x86,
        in_vm="hypervisor" in flags,
    )
