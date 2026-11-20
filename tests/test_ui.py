import os
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtWidgets import QApplication  # noqa: E402

from prism_monitor.collector import Collector  # noqa: E402
from prism_monitor.ui import Overlay  # noqa: E402
from PySide6.QtCore import QSettings  # noqa: E402


class OverlayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_demo_rows(self):
        settings = QSettings('PrismMonitorTests', 'PrismMonitorTests')
        settings.clear()
        settings.setValue('style', 'card')
        overlay = Overlay(Collector(demo=True), settings)
        overlay.menu_factory = lambda: None
        overlay.refresh()
        self.assertEqual(len(overlay.fans.rows), 3)
        self.assertEqual(len(overlay.batteries.rows), 3)
        self.assertTrue(overlay.fps.line.isVisibleTo(overlay))
        self.assertTrue(overlay.batteries.rows[2][1].text().endswith('%'))
        self.assertEqual([r[0].text() for r in overlay.system.rows], ['CPU', 'GPU', 'Memory', 'Swap'])
        self.assertIn('°C', overlay.system.rows[0][1].text())
        settings.clear()

    def test_poster_look(self):
        settings = QSettings('PrismMonitorTests', 'PrismMonitorTests')
        settings.clear()
        overlay = Overlay(Collector(demo=True), settings)
        overlay.menu_factory = lambda: None
        overlay.refresh()
        self.assertTrue(overlay.poster.isVisibleTo(overlay))
        self.assertFalse(overlay.fans.isVisibleTo(overlay))
        self.assertEqual(overlay.poster.hero[1], 'FPS')
        self.assertEqual([g.caption for g in overlay.poster.groups], ['SYSTEM', 'FANS', 'BLUETOOTH'])
        self.assertGreater(overlay.poster.width(), 200)
        settings.clear()


if __name__ == '__main__':
    unittest.main()
