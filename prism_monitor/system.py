"""CPU / GPU temperature and usage, and memory use.

Linux: /proc/stat, /proc/meminfo, hwmon (coretemp, k10temp, zenpower, amdgpu,
nouveau) and thermal zones; NVIDIA via nvidia-smi.
Windows: GetSystemTimes / GlobalMemoryStatusEx for usage; temperatures from
LibreHardwareMonitor (via the PowerShell helper or its web server) or nvidia-smi.
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from .util import WINDOWS, run

HWMON = Path('/sys/class/hwmon')
THERMAL = Path('/sys/class/thermal')


@dataclass
class Chip:
    """One processor row: CPU or GPU."""
    name: str
    temp: float | None = None
    load: float | None = None

    def has_data(self) -> bool:
        return self.temp is not None or self.load is not None


@dataclass
class Memory:
    used_gb: float
    total_gb: float
    swap_used_gb: float | None = None   # Linux only; None when there is no swap
    swap_total_gb: float | None = None

    @property
    def percent(self) -> float:
        return 100.0 * self.used_gb / self.total_gb if self.total_gb else 0.0


# usage ---------------------------------------------------------------------
class CpuLoad:
    """CPU busy % between two calls."""

    def __init__(self):
        self.previous: tuple[int, int] | None = None

    @staticmethod
    def _times() -> tuple[int, int] | None:  # (idle, total)
        if WINDOWS:
            import ctypes
            from ctypes import wintypes
            idle, kernel, user = wintypes.FILETIME(), wintypes.FILETIME(), wintypes.FILETIME()
            if not ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)):
                return None
            as_int = lambda ft: (ft.dwHighDateTime << 32) | ft.dwLowDateTime  # noqa: E731
            return as_int(idle), as_int(kernel) + as_int(user)  # kernel time includes idle
        try:
            fields = Path('/proc/stat').read_text().splitlines()[0].split()[1:]
        except (OSError, IndexError):
            return None
        values = [int(v) for v in fields[:8]]
        idle = values[3] + (values[4] if len(values) > 4 else 0)
        return idle, sum(values)

    def read(self) -> float | None:
        now = self._times()
        if now is None:
            return None
        before, self.previous = self.previous, now
        if before is None:
            return None
        idle, total = now[0] - before[0], now[1] - before[1]
        if total <= 0:
            return None
        return max(0.0, min(100.0, 100.0 * (total - idle) / total))


def parse_meminfo(text: str) -> Memory | None:
    values = {}
    for line in text.splitlines():
        key, _, rest = line.partition(':')
        parts = rest.split()
        if parts and parts[0].isdigit():
            values[key] = int(parts[0])
    total = values.get('MemTotal')
    available = values.get('MemAvailable', values.get('MemFree'))
    if not total or available is None:
        return None
    gib = 1024 * 1024
    memory = Memory(used_gb=(total - available) / gib, total_gb=total / gib)
    swap_total, swap_free = values.get('SwapTotal', 0), values.get('SwapFree', 0)
    if swap_total:
        memory.swap_used_gb = (swap_total - swap_free) / gib
        memory.swap_total_gb = swap_total / gib
    return memory


def memory() -> Memory | None:
    if WINDOWS:
        import ctypes

        class Status(ctypes.Structure):
            _fields_ = [('dwLength', ctypes.c_ulong), ('dwMemoryLoad', ctypes.c_ulong),
                        ('ullTotalPhys', ctypes.c_ulonglong), ('ullAvailPhys', ctypes.c_ulonglong),
                        ('ullTotalPageFile', ctypes.c_ulonglong), ('ullAvailPageFile', ctypes.c_ulonglong),
                        ('ullTotalVirtual', ctypes.c_ulonglong), ('ullAvailVirtual', ctypes.c_ulonglong),
                        ('ullAvailExtendedVirtual', ctypes.c_ulonglong)]
        status = Status()
        status.dwLength = ctypes.sizeof(Status)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return None
        gib = 1024 ** 3
        return Memory((status.ullTotalPhys - status.ullAvailPhys) / gib, status.ullTotalPhys / gib)
    try:
        return parse_meminfo(Path('/proc/meminfo').read_text())
    except OSError:
        return None


# Linux temperatures ----------------------------------------------------------
def _read(path: Path) -> str | None:
    try:
        return path.read_text().strip()
    except OSError:
        return None


def _temps(chip: Path) -> dict[str, float]:
    """label -> °C for one hwmon chip (unlabelled inputs are keyed temp1, temp2…)."""
    out = {}
    for item in chip.glob('temp*_input'):
        value = _read(item)
        if value is None or not value.lstrip('-').isdigit():
            continue
        stem = item.name[:-len('_input')]
        label = _read(chip / f'{stem}_label') or stem
        out[label] = int(value) / 1000.0
    return out


CPU_CHIPS = {  # driver -> preferred labels, best first
    'coretemp': ('Package id 0',),
    'k10temp': ('Tctl', 'Tdie'),
    'zenpower': ('Tdie', 'Tctl'),
    'cpu_thermal': (),
    'thinkpad': ('CPU',),
}
GPU_CHIPS = {'amdgpu': ('edge', 'junction'), 'nouveau': (), 'radeon': (), 'xe': ('pkg',), 'i915': ()}


def _pick(temps: dict[str, float], preferred: tuple[str, ...]) -> float | None:
    for label in preferred:
        if label in temps:
            return temps[label]
    return max(temps.values()) if temps else None


def linux_cpu_temp(hwmon: Path = HWMON, thermal: Path = THERMAL) -> float | None:
    chips = {(_read(c / 'name') or ''): c for c in hwmon.glob('hwmon*')}
    for driver, labels in CPU_CHIPS.items():
        if driver in chips:
            value = _pick(_temps(chips[driver]), labels)
            if value is not None:
                return value
    for zone in thermal.glob('thermal_zone*'):
        if _read(zone / 'type') in ('x86_pkg_temp', 'TCPU', 'cpu-thermal'):
            value = _read(zone / 'temp')
            if value and value.lstrip('-').isdigit():
                return int(value) / 1000.0
    return None


def linux_gpu(hwmon: Path = HWMON) -> Chip | None:
    for chip in sorted(hwmon.glob('hwmon*')):
        driver = _read(chip / 'name') or ''
        if driver not in GPU_CHIPS:
            continue
        temp = _pick(_temps(chip), GPU_CHIPS[driver])
        busy = _read(chip / 'device' / 'gpu_busy_percent')
        load = float(busy) if busy and busy.isdigit() else None
        result = Chip('GPU', temp, load)
        if result.has_data():
            return result
    return None


# NVIDIA (both platforms) -------------------------------------------------------
@dataclass
class NvidiaGpu:
    name: str
    fan_percent: float | None
    temp: float | None
    load: float | None


def _number(text: str) -> float | None:
    text = text.strip().rstrip('%').strip()
    try:
        return float(text)
    except ValueError:  # "[N/A]", "[Not Supported]"
        return None


def parse_nvidia_smi(text: str) -> list[NvidiaGpu]:
    gpus = []
    for line in text.splitlines():
        parts = [p.strip() for p in line.split(',')]
        if len(parts) < 4 or not parts[0]:
            continue
        gpus.append(NvidiaGpu(parts[0], _number(parts[1]), _number(parts[2]), _number(parts[3])))
    return gpus


class NvidiaSmi:
    """Polls nvidia-smi; gives up quietly after repeated failures (no driver / no card)."""

    def __init__(self):
        self.exe = shutil.which('nvidia-smi')
        self.failures = 0

    def read(self) -> list[NvidiaGpu]:
        if not self.exe or self.failures >= 3:
            return []
        out = run([self.exe, '--query-gpu=name,fan.speed,temperature.gpu,utilization.gpu',
                   '--format=csv,noheader,nounits'], timeout=4)
        if out is None:
            self.failures += 1
            return []
        self.failures = 0
        return parse_nvidia_smi(out)


# LibreHardwareMonitor web server tree (Windows fallback) ----------------------------
CPU_TEMP_NAMES = ('CPU Package', 'Core (Tctl/Tdie)', 'Core (Tctl)', 'Core (Tdie)', 'Core Max', 'Core Average')
GPU_TEMP_NAMES = ('GPU Core', 'GPU Hot Spot')


def pick_named(values: dict[str, float], names: tuple[str, ...]) -> float | None:
    for name in names:
        if name in values:
            return values[name]
    return max(values.values()) if values else None


def parse_lhm_chips(data: dict) -> tuple[Chip | None, Chip | None]:
    """CPU and GPU temperature/load from LibreHardwareMonitor's data.json."""
    cpu = gpu = None

    def number(value: str) -> float | None:
        cleaned = ''.join(ch for ch in value.replace(',', '.') if ch.isdigit() or ch in '.-')
        try:
            return float(cleaned)
        except ValueError:
            return None

    def collect(node: dict, group: str, temps: dict, loads: dict):
        for child in node.get('Children') or []:
            text = str(child.get('Text', ''))
            if child.get('Children'):
                collect(child, text, temps, loads)
                continue
            value = number(str(child.get('Value', '')))
            if value is None:
                continue
            if group == 'Temperatures':
                temps[text] = value
            elif group == 'Load':
                loads[text] = value

    for computer in data.get('Children') or []:
        for hardware in computer.get('Children') or []:
            image = str(hardware.get('ImageURL', '')).lower()
            temps, loads = {}, {}
            collect(hardware, '', temps, loads)
            if 'cpu' in image and cpu is None:
                cpu = Chip('CPU', pick_named(temps, CPU_TEMP_NAMES), loads.get('CPU Total'))
            elif any(k in image for k in ('nvidia', 'ati', 'amd', 'intel', 'gpu')) and gpu is None:
                chip = Chip(str(hardware.get('Text', 'GPU')), pick_named(temps, GPU_TEMP_NAMES), loads.get('GPU Core'))
                if chip.has_data():
                    gpu = chip
    return cpu, gpu
