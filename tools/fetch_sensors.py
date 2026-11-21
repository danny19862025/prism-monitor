#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Fetch checksum-pinned sensor helpers into vendor/ (not stored in git).

* Intel PresentMon 2.6.0 console build (MIT) for the FPS readout.
The app degrades gracefully when these are missing; the build needs them.
"""
import hashlib
import sys
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
VENDOR = ROOT / 'vendor'
PRESENTMON = ('https://github.com/GameTechDev/PresentMon/releases/download/v2.6.0/PresentMon-2.6.0-x64.exe',
              'b2a706bc6ad475749e3b7e3409263aa1e6906d45bdcf993f6dbc0f660188f1af')


def download(url, expected):
    with urlopen(Request(url, headers={'User-Agent': 'PrismMonitor-build/1'}), timeout=90) as response:
        data = response.read()
    actual = hashlib.sha256(data).hexdigest()
    if actual != expected:
        raise SystemExit(f'Checksum mismatch for {url}: {actual}')
    return data


def main():
    exe = VENDOR / 'presentmon' / 'PresentMon.exe'
    if not exe.exists() or hashlib.sha256(exe.read_bytes()).hexdigest() != PRESENTMON[1]:
        exe.parent.mkdir(parents=True, exist_ok=True)
        exe.write_bytes(download(*PRESENTMON))
        print(f'Fetched {exe.relative_to(ROOT)}')
    print('Sensor helpers ready.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
