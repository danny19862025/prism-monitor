"""Polls every source on a background thread and hands the UI a Snapshot."""
from __future__ import annotations

import threading
import time

from . import battery, fans, system
from .fps import make_source
from .model import Snapshot
from .util import WINDOWS

FAN_EVERY = 2.0
BATTERY_EVERY = 15.0
GPU_EVERY = 3.0
CPU_EVERY = 1.0


class Collector:
    def __init__(self, demo: bool = False):
        self.demo = demo
        self.fps_source = None if demo else make_source()
        self.helper = None
        self.nvidia = system.NvidiaSmi()
        self.cpu_load = system.CpuLoad()
        self.lock = threading.Lock()
        self.system_fans: list = []
        self.nvidia_gpus: list = []
        self.batteries: list = []
        self.battery_checked = False
        self.cpu: system.Chip | None = None
        self.linux_gpu: system.Chip | None = None
        self.memory: system.Memory | None = None
        self.lhm_web: tuple[system.Chip | None, system.Chip | None] = (None, None)
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
        next_fan = next_battery = next_gpu = next_cpu = 0.0
        while not self.stopping.is_set():
            now = time.monotonic()
            if now >= next_cpu:
                load, mem = self.cpu_load.read(), system.memory()
                temp = None if WINDOWS else system.linux_cpu_temp()
                with self.lock:
                    self.cpu = system.Chip('CPU', temp, load)
                    self.memory = mem
                next_cpu = now + CPU_EVERY
            if now >= next_gpu:
                gpus = self.nvidia.read()
                linux_gpu = None if WINDOWS else system.linux_gpu()
                with self.lock:
                    self.nvidia_gpus, self.linux_gpu = gpus, linux_gpu
                next_gpu = now + GPU_EVERY
            if now >= next_fan:
                if WINDOWS:
                    web = None
                    if self.helper and self.helper.ready and not self.helper.snapshot()[0]:
                        web = system_from_lhm_web()
                    with self.lock:
                        self.system_fans = web[0] if web else []
                        self.lhm_web = web[1:] if web else (None, None)
                else:
                    found = fans.hwmon_fans()
                    with self.lock:
                        self.system_fans = found
                next_fan = now + FAN_EVERY
            if not WINDOWS and now >= next_battery:
                found = battery.linux_batteries()
                with self.lock:
                    self.batteries, self.battery_checked = found, True
                next_battery = now + BATTERY_EVERY
            self.stopping.wait(0.25)

    def snapshot(self) -> Snapshot:
        if self.demo:
            return demo_snapshot()
        snap = Snapshot()
        with self.lock:
            system_fans, gpus = list(self.system_fans), list(self.nvidia_gpus)
            snap.batteries = list(self.batteries)
            battery_checked = self.battery_checked
            cpu, linux_gpu, snap.memory = self.cpu, self.linux_gpu, self.memory
            web_cpu, web_gpu = self.lhm_web
        lhm = False
        helper_cpu = helper_gpu = None
        if self.helper:
            helper_fans, snap.batteries, lhm, battery_checked = self.helper.snapshot()
            system_fans = helper_fans or system_fans
            helper_cpu, helper_gpu = self.helper.chips()

        # CPU: usage from the OS, temperature from hwmon (Linux) or LibreHardwareMonitor (Windows)
        if cpu is not None:
            extra = helper_cpu or web_cpu
            temp = cpu.temp if cpu.temp is not None else (extra.temp if extra else None)
            snap.cpu = system.Chip('CPU', temp, cpu.load)
        # GPU: NVIDIA first, then amdgpu/nouveau (Linux) or LibreHardwareMonitor (Windows)
        if gpus and (gpus[0].temp is not None or gpus[0].load is not None):
            snap.gpu = system.Chip(gpus[0].name, gpus[0].temp, gpus[0].load)
        else:
            snap.gpu = linux_gpu or helper_gpu or web_gpu

        snap.fans = fans.dedupe(system_fans + fans.nvidia_fans(gpus))
        if not snap.fans:
            if WINDOWS and lhm:
                snap.notes['fans'] = ('LibreHardwareMonitor is running but shares no fans. Run it as '
                                      'administrator so it can read the fan controller.')
            elif WINDOWS and self.helper and not self.helper.ready:
                snap.notes['fans'] = 'Reading sensors…'
            else:
                snap.notes['fans'] = fans.hint()
        if WINDOWS and snap.cpu and snap.cpu.temp is None:
            snap.notes['system'] = 'CPU temperature needs LibreHardwareMonitor running as administrator.'
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


def system_from_lhm_web():
    """(fans, cpu, gpu) from LibreHardwareMonitor's optional web server, or None."""
    import json
    import urllib.request
    try:
        with urllib.request.urlopen('http://127.0.0.1:8085/data.json', timeout=0.4) as reply:
            data = json.load(reply)
    except (OSError, ValueError):
        return None
    cpu, gpu = system.parse_lhm_chips(data)
    return fans.parse_lhm_tree(data), cpu, gpu


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
        cpu=system.Chip('CPU', 64 + 3 * wobble, 38 + 10 * wobble),
        gpu=system.Chip('NVIDIA GeForce RTX 4070', 71 + 2 * wobble, 92),
        memory=system.Memory(9.4, 31.9, 0.2, 8.0),
    )
