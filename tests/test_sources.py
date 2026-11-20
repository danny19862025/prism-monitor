import json
import tempfile
import unittest
from pathlib import Path

from prism_monitor import battery, fans, fps, windows_helper


def write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


class FanTests(unittest.TestCase):
    def test_hwmon_labels_and_unreadable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / 'hwmon0/name', 'nct6798\n')
            write(root / 'hwmon0/fan1_input', '1200\n')
            write(root / 'hwmon0/fan1_label', 'CPU Fan\n')
            write(root / 'hwmon0/fan2_input', '800\n')
            (root / 'hwmon0/fan3_input').mkdir()  # unreadable entry is skipped
            write(root / 'hwmon1/name', 'amdgpu\n')
            write(root / 'hwmon1/fan1_input', '0\n')
            write(root / 'hwmon2/name', 'acpi_fan\n')
            write(root / 'hwmon2/fan1_input', '0\n')
            got = [(f.name, f.rpm) for f in fans.hwmon_fans(root)]
        self.assertEqual(got, [('CPU Fan', 1200), ('nct6798 fan 2', 800), ('GPU fan', 0)])

    def test_nvidia_smi(self):
        got = fans.parse_nvidia_smi('NVIDIA GeForce RTX 4070, 41 %\n')
        self.assertEqual((got[0].name, got[0].percent, got[0].text()), ('NVIDIA GeForce RTX 4070 fan', 41.0, '41%'))
        self.assertEqual(fans.parse_nvidia_smi('Laptop GPU, [N/A]\n'), [])

    def test_lhm_tree(self):
        tree = {'Text': 'Sensor', 'Children': [{'Text': 'PC', 'Children': [
            {'Text': 'ASUS PRIME B650', 'Children': [{'Text': 'Nuvoton NCT6799D', 'Children': [
                {'Text': 'Fans', 'Children': [{'Text': 'Fan #1', 'Value': '1,034 RPM', 'Children': []},
                                              {'Text': 'Fan #2', 'Value': '0 RPM', 'Children': []}]},
                {'Text': 'Temperatures', 'Children': [{'Text': 'CPU', 'Value': '41.0 °C', 'Children': []}]}]}]},
            {'Text': 'NVIDIA RTX', 'Children': [{'Text': 'Fans', 'Children': [
                {'Text': 'GPU Fan 1', 'Value': '1500 RPM', 'Children': []}]}]}]}]}
        got = [(f.name, f.rpm) for f in fans.parse_lhm_tree(tree)]
        self.assertEqual(got, [('ASUS PRIME B650 · Fan #1', 1034), ('ASUS PRIME B650 · Fan #2', 0),
                               ('NVIDIA RTX · GPU Fan 1', 1500)])


class BatteryTests(unittest.TestCase):
    def test_bluez(self):
        data = {'type': 'a{oa{sa{sv}}}', 'data': [{
            '/org/bluez/hci0/dev_AA': {'org.bluez.Device1': {'Alias': {'type': 's', 'data': 'WH-1000XM5'},
                                                             'Connected': {'type': 'b', 'data': True}},
                                       'org.bluez.Battery1': {'Percentage': {'type': 'y', 'data': 80}}},
            '/org/bluez/hci0/dev_BB': {'org.bluez.Device1': {'Alias': {'type': 's', 'data': 'Old'},
                                                             'Connected': {'type': 'b', 'data': False}},
                                       'org.bluez.Battery1': {'Percentage': {'type': 'y', 'data': 5}}},
            '/org/bluez/hci0': {'org.bluez.Adapter1': {}}}]}
        got = battery.parse_bluez(json.dumps(data))
        self.assertEqual([(b.name, b.percent) for b in got], [('WH-1000XM5', 80)])
        self.assertEqual(battery.parse_bluez('not json'), [])

    def test_sysfs_device_scope_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, scope, cap in (('BAT0', 'System', '70'), ('hidpp_battery_0', 'Device', '55'),
                                     ('ps-controller-battery-x', 'Device', None)):
                write(root / name / 'type', 'Battery')
                write(root / name / 'scope', scope)
                if cap:
                    write(root / name / 'capacity', cap)
                else:
                    write(root / name / 'capacity_level', 'Low')
            write(root / 'hidpp_battery_0/model_name', 'MX Master 3S')
            got = [(b.name, b.text()) for b in battery.sysfs_device_batteries(root)]
        self.assertEqual(got, [('MX Master 3S', '55%'), ('ps-controller-battery-x', 'Low')])

    def test_upower_skips_laptop_battery(self):
        text = ('Device: /org/freedesktop/UPower/devices/battery_BAT0\n  native-path: BAT0\n'
                '  power supply: yes\n  battery\n    percentage: 70%\n\n'
                'Device: /org/freedesktop/UPower/devices/headset_dev_AA\n  native-path: /org/bluez/hci0/dev_AA\n'
                '  model: Buds Pro\n  power supply: no\n  headset\n    percentage: 64%\n\n'
                'Device: /org/freedesktop/UPower/devices/DisplayDevice\n  power supply: yes\n    percentage: 70%\n')
        self.assertEqual([(b.name, b.percent) for b in battery.parse_upower(text)], [('Buds Pro', 64)])

    def test_merge_dedupes(self):
        a = [battery.Battery('Mouse', 50)]
        b = [battery.Battery('mouse', 40), battery.Battery('Keys', 90)]
        self.assertEqual([(x.name, x.percent) for x in battery.merge(a, None, b)], [('Keys', 90), ('Mouse', 50)])


