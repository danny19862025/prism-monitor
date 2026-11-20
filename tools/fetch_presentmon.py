"""Download the pinned PresentMon console app (Windows FPS source) into vendor/presentmon."""
from __future__ import annotations

import hashlib
import sys
import urllib.request
from pathlib import Path

VERSION = '2.6.0'
URL = f'https://github.com/GameTechDev/PresentMon/releases/download/v{VERSION}/PresentMon-{VERSION}-x64.exe'
SHA256 = 'b2a706bc6ad475749e3b7e3409263aa1e6906d45bdcf993f6dbc0f660188f1af'

target = Path(__file__).resolve().parent.parent / 'vendor' / 'presentmon' / f'PresentMon-{VERSION}-x64.exe'


def main() -> int:
    if target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest() == SHA256:
        print(f'PresentMon {VERSION} already present: {target}')
        return 0
    target.parent.mkdir(parents=True, exist_ok=True)
    print(f'Downloading {URL}')
    with urllib.request.urlopen(URL, timeout=60) as reply:
        data = reply.read()
    digest = hashlib.sha256(data).hexdigest()
    if digest != SHA256:
        print(f'PresentMon checksum mismatch: {digest}', file=sys.stderr)
        return 1
    target.write_bytes(data)
    print(f'Saved {target}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
