"""Polls every source on a background thread and hands the UI a Snapshot."""
from __future__ import annotations

import threading
import time

from . import battery, fans
from .fps import make_source
from .model import Snapshot
from .util import WINDOWS

FAN_EVERY = 2.0
BATTERY_EVERY = 15.0
GPU_EVERY = 5.0


class Collector:
    def __init__(self, demo: bool = False):
        self.demo = demo
        self.fps_source = None if demo else make_source()
        self.helper = None
        self.nvidia = fans.NvidiaFans()
        self.lock = threading.Lock()
        self.system_fans: list = []
        self.gpu_fans: list = []
        self.batteries: list = []
        self.battery_checked = False
        self.stopping = threading.Event()
        self.thread = threading.Thread(target=self._loop, daemon=True, name='collector')

    def start(self):
        if self.demo:
            return
        if WINDOWS:
            from .windows_helper import WindowsHelper
            self.helper = WindowsHelper()
            self.helper.start()
        self.fps_source.start()
        self.thread.start()

    def _loop(self):
        next_fan = next_battery = next_gpu = 0.0
        while not self.stopping.is_set():
            now = time.monotonic()
            if now >= next_gpu:
                gpu = self.nvidia.read()
                with self.lock:
                    self.gpu_fans = gpu
                next_gpu = now + GPU_EVERY
            if not WINDOWS:
                if now >= next_fan:
                    system = fans.hwmon_fans()
                    with self.lock:
                        self.system_fans = system
                    next_fan = now + FAN_EVERY
                if now >= next_battery:
                    found = battery.linux_batteries()
                    with self.lock:
                        self.batteries, self.battery_checked = found, True
                    next_battery = now + BATTERY_EVERY
            self.stopping.wait(0.5)

    def snapshot(self) -> Snapshot:
        if self.demo:
            return demo_snapshot()
        snap = Snapshot()
        with self.lock:
            system, gpu = list(self.system_fans), list(self.gpu_fans)
            snap.batteries = list(self.batteries)
            battery_checked = self.battery_checked
        lhm = False
        if self.helper:
            system, snap.batteries, lhm, battery_checked = self.helper.snapshot()
            if not system:
                system = fans.lhm_http_fans() or []
        snap.fans = fans.dedupe(system + gpu)
        if not snap.fans:
            if WINDOWS and lhm:
                snap.notes['fans'] = ('LibreHardwareMonitor is running but shares no fans. Run it as '
                                      'administrator so it can read the fan controller.')
            elif WINDOWS and self.helper and not self.helper.ready:
                snap.notes['fans'] = 'Reading sensors…'
            else:
                snap.notes['fans'] = fans.hint()
        if not snap.batteries:
            if not battery_checked:
                snap.notes['batteries'] = 'Looking for devices…'
            else:
                snap.notes['batteries'] = battery.HINT if WINDOWS else battery.LINUX_HINT
        snap.fps = self.fps_source.read()
        if snap.fps is None:
            snap.notes['fps'] = self.fps_source.error
        return snap

    def stop(self):
        self.stopping.set()
        if self.fps_source:
            self.fps_source.stop()
        if self.helper:
            self.helper.stop()


def demo_snapshot() -> Snapshot:
    from .model import Battery, Fan, Fps
    import math
    t = time.time()
    wobble = math.sin(t / 2)
    return Snapshot(
        fans=[Fan('CPU fan', rpm=int(1450 + 120 * wobble)), Fan('Case fan 1', rpm=980),
              Fan('GPU fan', percent=48 + 6 * wobble)],
        batteries=[Battery('WH-1000XM5', 80), Battery('Xbox Wireless Controller', 35),
                   Battery('MX Master 3S', 12)],
        fps=Fps('Demo game', fps=143 + 4 * wobble, frametime_ms=1000 / (143 + 4 * wobble), low_1pct=118),
    )