class FpsTests(unittest.TestCase):
    def test_tracker_average_and_staleness(self):
        now = [0.0]
        t = fps.FrameTracker(clock=lambda: now[0])
        for _ in range(240):
            t.add(10, 'game.exe', 1000 / 120)
        for _ in range(30):
            t.add(20, 'launcher.exe', 1000 / 60)
        got = t.current()
        self.assertEqual(got.app, 'game.exe')
        self.assertAlmostEqual(got.fps, 120, places=3)
        self.assertEqual(t.current(prefer_pid=20).app, 'launcher.exe')
        now[0] = 5.0
        self.assertIsNone(t.current())

    def test_presentmon_v1_and_v2_headers(self):
        for header, row in (('Application,ProcessID,SwapChainAddress,Runtime,SyncInterval,PresentFlags,Dropped,'
                             'TimeInSeconds,msInPresentAPI,msBetweenPresents', 'Game.exe,42,0x1,DXGI,0,0,0,1.0,0.1,{ft}'),
                            ('Application,ProcessID,SwapChainAddress,PresentRuntime,CPUStartTime,MsBetweenAppStart',
                             'Game.exe,42,0x1,DXGI,10.0,{ft}')):
            t = fps.FrameTracker()
            p = fps.PresentMonParser(t)
            p.feed('error: something, with a comma')  # ignored before the header
            p.feed(header)
            p.feed('dwm.exe,1,0x2,DXGI,0,0,0,1,0.1,16.6')
            for _ in range(200):
                p.feed(row.format(ft='6.944'))
            got = t.current()
            self.assertEqual(got.app, 'Game.exe')
            self.assertAlmostEqual(got.fps, 144, delta=0.1)
            self.assertIsNotNone(got.low_1pct)

    def test_mangohud_tail(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / 'Cyberpunk2077.exe_2026-11-20_10-00-00.csv'
            log.write_text('os,cpu,gpu,ram,kernel,driver,cpuscheduler\nArch,x,y,16,6,1,none\n'
                           'fps,frametime,cpu_load,gpu_load,elapsed\n'
                           '90.1,11.1,40,90,1\n97.4,10.27,41,92,2\n98,10.2,4')  # last line half-written
            (Path(tmp) / 'Cyberpunk2077.exe_2026-11-20_10-00-00_summary.csv').write_text('x')
            src = fps.MangoHudSource(Path(tmp))
            got = src.read()
        self.assertEqual(got.app, 'Cyberpunk2077.exe')
        self.assertAlmostEqual(got.fps, 97.4)
        self.assertAlmostEqual(got.frametime_ms, 10.27)


class WindowsHelperTests(unittest.TestCase):
    def test_parse_message_single_items(self):
        msg = json.dumps({'fans': {'name': 'Board · Fan #1', 'rpm': 900}, 'lhm': True,
                          'batteries': {'name': 'Xbox Wireless Controller', 'percent': 30}})
        f, lhm, b = windows_helper.parse_message(msg)
        self.assertEqual((f[0].rpm, lhm, b[0].percent), (900, True, 30))
        f, lhm, b = windows_helper.parse_message(json.dumps({'fans': [], 'lhm': False, 'batteries': None}))
        self.assertEqual((f, lhm, b), ([], False, None))
        self.assertIsNone(windows_helper.parse_message('garbage'))

    def test_script_is_encoded(self):
        import base64
        text = base64.b64decode(windows_helper.encoded_script()).decode('utf-16-le')
        self.assertIn('Start-Sleep -Seconds 2', text)
        self.assertIn('$loop % 10', text)


if __name__ == '__main__':
    unittest.main()
