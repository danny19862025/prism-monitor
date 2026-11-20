"""The always-on-top widget and its tray icon."""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QPoint, QRectF, QSettings, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QColor, QFont, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (QApplication, QGridLayout, QLabel, QMenu, QSizePolicy, QSystemTrayIcon,
                               QVBoxLayout, QWidget)

from . import __version__
from .collector import Collector
from .model import Snapshot
from .util import LINUX, WINDOWS

ACCENT = '#7cc7ff'
TEXT = '#eef3f8'
MUTED = '#9aa7b4'
GOOD, WARN, BAD = '#5fd38d', '#f2c14e', '#ff6b6b'


def battery_color(percent: int | None) -> str:
    if percent is None:
        return MUTED
    return BAD if percent <= 20 else WARN if percent <= 40 else GOOD


def fps_color(fps: float) -> str:
    return GOOD if fps >= 55 else WARN if fps >= 30 else BAD


def temp_color(temp: float | None) -> str:
    if temp is None:
        return ACCENT
    return GOOD if temp < 70 else WARN if temp < 85 else BAD


def chip_text(chip) -> str:
    parts = []
    if chip.load is not None:
        parts.append(f'{chip.load:.0f}%')
    if chip.temp is not None:
        parts.append(f'{chip.temp:.0f}°C')
    return '  ·  '.join(parts) or '—'


DEFAULT_OPACITY = 92


def make_icon() -> QIcon:
    pix = QPixmap(64, 64)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    path = QPainterPath()
    path.moveTo(32, 6); path.lineTo(58, 54); path.lineTo(6, 54); path.closeSubpath()
    p.setPen(QPen(QColor(ACCENT), 5))
    p.setBrush(QColor('#14202c'))
    p.drawPath(path)
    p.setPen(QPen(QColor(GOOD), 5))
    p.drawLine(18, 44, 28, 34); p.drawLine(28, 34, 34, 40); p.drawLine(34, 40, 46, 26)
    p.end()
    return QIcon(pix)


