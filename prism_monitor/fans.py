"""Fan speed sources.

Linux: kernel hwmon (`/sys/class/hwmon/*/fan*_input`), which covers motherboard
Super-I/O chips, laptop EC drivers (hp, thinkpad, dell-smm, asus…) and AMD GPUs.
Windows: Windows has no built-in fan API, so speeds come from LibreHardwareMonitor
(its WMI namespace via the PowerShell helper, or its optional web server).
Both: NVIDIA GPU fan duty through `nvidia-smi`.
"""
from __future__ import annotations

import json
import urllib.request
from pathlib import Path

from .model import Fan
from .util import WINDOWS

HWMON = Path('/sys/class/hwmon')

_FRIENDLY_CHIPS = {
    'amdgpu': 'GPU', 'nouveau': 'GPU', 'hp': 'System', 'thinkpad': 'System',
    'dell_smm': 'System', 'asus': 'System', 'asus_wmi_sensors': 'Board',
    'nct6775': 'Board', 'nct6683': 'Board', 'it87': 'Board', 'acpi_fan': 'ACPI',
}


def _read(path: Path) -> str | None:
    try:
        return path.read_text().strip()
    except OSError:  # many fan attributes raise ENODEV/EIO when the chip is asleep
        return None


def _number_in(name: str, prefix: str, suffix: str = '') -> int:
    middle = name[len(prefix):len(name) - len(suffix)]
    return int(middle) if middle.isdigit() else 0


def hwmon_fans(root: Path = HWMON) -> list[Fan]:
    fans: list[Fan] = []
    for chip in sorted(root.glob('hwmon*'), key=lambda p: _number_in(p.name, 'hwmon')):
        chip_name = _read(chip / 'name') or chip.name
        inputs = sorted(chip.glob('fan*_input'), key=lambda p: _number_in(p.name, 'fan', '_input'))
        for item in inputs:
            value = _read(item)
            if value is None or not value.lstrip('-').isdigit():
                continue
            index = _number_in(item.name, 'fan', '_input')
            label = _read(chip / f'fan{index}_label')
            prefix = _FRIENDLY_CHIPS.get(chip_name, chip_name)
            name = label or (f'{prefix} fan' if len(inputs) == 1 else f'{prefix} fan {index}')
            fans.append(Fan(name=name, rpm=max(0, int(value)), source=f'hwmon:{chip_name}'))
    # ACPI fan objects mostly mirror a real fan as on/off; hide them when real ones exist
    if any(f.source != 'hwmon:acpi_fan' for f in fans):
        fans = [f for f in fans if f.source != 'hwmon:acpi_fan']
    return fans


def nvidia_fans(gpus) -> list[Fan]:
    """Fan rows from system.NvidiaSmi readings (NVIDIA reports duty %, not RPM)."""
    fans = []
    for i, gpu in enumerate(gpus):
        if gpu.fan_percent is None:  # passively cooled or laptop GPUs report N/A
            continue
        label = f'{gpu.name} fan' if len(gpus) == 1 else f'{gpu.name} #{i} fan'
        fans.append(Fan(name=label, percent=gpu.fan_percent, source='nvidia-smi'))
    return fans


def parse_lhm_tree(data: dict) -> list[Fan]:
    """Walk LibreHardwareMonitor's `data.json` tree and return every RPM sensor."""
    fans: list[Fan] = []

    def walk(node: dict, hardware: str, depth: int):
        text = str(node.get('Text', ''))
        value = str(node.get('Value', ''))
        children = node.get('Children') or []
        if not children and value.upper().endswith('RPM'):
            number = value.upper().replace('RPM', '').replace(',', '').strip()
            try:
                rpm = int(round(float(number)))
            except ValueError:
                return
            name = text if not hardware else f'{hardware} · {text}'
            fans.append(Fan(name=name, rpm=rpm, source='LibreHardwareMonitor'))
            return
        # depth 2 is the hardware level: root ("Sensor") > computer > hardware
        next_hw = text if depth == 2 else hardware
        for child in children:
            walk(child, next_hw, depth + 1)

    walk(data, '', 0)
    return fans


def lhm_http_fans(port: int = 8085) -> list[Fan] | None:
    """Fans from LibreHardwareMonitor's 'Remote web server' option, or None if it is off."""
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/data.json', timeout=0.4) as reply:
            return parse_lhm_tree(json.load(reply))
    except (OSError, ValueError):
        return None


def dedupe(fans: list[Fan]) -> list[Fan]:
    seen, out = set(), []
    for fan in fans:
        key = fan.name.casefold()
        if key not in seen:
            seen.add(key)
            out.append(fan)
    return out


WINDOWS_HINT = ('Windows does not expose fan speeds itself. Install and run LibreHardwareMonitor '
                '(winget install LibreHardwareMonitor.LibreHardwareMonitor) and Prism Monitor '
                'picks its fans up automatically.')
LINUX_HINT = ('No readable fan sensors. Load your board/laptop driver (e.g. sensors-detect, '
              'nct6775, it87, dell-smm-hwmon) so fans appear in /sys/class/hwmon.')


def hint() -> str:
    return WINDOWS_HINT if WINDOWS else LINUX_HINT
