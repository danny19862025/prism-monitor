"""One long-lived hidden PowerShell process that reports Windows-only sensors.

It prints one JSON line every couple of seconds:
  {"fans": [{"name":..,"rpm":..}], "lhm": true|false, "batteries": [...] | null}
`batteries` is only refreshed every BATTERY_EVERY loops (null means unchanged),
because enumerating Bluetooth devices costs about a second.

Fans: LibreHardwareMonitor / OpenHardwareMonitor publish their sensors in WMI
while they run. Batteries: DEVPKEY_Bluetooth_Battery on Bluetooth device nodes,
the value Settings > Bluetooth shows.
"""
from __future__ import annotations

import base64
import json
import subprocess
import threading

from .model import Battery, Fan
from .util import NO_WINDOW

SCRIPT = r'''
$ErrorActionPreference = 'SilentlyContinue'
$ProgressPreference = 'SilentlyContinue'
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$batteryKey = '{104EA319-6EE2-4701-BD47-8DDBF425BBE5} 2'
$loop = 0
function Get-Fans {
  foreach ($ns in 'root/LibreHardwareMonitor', 'root/OpenHardwareMonitor') {
    $sensors = @(Get-CimInstance -Namespace $ns -ClassName Sensor -Filter "SensorType='Fan'")
    if ($sensors.Count -eq 0) { continue }
    $names = @{}; $parents = @{}
    foreach ($h in @(Get-CimInstance -Namespace $ns -ClassName Hardware)) { $names[$h.Identifier] = $h.Name; $parents[$h.Identifier] = $h.Parent }
    $out = foreach ($s in ($sensors | Sort-Object Parent, Index)) {
      $id = $s.Parent
      while ($parents[$id] -and $names.ContainsKey($parents[$id])) { $id = $parents[$id] }
      $owner = $names[$id]
      $label = $s.Name
      if ($owner) { $label = "$owner · $($s.Name)" }
      [pscustomobject]@{ name = $label; rpm = [int][math]::Round([double]$s.Value) }
    }
    return @{ fans = @($out); lhm = $true }
  }
  $running = @(Get-Process -Name LibreHardwareMonitor, OpenHardwareMonitor).Count -gt 0
  return @{ fans = @(); lhm = $running }
}
function Get-Batteries {
  $result = @{}
  foreach ($d in @(Get-PnpDevice -PresentOnly | Where-Object { $_.InstanceId -like 'BTH*' })) {
    $p = Get-PnpDeviceProperty -InstanceId $d.InstanceId -KeyName $batteryKey
    if ($p -and $null -ne $p.Data) {
      $name = $d.FriendlyName
      if ($name -and (-not $result.ContainsKey($name) -or $result[$name] -lt [int]$p.Data)) { $result[$name] = [int]$p.Data }
    }
  }
  return @($result.GetEnumerator() | ForEach-Object { [pscustomobject]@{ name = $_.Key; percent = $_.Value } })
}
while ($true) {
  $f = Get-Fans
  $msg = @{ fans = $f.fans; lhm = $f.lhm; batteries = $null }
  if ($loop % BATTERY_EVERY -eq 0) { $msg.batteries = @(Get-Batteries) }
  [Console]::Out.WriteLine(($msg | ConvertTo-Json -Compress -Depth 4))
  [Console]::Out.Flush()
  $loop++
  Start-Sleep -Seconds INTERVAL
}
'''

INTERVAL = 2
BATTERY_EVERY = 10  # every 20 s


def encoded_script() -> str:
    text = SCRIPT.replace('BATTERY_EVERY', str(BATTERY_EVERY)).replace('INTERVAL', str(INTERVAL))
    return base64.b64encode(text.encode('utf-16-le')).decode('ascii')


def parse_message(line: str) -> tuple[list[Fan], bool, list[Battery] | None] | None:
    try:
        data = json.loads(line)
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None

    def as_list(value):  # ConvertTo-Json turns one-item arrays into objects
        if value is None:
            return None
        return value if isinstance(value, list) else [value]

    fans = []
    for item in as_list(data.get('fans')) or []:
        try:
            fans.append(Fan(name=str(item['name']), rpm=int(item['rpm']), source='LibreHardwareMonitor'))
        except (KeyError, TypeError, ValueError):
            continue
    batteries = None
    raw = as_list(data.get('batteries'))
    if raw is not None:
        batteries = []
        for item in raw:
            try:
                batteries.append(Battery(name=str(item['name']), percent=int(item['percent']), source='Windows'))
            except (KeyError, TypeError, ValueError):
                continue
        batteries.sort(key=lambda b: b.name.casefold())
    return fans, bool(data.get('lhm')), batteries


class WindowsHelper:
    def __init__(self):
        self.proc: subprocess.Popen | None = None
        self.fans: list[Fan] = []
        self.batteries: list[Battery] = []
        self.lhm_running = False
        self.ready = False
        self.error = ''
        self.lock = threading.Lock()

    def start(self):
        args = ['powershell.exe', '-NoLogo', '-NoProfile', '-NonInteractive',
                '-ExecutionPolicy', 'Bypass', '-EncodedCommand', encoded_script()]
        try:
            self.proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                         stdin=subprocess.DEVNULL, text=True, encoding='utf-8',
                                         errors='replace', creationflags=NO_WINDOW, bufsize=1)
        except OSError as exc:
            self.error = f'Could not start PowerShell: {exc}'
            return
        threading.Thread(target=self._pump, daemon=True, name='windows-helper').start()

    def _pump(self):
        assert self.proc and self.proc.stdout
        for line in self.proc.stdout:
            parsed = parse_message(line)
            if not parsed:
                continue
            fans, lhm, batteries = parsed
            with self.lock:
                self.fans, self.lhm_running, self.ready = fans, lhm, True
                if batteries is not None:
                    self.batteries = batteries
        self.error = 'The Windows sensor helper stopped.'

    def snapshot(self):
        with self.lock:
            return list(self.fans), list(self.batteries), self.lhm_running, self.ready

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.kill()


def allow_fps_without_admin() -> bool:
    """Ask for elevation once and add the user to Performance Log Users (S-1-5-32-559)."""
    import ctypes
    import getpass
    import os
    domain = os.environ.get('USERDOMAIN', '')
    user = f'{domain}\\{getpass.getuser()}' if domain else getpass.getuser()
    user = user.replace("'", "''")
    command = (f"Add-LocalGroupMember -SID 'S-1-5-32-559' -Member '{user}' -ErrorAction SilentlyContinue; "
               "Write-Host 'Done. Sign out of Windows and back in, then restart Prism Monitor.'; Start-Sleep 4")
    encoded = base64.b64encode(command.encode('utf-16-le')).decode('ascii')
    result = ctypes.windll.shell32.ShellExecuteW(None, 'runas', 'powershell.exe',
                                                 f'-NoProfile -EncodedCommand {encoded}', None, 1)
    return result > 32