class Bar(QWidget):
    """Tiny battery level bar."""

    def __init__(self):
        super().__init__()
        self.percent: int | None = None
        self.setFixedSize(34, 10)

    def set_percent(self, percent: int | None):
        if percent != self.percent:
            self.percent = percent
            self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        p.setPen(QPen(QColor(MUTED), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(rect, 3, 3)
        if self.percent is not None:
            fill = QRectF(2, 2, (self.width() - 4) * max(0, min(100, self.percent)) / 100, self.height() - 4)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(battery_color(self.percent)))
            p.drawRoundedRect(fill, 2, 2)


def label(text='', size=10, color=TEXT, bold=False) -> QLabel:
    w = QLabel(text)
    f = QFont()
    f.setPointSizeF(size)
    f.setBold(bold)
    w.setFont(f)
    w.setStyleSheet(f'color: {color}; background: transparent;')
    return w


class Section(QWidget):
    def __init__(self, title: str):
        super().__init__()
        self.box = QVBoxLayout(self)
        self.box.setContentsMargins(0, 0, 0, 0)
        self.box.setSpacing(3)
        self.title = label(title.upper(), 8, ACCENT, True)
        self.box.addWidget(self.title)
        self.note = label('', 8.5, MUTED)
        self.note.setWordWrap(True)
        self.note.setMaximumWidth(290)
        self.note.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        self.box.addWidget(self.note)

    def set_note(self, text: str | None):
        self.note.setText(text or '')
        self.note.setVisible(bool(text))


class RowSection(Section):
    """Name / value rows that are rebuilt only when the set of names changes."""

    def __init__(self, title: str, with_bar=False):
        super().__init__(title)
        self.with_bar = with_bar
        self.grid_host = QWidget()
        self.grid = QGridLayout(self.grid_host)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(10)
        self.grid.setVerticalSpacing(2)
        self.box.insertWidget(1, self.grid_host)
        self.names: list[str] = []
        self.rows: list[tuple] = []

    def set_rows(self, rows: list[tuple[str, str, int | None, str]]):
        names = [r[0] for r in rows]
        if names != self.names:
            while self.grid.count():
                item = self.grid.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            self.rows = []
            for i, name in enumerate(names):
                n = label(name, 10, TEXT)
                n.setMaximumWidth(200)
                v = label('', 10, TEXT, True)
                v.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.grid.addWidget(n, i, 0)
                col = 1
                bar = None
                if self.with_bar:
                    bar = Bar()
                    self.grid.addWidget(bar, i, 1, Qt.AlignVCenter)
                    col = 2
                self.grid.addWidget(v, i, col)
                self.rows.append((n, v, bar))
            self.grid.setColumnStretch(0, 1)
            self.names = names
        for (n, v, bar), (name, value, percent, color) in zip(self.rows, rows):
            metrics = n.fontMetrics()
            n.setText(metrics.elidedText(name, Qt.ElideRight, 200))
            n.setToolTip(name)
            v.setText(value)
            v.setStyleSheet(f'color: {color}; background: transparent;')
            if bar:
                bar.set_percent(percent)
        self.grid_host.setVisible(bool(rows))


class FpsSection(Section):
    def __init__(self):
        super().__init__('Frame rate')
        line = QWidget()
        grid = QGridLayout(line)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(8)
        self.value = label('—', 26, TEXT, True)
        self.unit = label('FPS', 9, MUTED, True)
        self.app = label('', 9, TEXT)
        self.detail = label('', 8.5, MUTED)
        grid.addWidget(self.value, 0, 0, 2, 1)
        grid.addWidget(self.unit, 0, 1, Qt.AlignBottom)
        grid.addWidget(self.app, 0, 2, Qt.AlignBottom)
        grid.addWidget(self.detail, 1, 1, 1, 2, Qt.AlignTop)
        grid.setColumnStretch(2, 1)
        self.line = line
        self.box.insertWidget(1, line)

    def set_fps(self, fps):
        self.line.setVisible(fps is not None)
        if fps is None:
            return
        self.value.setText(f'{fps.fps:.0f}')
        self.value.setStyleSheet(f'color: {fps_color(fps.fps)}; background: transparent;')
        app = fps.app.removesuffix('.exe')
        self.app.setText(self.app.fontMetrics().elidedText(app, Qt.ElideRight, 170))
        self.app.setToolTip(fps.app)
        detail = f'{fps.frametime_ms:.1f} ms'
        if fps.low_1pct:
            detail += f' · 1% low {fps.low_1pct:.0f}'
        self.detail.setText(detail)


class Overlay(QWidget):
    def __init__(self, collector: Collector, settings: QSettings):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.collector = collector
        self.settings = settings
        self.setWindowTitle('Prism Monitor')
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.drag_from: QPoint | None = None

        box = QVBoxLayout(self)
        box.setContentsMargins(14, 12, 14, 12)
        box.setSpacing(10)
        self.fps = FpsSection()
        self.system = RowSection('System')
        self.fans = RowSection('Fans')
        self.batteries = RowSection('Bluetooth battery', with_bar=True)
        for w in (self.fps, self.system, self.fans, self.batteries):
            box.addWidget(w)
        self.setMinimumWidth(230)
        self.apply_settings()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(500)
        self.refresh()

    # settings ------------------------------------------------------------
    def opt(self, key, default):
        value = self.settings.value(key, default)
        if isinstance(default, bool):
            return value in (True, 'true', '1', 1)
        try:
            return type(default)(value)
        except (TypeError, ValueError):
            return default

    def apply_settings(self):
        self.setWindowFlag(Qt.WindowTransparentForInput, self.opt('click_through', False))
        self.update()

    def restore_position(self):
        pos = self.settings.value('pos')
        screen = QApplication.primaryScreen().availableGeometry()
        if isinstance(pos, QPoint) and any(s.availableGeometry().contains(pos) for s in QApplication.screens()):
            self.move(pos)
        else:
            self.adjustSize()
            self.move(screen.right() - self.width() - 24, screen.top() + 24)

    # data ----------------------------------------------------------------
    def refresh(self):
        snap: Snapshot = self.collector.snapshot()
        tips = self.opt('show_tips', False)

        def place(section, key, has_data, note_key):
            section.setVisible(self.opt(key, True) and (has_data or tips))
            section.set_note(snap.notes.get(note_key) if tips or not has_data else None)

        self.fps.set_fps(snap.fps)
        place(self.fps, 'show/fps', snap.fps is not None, 'fps')

        rows = []
        if snap.cpu is not None and snap.cpu.has_data():
            rows.append(('CPU', chip_text(snap.cpu), None, temp_color(snap.cpu.temp)))
        if snap.gpu is not None and snap.gpu.has_data():
            rows.append(('GPU', chip_text(snap.gpu), None, temp_color(snap.gpu.temp)))
        if snap.memory is not None:
            m = snap.memory
            rows.append(('Memory', f'{m.used_gb:.1f} / {m.total_gb:.0f} GB', None,
                         WARN if m.percent >= 90 else ACCENT))
            if m.swap_total_gb:
                rows.append(('Swap', f'{m.swap_used_gb:.1f} / {m.swap_total_gb:.0f} GB', None,
                             WARN if m.swap_used_gb / m.swap_total_gb >= 0.5 else ACCENT))
        self.system.set_rows(rows)
        if snap.gpu is not None and self.system.rows and len(rows) > 1 and rows[1][0] == 'GPU':
            self.system.rows[1][0].setToolTip(snap.gpu.name)
        self.system.setVisible(self.opt('show/system', True) and bool(rows))
        self.system.set_note(snap.notes.get('system') if tips else None)

        self.fans.set_rows([(f.name, f.text(), None, ACCENT) for f in snap.fans])
        place(self.fans, 'show/fans', bool(snap.fans), 'fans')
        self.batteries.set_rows([(b.name, b.text(), b.percent, battery_color(b.percent)) for b in snap.batteries])
        place(self.batteries, 'show/batteries', bool(snap.batteries), 'batteries')
        self.adjustSize()

    # painting / moving -----------------------------------------------------
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        alpha = max(40, min(255, int(255 * self.opt('opacity', DEFAULT_OPACITY) / 100)))
        p.setPen(QPen(QColor(124, 199, 255, 70), 1))
        p.setBrush(QColor(12, 16, 22, alpha))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 12, 12)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and not self.opt('locked', False):
            handle = self.windowHandle()
            if handle and handle.startSystemMove():  # needed on Wayland, nicer elsewhere
                return
            self.drag_from = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if self.drag_from is not None:
            self.move(event.globalPosition().toPoint() - self.drag_from)

    def mouseReleaseEvent(self, _):
        self.drag_from = None
        self.settings.setValue('pos', self.pos())

    def moveEvent(self, event):
        super().moveEvent(event)
        if self.isVisible():
            self.settings.setValue('pos', self.pos())

    def contextMenuEvent(self, event):
        self.menu_factory().exec(event.globalPos())


