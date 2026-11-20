"""KDE Plasma: ask KWin (through a tiny one-shot KWin script over D-Bus) to treat the
widget like a desktop widget: on every virtual desktop, and out of the taskbar,
pager and Alt+Tab. Plain X11 hints are not enough under Wayland, where KWin keeps
XWayland's own desktop list separate."""
from __future__ import annotations

import os

from .util import state_dir

SCRIPT_NAME = 'prism-monitor-widget'
SCRIPT = '''
for (const w of workspace.windowList()) {
    if (w.pid === %d && w.caption === "Prism Monitor") {
        w.onAllDesktops = true;
        w.skipTaskbar = true;
        w.skipPager = true;
        w.skipSwitcher = true;
    }
}
'''


def is_kde() -> bool:
    return 'KDE' in os.environ.get('XDG_CURRENT_DESKTOP', '').upper()


def make_widget_like() -> bool:
    """Returns True if KWin accepted and ran the script."""
    if not is_kde():
        return False
    try:
        from PySide6.QtDBus import QDBusConnection, QDBusInterface
    except ImportError:
        return False
    bus = QDBusConnection.sessionBus()
    if not bus.isConnected():
        return False
    path = state_dir() / 'kwin-widget.js'
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(SCRIPT % os.getpid())
    except OSError:
        return False
    scripting = QDBusInterface('org.kde.KWin', '/Scripting', 'org.kde.kwin.Scripting', bus)
    if not scripting.isValid():
        return False
    scripting.call('unloadScript', SCRIPT_NAME)  # a copy left over from an earlier run
    reply = scripting.call('loadScript', str(path), SCRIPT_NAME)
    args = reply.arguments()
    if not args or not isinstance(args[0], int) or args[0] < 0:
        return False
    script = QDBusInterface('org.kde.KWin', f'/Scripting/Script{args[0]}', 'org.kde.kwin.Script', bus)
    script.call('run')
    scripting.call('unloadScript', SCRIPT_NAME)
    return True
