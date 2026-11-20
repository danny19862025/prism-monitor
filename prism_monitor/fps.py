"""Game frame-rate sources.

Windows: Intel PresentMon (MIT) streams one CSV row per presented frame for every
process. It needs administrator rights or membership of the built-in
"Performance Log Users" group.
Linux: there is no system-wide frame counter, so games are started through
`prism-monitor-run` (Steam: `prism-monitor-run %command%`). That enables
MangoHud logging into Prism Monitor's folder, and the newest log is tailed live.
"""
from __future__ import annotations

import csv
import io
import os
import shutil
import subprocess
import threading
import time
from collections import deque
from pathlib import Path

from .model import Fps
from .util import NO_WINDOW, WINDOWS, app_root, mangohud_log_dir


class FrameTracker:
    """Rolling per-process frame times -> FPS, average frame time and 1% low."""

    WINDOW_MS = 1000.0   # FPS is averaged over the last second of frames
    LOW_WINDOW_MS = 10000.0
    STALE_S = 2.0        # a process that stopped presenting disappears after this

    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.frames: dict[tuple[int, str], deque[float]] = {}
        self.last_seen: dict[tuple[int, str], float] = {}
        self.lock = threading.Lock()

    def add(self, pid: int, app: str, frametime_ms: float):
        if not 0.05 < frametime_ms < 5000:
            return
        key = (pid, app)
        with self.lock:
            q = self.frames.setdefault(key, deque())
            q.append(frametime_ms)
            total = sum(q)
            while q and total > self.LOW_WINDOW_MS:
                total -= q.popleft()
            self.last_seen[key] = self.clock()

    def stats(self, key) -> Fps | None:
        q = self.frames.get(key)
        if not q:
            return None
        recent, total = [], 0.0
        for ft in reversed(q):
            recent.append(ft)
            total += ft
            if total >= self.WINDOW_MS:
                break
        avg = total / len(recent)
        ordered = sorted(q, reverse=True)
        worst = ordered[:max(1, len(ordered) // 100)]
        low = 1000.0 / (sum(worst) / len(worst)) if len(q) >= 100 else None
        return Fps(app=key[1], fps=1000.0 / avg, frametime_ms=avg, low_1pct=low)

    def current(self, prefer_pid: int | None = None) -> Fps | None:
        now = self.clock()
        with self.lock:
            for key in [k for k, t in self.last_seen.items() if now - t > self.STALE_S]:
                self.last_seen.pop(key, None)
                self.frames.pop(key, None)
            if not self.frames:
                return None
            if prefer_pid is not None:
                for key in self.frames:
                    if key[0] == prefer_pid:
                        return self.stats(key)
            # otherwise the busiest presenter (the game, not a 60 Hz launcher)
            key = max(self.frames, key=lambda k: len(self.frames[k]))
            return self.stats(key)


def _column(header: list[str], *names: str) -> int | None:
    lowered = [h.strip().casefold() for h in header]
    for name in names:
        if name.casefold() in lowered:
            return lowered.index(name.casefold())
    return None


class PresentMonParser:
    """Feeds PresentMon CSV lines (1.x or 2.x column names) into a FrameTracker."""

    IGNORE = {'dwm.exe', 'prismmonitor.exe', 'explorer.exe', 'searchhost.exe',
              'textinputhost.exe', 'shellexperiencehost.exe', 'startmenuexperiencehost.exe'}

    def __init__(self, tracker: FrameTracker):
        self.tracker = tracker
        self.header: list[str] | None = None
        self.app = self.pid = self.ft = None

    def feed(self, line: str):
        line = line.strip()
        if not line:
            return
        row = next(csv.reader(io.StringIO(line)))
        if row and row[0].strip().casefold() == 'application':
            self.header = row
            self.app = _column(row, 'Application')
            self.pid = _column(row, 'ProcessID')
            self.ft = _column(row, 'MsBetweenPresents', 'msBetweenPresents', 'MsBetweenAppStart', 'FrameTime')
            return
        if self.header is None or None in (self.app, self.pid, self.ft) or len(row) <= max(self.app, self.pid, self.ft):
            return
        app = row[self.app].strip()
        if app.casefold() in self.IGNORE:
            return
        try:
            self.tracker.add(int(row[self.pid]), app, float(row[self.ft]))
        except ValueError:
            pass


def foreground_pid() -> int | None:
    if not WINDOWS:
        return None
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return None
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value or None


def find_presentmon() -> str | None:
    override = os.environ.get('PRISM_MONITOR_PRESENTMON')
    if override and Path(override).is_file():
        return override
    for folder in (app_root() / 'tools' / 'presentmon', app_root() / 'vendor' / 'presentmon'):
        for exe in sorted(folder.glob('PresentMon*.exe'), reverse=True):
            return str(exe)
    return shutil.which('PresentMon.exe') or shutil.which('PresentMon')


ACCESS_HINT = ('FPS needs permission to watch frame events. Right-click Prism Monitor and choose '
               '"Allow FPS without admin…" (then sign out and in), or run Prism Monitor as administrator.')


class PresentMonSource:
    def __init__(self):
        self.tracker = FrameTracker()
        self.parser = PresentMonParser(self.tracker)
        self.proc: subprocess.Popen | None = None
        self.error = ''
        self.exe = find_presentmon()
        self.thread: threading.Thread | None = None
        self.stopping = False

    def start(self):
        if not self.exe:
            self.error = 'PresentMon is missing from this build, so FPS is unavailable.'
            return
        args = [self.exe, '--output_stdout', '--no_console_stats', '--stop_existing_session',
                '--session_name', 'PrismMonitor', '--v1_metrics', '--exclude', 'dwm.exe']
        try:
            self.proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                         stdin=subprocess.DEVNULL, text=True, bufsize=1,
                                         creationflags=NO_WINDOW, errors='replace')
        except OSError as exc:
            self.error = f'Could not start PresentMon: {exc}'
            return
        self.error = 'Waiting for a game…'
        self.thread = threading.Thread(target=self._pump, daemon=True, name='presentmon')
        self.thread.start()

    def _pump(self):
        assert self.proc and self.proc.stdout
        log = deque(maxlen=8)
        for line in self.proc.stdout:
            if self.parser.header is None and not line.lstrip().casefold().startswith('application'):
                log.append(line.strip())
                continue
            self.parser.feed(line)
        code = self.proc.wait()
        if self.stopping:
            return
        text = ' '.join(log).casefold()
        if 'access' in text or 'elevat' in text or 'administrator' in text or code == 5:
            self.error = ACCESS_HINT
        else:
            self.error = f'PresentMon stopped (code {code}). ' + ' '.join(log)[-200:]

    def read(self) -> Fps | None:
        return self.tracker.current(foreground_pid())

    def stop(self):
        self.stopping = True
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.proc.kill()


def parse_mangohud_tail(lines: list[str], header: list[str]) -> Fps | None:
    """Latest FPS from the last complete data line of a MangoHud log."""
    fps_col = _column(header, 'fps')
    ft_col = _column(header, 'frametime')
    if fps_col is None:
        return None
    for line in reversed(lines):
        parts = line.strip().split(',')
        if len(parts) != len(header):  # skip a half-written last line
            continue
        try:
            fps = float(parts[fps_col])
            ft = float(parts[ft_col]) if ft_col is not None else 1000.0 / max(fps, 0.1)
        except ValueError:
            continue
        return Fps(app='', fps=fps, frametime_ms=ft)
    return None


def mangohud_app_name(path: Path) -> str:
    stem = path.stem  # "<program>_YYYY-MM-DD_HH-MM-SS"
    parts = stem.rsplit('_', 2)
    return parts[0] if len(parts) == 3 else stem


LINUX_HINT = ('Start games with prism-monitor-run (Steam launch options: '
              '"prism-monitor-run %command%").')


class MangoHudSource:
    LIVE_S = 3.0

    def __init__(self, folder: Path | None = None):
        self.folder = folder or mangohud_log_dir()
        self.error = ''
        self.cached: tuple[Path, list[str]] | None = None

    def start(self):
        self.folder.mkdir(parents=True, exist_ok=True)
        cutoff = time.time() - 3 * 86400
        for old in self.folder.glob('*.csv'):
            try:
                if old.stat().st_mtime < cutoff:
                    old.unlink()
            except OSError:
                pass
        if not shutil.which('mangohud'):
            self.error = ('Install MangoHud (sudo pacman -S mangohud lib32-mangohud), then start games with '
                          'prism-monitor-run (Steam launch options: "prism-monitor-run %command%").')
        else:
            self.error = LINUX_HINT

    def _header(self, path: Path) -> list[str] | None:
        if self.cached and self.cached[0] == path:
            return self.cached[1]
        try:
            with path.open(errors='replace') as f:
                for _ in range(12):
                    line = f.readline()
                    if not line:
                        break
                    if line.startswith('fps,'):
                        header = line.strip().split(',')
                        self.cached = (path, header)
                        return header
        except OSError:
            pass
        return None

    def read(self) -> Fps | None:
        now = time.time()
        newest, newest_time = None, 0.0
        try:
            for log in self.folder.glob('*.csv'):
                if log.name.endswith('_summary.csv'):
                    continue
                mtime = log.stat().st_mtime
                if mtime > newest_time:
                    newest, newest_time = log, mtime
        except OSError:
            return None
        if newest is None or now - newest_time > self.LIVE_S:
            return None
        header = self._header(newest)
        if not header:
            return None
        try:
            with newest.open('rb') as f:
                f.seek(0, os.SEEK_END)
                size = f.tell()
                f.seek(max(0, size - 4096))
                tail = f.read().decode(errors='replace').splitlines()[1:]
        except OSError:
            return None
        fps = parse_mangohud_tail(tail, header)
        if fps is None:
            return None
        return Fps(app=mangohud_app_name(newest), fps=fps.fps, frametime_ms=fps.frametime_ms)

    def stop(self):
        pass


def make_source():
    return PresentMonSource() if WINDOWS else MangoHudSource()