# autostart ---------------------------------------------------------------
def launch_command() -> list[str]:
    if getattr(sys, 'frozen', False):
        return [sys.executable]
    return [sys.executable, str(Path(__file__).resolve().parent.parent / 'main.py')]


def autostart_enabled() -> bool:
    if WINDOWS:
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Run') as key:
                winreg.QueryValueEx(key, 'PrismMonitor')
                return True
        except OSError:
            return False
    return linux_autostart_file().exists()


def linux_autostart_file() -> Path:
    import os
    base = Path(os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config')
    return base / 'autostart' / 'prism-monitor.desktop'


def set_autostart(enabled: bool):
    command = launch_command()
    if WINDOWS:
        import subprocess
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Run', 0,
                            winreg.KEY_SET_VALUE) as key:
            if enabled:
                winreg.SetValueEx(key, 'PrismMonitor', 0, winreg.REG_SZ, subprocess.list2cmdline(command))
            else:
                try:
                    winreg.DeleteValue(key, 'PrismMonitor')
                except OSError:
                    pass
        return
    path = linux_autostart_file()
    if enabled:
        import shlex
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('[Desktop Entry]\nType=Application\nName=Prism Monitor\n'
                        f'Exec={shlex.join(command)}\nIcon=utilities-system-monitor\n'
                        'X-GNOME-Autostart-enabled=true\n')
    else:
        path.unlink(missing_ok=True)


