"""Small helpers: hidden subprocesses, app folders."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

WINDOWS = sys.platform == 'win32'
LINUX = sys.platform.startswith('linux')
NO_WINDOW = 0x08000000 if WINDOWS else 0  # CREATE_NO_WINDOW


def run(args: list[str], timeout: float = 3.0) -> str | None:
    """Run a command without flashing a console; return stdout or None on any failure."""
    try:
        done = subprocess.run(args, capture_output=True, text=True, timeout=timeout,
                              creationflags=NO_WINDOW, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return None
    if done.returncode != 0:
        return None
    return done.stdout


def app_root() -> Path:
    """Folder that holds the app (the PyInstaller bundle or the source checkout)."""
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def state_dir() -> Path:
    if WINDOWS:
        base = Path(os.environ.get('LOCALAPPDATA') or Path.home() / 'AppData' / 'Local')
        return base / 'PrismMonitor'
    base = Path(os.environ.get('XDG_STATE_HOME') or Path.home() / '.local' / 'state')
    return base / 'prism-monitor'


def mangohud_log_dir() -> Path:
    return state_dir() / 'mangohud'
