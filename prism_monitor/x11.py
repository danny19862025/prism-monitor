"""Make the widget behave like a desktop widget on Linux/X11 (XWayland too):
not listed in the taskbar/dock, the pager or Alt+Tab.

Qt has no API for this, so we ask the window manager directly with an EWMH
_NET_WM_STATE client message through libX11.
"""
from __future__ import annotations

import ctypes
import ctypes.util

_lib = None


def _x11():
    global _lib
    if _lib is None:
        name = ctypes.util.find_library('X11') or 'libX11.so.6'
        try:
            _lib = ctypes.CDLL(name)
        except OSError:
            _lib = False
            return None
        _lib.XOpenDisplay.restype = ctypes.c_void_p
        _lib.XOpenDisplay.argtypes = [ctypes.c_char_p]
        _lib.XInternAtom.restype = ctypes.c_ulong
        _lib.XInternAtom.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
        _lib.XDefaultRootWindow.restype = ctypes.c_ulong
        _lib.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
        _lib.XSendEvent.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_long, ctypes.c_void_p]
        _lib.XFlush.argtypes = [ctypes.c_void_p]
        _lib.XCloseDisplay.argtypes = [ctypes.c_void_p]
    return _lib or None


class _ClientMessage(ctypes.Structure):
    _fields_ = [('type', ctypes.c_int), ('serial', ctypes.c_ulong), ('send_event', ctypes.c_int),
                ('display', ctypes.c_void_p), ('window', ctypes.c_ulong), ('message_type', ctypes.c_ulong),
                ('format', ctypes.c_int), ('data', ctypes.c_long * 5)]


class _Event(ctypes.Union):
    _fields_ = [('xclient', _ClientMessage), ('pad', ctypes.c_long * 24)]


CLIENT_MESSAGE = 33
SUBSTRUCTURE = (1 << 19) | (1 << 20)  # SubstructureNotify | SubstructureRedirect


def set_states(window_id: int, add: list[str], remove: list[str] = ()) -> bool:
    """Add/remove _NET_WM_STATE_* flags on a mapped window. Returns False if X11 is unavailable."""
    lib = _x11()
    if not lib:
        return False
    display = lib.XOpenDisplay(None)
    if not display:
        return False
    try:
        root = lib.XDefaultRootWindow(display)
        state = lib.XInternAtom(display, b'_NET_WM_STATE', 0)
        for action, names in ((1, add), (0, remove)):
            # EWMH allows two properties per message
            for i in range(0, len(names), 2):
                pair = [lib.XInternAtom(display, f'_NET_WM_STATE_{n}'.encode(), 0) for n in names[i:i + 2]]
                event = _Event()
                msg = event.xclient
                msg.type, msg.send_event, msg.display = CLIENT_MESSAGE, 1, display
                msg.window, msg.message_type, msg.format = window_id, state, 32
                msg.data[0] = action
                msg.data[1] = pair[0]
                msg.data[2] = pair[1] if len(pair) > 1 else 0
                msg.data[3] = 1  # source: normal application
                lib.XSendEvent(display, root, 0, SUBSTRUCTURE, ctypes.byref(event))
        lib.XFlush(display)
        return True
    finally:
        lib.XCloseDisplay(display)


def show_on_all_desktops(window_id: int) -> bool:
    """Ask the window manager to show the window on every virtual desktop (_NET_WM_DESKTOP = all)."""
    lib = _x11()
    if not lib:
        return False
    display = lib.XOpenDisplay(None)
    if not display:
        return False
    try:
        event = _Event()
        msg = event.xclient
        msg.type, msg.send_event, msg.display = CLIENT_MESSAGE, 1, display
        msg.window, msg.format = window_id, 32
        msg.message_type = lib.XInternAtom(display, b'_NET_WM_DESKTOP', 0)
        msg.data[0] = 0xFFFFFFFF
        msg.data[1] = 1
        lib.XSendEvent(display, lib.XDefaultRootWindow(display), 0, SUBSTRUCTURE, ctypes.byref(event))
        lib.XFlush(display)
        return True
    finally:
        lib.XCloseDisplay(display)