class Controller:
    def __init__(self, app: QApplication, demo=False):
        self.app = app
        self.settings = QSettings('PrismMonitor', 'PrismMonitor')
        self.collector = Collector(demo=demo)
        self.collector.start()
        self.overlay = Overlay(self.collector, self.settings)
        self.overlay.menu_factory = self.build_menu
        self.tray = None
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = QSystemTrayIcon(make_icon(), app)
            self.tray.setToolTip('Prism Monitor')
            self.tray.activated.connect(self.tray_clicked)
            self.tray.setContextMenu(self.build_menu())
            self.tray.show()
        app.aboutToQuit.connect(self.collector.stop)

    def show(self):
        self.overlay.restore_position()
        if self.settings.value('visible', True) in (True, 'true') or not self.tray:
            self.overlay.show()

    def tray_clicked(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            self.toggle_visible()

    def toggle_visible(self):
        visible = not self.overlay.isVisible()
        self.overlay.setVisible(visible)
        self.settings.setValue('visible', visible)

    def toggle(self, key, default=False):
        self.settings.setValue(key, not self.overlay.opt(key, default))
        was_visible = self.overlay.isVisible()
        self.overlay.apply_settings()
        if was_visible:
            self.overlay.show()  # changing window flags hides the window
        if self.tray:
            self.tray.setContextMenu(self.build_menu())

    def build_menu(self) -> QMenu:
        menu = QMenu()
        o = self.overlay
        menu.addAction('Hide widget' if o.isVisible() else 'Show widget', self.toggle_visible)
        menu.addSeparator()
        for key, text in (('show/fps', 'Show FPS'), ('show/system', 'Show CPU / GPU / memory'),
                          ('show/fans', 'Show fans'), ('show/batteries', 'Show Bluetooth battery')):
            a = menu.addAction(text, lambda k=key: self.toggle(k, True))
            a.setCheckable(True)
            a.setChecked(o.opt(key, True))
        tips = menu.addAction('Show tips for empty sections', lambda: self.toggle('show_tips'))
        tips.setCheckable(True)
        tips.setChecked(o.opt('show_tips', False))
        menu.addSeparator()
        lock = menu.addAction('Lock position', lambda: self.toggle('locked'))
        lock.setCheckable(True)
        lock.setChecked(o.opt('locked', False))
        through = menu.addAction('Click-through (use the tray icon to undo)', lambda: self.toggle('click_through'))
        through.setCheckable(True)
        through.setChecked(o.opt('click_through', False))
        through.setEnabled(self.tray is not None or o.opt('click_through', False))
        opacity = menu.addMenu('Background opacity')
        group = QActionGroup(opacity)
        for value in (60, 80, DEFAULT_OPACITY, 100):
            a = QAction(f'{value}%', opacity, checkable=True)
            a.setChecked(o.opt('opacity', DEFAULT_OPACITY) == value)
            a.triggered.connect(lambda _=False, v=value: self.set_opacity(v))
            group.addAction(a)
            opacity.addAction(a)
        start = menu.addAction('Start when I sign in', self.toggle_autostart)
        start.setCheckable(True)
        start.setChecked(autostart_enabled())
        if WINDOWS:
            menu.addSeparator()
            menu.addAction('Allow FPS without admin…', self.allow_fps)
        if LINUX:
            menu.addSeparator()
            menu.addAction('How to get game FPS…', self.linux_fps_help)
        menu.addSeparator()
        menu.addAction(f'Quit Prism Monitor {__version__}', self.app.quit)
        return menu

    def set_opacity(self, value):
        self.settings.setValue('opacity', value)
        self.overlay.update()

    def toggle_autostart(self):
        try:
            set_autostart(not autostart_enabled())
        except OSError as exc:
            self.message('Could not change sign-in start', str(exc))
        if self.tray:
            self.tray.setContextMenu(self.build_menu())

    def allow_fps(self):
        from .windows_helper import allow_fps_without_admin
        if allow_fps_without_admin():
            self.message('FPS permission', 'After the window says Done, sign out of Windows and back in.')

    def linux_fps_help(self):
        self.message('Game FPS on Linux',
                     'Install MangoHud, then start games through prism-monitor-run.\n'
                     'Steam: game Properties → Launch options → prism-monitor-run %command%')

    def message(self, title, text):
        if self.tray:
            self.tray.showMessage(title, text, make_icon(), 8000)
        else:
            if sys.stderr:
                print(f'{title}: {text}', file=sys.stderr)
