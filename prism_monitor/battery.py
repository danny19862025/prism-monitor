"""Bluetooth / wireless device battery sources.

Linux: BlueZ `org.bluez.Battery1` (read through `busctl --json`), kernel HID
power supplies in `/sys/class/power_supply` (Logitech, DualSense, Xbox via
xpadneo…), and UPower as a fallback.
Windows: the Bluetooth battery device property, read by the PowerShell helper
(see windows_helper.py) — the same value the Settings app shows.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from .model import Battery
from .util import run

POWER_SUPPLY = Path('/sys/class/power_supply')


def parse_bluez(text: str) -> list[Battery]:
    """Parse `busctl --json=short call org.bluez / …ObjectManager GetManagedObjects`."""
    try:
        data = json.loads(text)['data'][0]
    except (ValueError, KeyError, IndexError, TypeError):
        return []
    out = []
    for path, interfaces in data.items():
        battery = interfaces.get('org.bluez.Battery1')
        device = interfaces.get('org.bluez.Device1')
        if not battery or not device:
            continue
        if not device.get('Connected', {}).get('data', False):
            continue
        name = (device.get('Alias') or device.get('Name') or {}).get('data') or path.rsplit('/', 1)[-1]
        percent = battery.get('Percentage', {}).get('data')
        out.append(Battery(name=str(name), percent=int(percent) if percent is not None else None, source='BlueZ'))
    return out


def bluez_batteries() -> list[Battery] | None:
    if not shutil.which('busctl'):
        return None
    out = run(['busctl', '--system', '--json=short', 'call', 'org.bluez', '/',
               'org.freedesktop.DBus.ObjectManager', 'GetManagedObjects'], timeout=3)
    return None if out is None else parse_bluez(out)


def _read(path: Path) -> str | None:
    try:
        return path.read_text().strip()
    except OSError:
        return None


def sysfs_device_batteries(root: Path = POWER_SUPPLY) -> list[Battery]:
    """Peripheral batteries (scope=Device) exposed by kernel HID drivers."""
    out = []
    for supply in sorted(root.glob('*')):
        if _read(supply / 'scope') != 'Device' or _read(supply / 'type') != 'Battery':
            continue
        if _read(supply / 'present') == '0':
            continue
        name = _read(supply / 'model_name') or supply.name
        capacity = _read(supply / 'capacity')
        level = _read(supply / 'capacity_level') or ''
        percent = int(capacity) if capacity and capacity.isdigit() else None
        out.append(Battery(name=name, percent=percent, level='' if level == 'Unknown' else level, source='kernel'))
    return out


def parse_upower(text: str) -> list[Battery]:
    """Parse `upower --dump`, keeping peripherals only (not the laptop battery or AC)."""
    out = []
    for block in text.split('\n\n'):
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines or not lines[0].startswith('Device:'):
            continue
        path = lines[0].split(':', 1)[1].strip()
        if 'DisplayDevice' in path or 'line_power' in path or '/battery_BAT' in path:
            continue
        fields = {}
        for line in lines[1:]:
            if ':' in line:
                key, value = line.split(':', 1)
                fields.setdefault(key.strip(), value.strip())
        if fields.get('power supply') == 'yes':
            continue
        percent_text = fields.get('percentage', '').rstrip('%').split('%')[0].strip()
        if not percent_text:
            continue
        try:
            percent = int(round(float(percent_text)))
        except ValueError:
            continue
        name = fields.get('model') or fields.get('native-path') or path.rsplit('/', 1)[-1]
        out.append(Battery(name=name, percent=percent, source='UPower'))
    return out


def upower_batteries() -> list[Battery] | None:
    if not shutil.which('upower'):
        return None
    out = run(['upower', '--dump'], timeout=3)
    return None if out is None else parse_upower(out)


def merge(*groups: list[Battery] | None) -> list[Battery]:
    """Combine sources, keeping the first reading for each device name."""
    seen, out = set(), []
    for group in groups:
        for battery in group or []:
            key = battery.name.casefold().strip()
            if key in seen:
                continue
            seen.add(key)
            out.append(battery)
    return sorted(out, key=lambda b: b.name.casefold())


def linux_batteries() -> list[Battery]:
    bluez = bluez_batteries()
    if bluez is None:  # no busctl/BlueZ: UPower sees both Bluetooth and HID devices
        return merge(upower_batteries(), sysfs_device_batteries())
    return merge(bluez, sysfs_device_batteries())


HINT = 'No connected wireless devices are reporting a battery level.'
LINUX_HINT = (HINT + ' Some headsets only report it with PipeWire running, or with '
              '"Experimental = true" in /etc/bluetooth/main.conf.')
