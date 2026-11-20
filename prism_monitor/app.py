"""Entry point and command-line options."""
from __future__ import annotations

import argparse
import os
import shutil
import sys

from . import __version__
from .util import LINUX, mangohud_log_dir, state_dir


def say(text: str, error: bool = False):
    stream = sys.stderr if error else sys.stdout
    if stream:  # a windowed (no console) Windows build has no stdout/stderr
        print(text, file=stream, flush=True)


def run_game(command: list[str]) -> int:
    """Linux: start a game with MangoHud logging into Prism Monitor's folder."""
    if not command:
        print('usage: prism-monitor-run <game command…>   (Steam: prism-monitor-run %command%)', file=sys.stderr)
        return 2
    folder = mangohud_log_dir()
    folder.mkdir(parents=True, exist_ok=True)
    extra = f'output_folder={folder},autostart_log=1,log_interval=250'
    if os.environ.get('PRISM_MONITOR_HUD') != '1':
        # MangoHud stops logging when its HUD is off (no_display), so draw it fully transparent
        extra += ',fps_only,alpha=0,background_alpha=0'
    current = os.environ.get('MANGOHUD_CONFIG')
    os.environ['MANGOHUD_CONFIG'] = f'{current},{extra}' if current else extra
    os.environ['MANGOHUD'] = '1'
    wrapper = shutil.which('mangohud')
    if not wrapper:
        print('prism-monitor-run: MangoHud is not installed, so FPS will not be reported.', file=sys.stderr)
    args = [wrapper, *command] if wrapper else command
    os.execvp(args[0], args)
    return 127


INSTANCE_NAME = f'prism-monitor-{os.getuid() if hasattr(os, "getuid") else os.environ.get("USERNAME", "user")}'


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog='prism-monitor', description='Fan speed, FPS and Bluetooth battery widget.')
    parser.add_argument('--version', action='version', version=f'Prism Monitor {__version__}')
    parser.add_argument('--demo', action='store_true', help='show sample readings instead of real sensors')
    parser.add_argument('--smoke-test', action='store_true', help='start, read sensors once and exit')
    parser.add_argument('--screenshot', metavar='PNG', help='save a picture of the widget and exit')
    parser.add_argument('--print', dest='print_once', action='store_true', help='print one reading to the terminal')
    parser.add_argument('--run-game', nargs=argparse.REMAINDER, metavar='CMD',
                        help='(Linux) run a game with FPS logging enabled')
    args = parser.parse_args(argv)

    if args.run_game is not None:
        command = args.run_game[1:] if args.run_game[:1] == ['--'] else args.run_game
        return run_game(command)
    if args.print_once:
        return print_once(args.demo)

    if LINUX and os.environ.get('WAYLAND_DISPLAY') and os.environ.get('DISPLAY') and 'QT_QPA_PLATFORM' not in os.environ:
        # Wayland gives apps no "always on top" or saved positions; XWayland does.
        os.environ['QT_QPA_PLATFORM'] = 'xcb;wayland'

    from PySide6.QtCore import QLockFile, QTimer
    from PySide6.QtWidgets import QApplication
    from .ui import Controller, make_icon

    app = QApplication(sys.argv[:1])
    app.setApplicationName('Prism Monitor')
    app.setOrganizationName('PrismMonitor')
    app.setQuitOnLastWindowClosed(False)
    app.setWindowIcon(make_icon())

    lock = None
    if not (args.smoke_test or args.screenshot):
        state_dir().mkdir(parents=True, exist_ok=True)
        lock = QLockFile(str(state_dir() / 'instance.lock'))
        if not lock.tryLock(100):
            # Already running: tell it to become movable/clickable again (undoes click-through and lock).
            from PySide6.QtNetwork import QLocalSocket
            sock = QLocalSocket()
            sock.connectToServer(INSTANCE_NAME)
            if sock.waitForConnected(1000):
                sock.write(b'unlock\n')
                sock.waitForBytesWritten(1000)
                sock.disconnectFromServer()
                say('Prism Monitor is already running; it can be dragged and right-clicked again.')
            else:
                say('Prism Monitor is already running (look for its tray icon).', error=True)
            return 0

    controller = Controller(app, demo=args.demo)
    server = None
    if lock is not None:
        from PySide6.QtNetwork import QLocalServer
        QLocalServer.removeServer(INSTANCE_NAME)
        server = QLocalServer()
        if server.listen(INSTANCE_NAME):
            def incoming():
                while server.hasPendingConnections():
                    conn = server.nextPendingConnection()
                    conn.readyRead.connect(lambda c=conn: (c.readAll(), controller.unlock()))
            server.newConnection.connect(incoming)
    controller.show()

    if args.smoke_test:
        def finish():
            snap = controller.collector.snapshot()
            say(f'smoke test ok: {len(snap.fans)} fans, {len(snap.batteries)} batteries, '
                f'fps={"yes" if snap.fps else "no"}')
            app.quit()
        QTimer.singleShot(2500, finish)
    if args.screenshot:
        def shoot():
            controller.overlay.refresh()
            controller.overlay.grab().save(args.screenshot)
            app.quit()
        QTimer.singleShot(2500, shoot)
    code = app.exec()
    controller.collector.stop()
    return code


def print_once(demo: bool) -> int:
    import time
    from .collector import Collector
    c = Collector(demo=demo)
    c.start()
    time.sleep(3)
    deadline = time.monotonic() + 30  # PowerShell's first Bluetooth scan can be slow
    while c.helper and not c.helper.ready and time.monotonic() < deadline:
        time.sleep(0.5)
    snap = c.snapshot()
    c.stop()
    print('Fans:')
    for f in snap.fans:
        print(f'  {f.name}: {f.text()}  [{f.source}]')
    if not snap.fans:
        print(f'  ({snap.notes.get("fans", "none")})')
    print('Bluetooth battery:')
    for b in snap.batteries:
        print(f'  {b.name}: {b.text()}  [{b.source}]')
    if not snap.batteries:
        print(f'  ({snap.notes.get("batteries", "none")})')
    print('FPS:', f'{snap.fps.app} {snap.fps.fps:.0f}' if snap.fps else f'({snap.notes.get("fps", "none")})')
    return 0
