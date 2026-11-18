"""The few Win32 calls textsaver needs, via ctypes."""

import ctypes
import math
import time
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
MONITORENUMPROC = ctypes.WINFUNCTYPE(
    wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC, ctypes.POINTER(wintypes.RECT), wintypes.LPARAM
)

user32.SetProcessDpiAwarenessContext.argtypes = [wintypes.HANDLE]
user32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
user32.EnumDisplayMonitors.argtypes = [wintypes.HDC, ctypes.c_void_p, MONITORENUMPROC, wintypes.LPARAM]
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND] + [ctypes.c_int] * 4 + [wintypes.UINT]
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
kernel32.CreateMutexW.restype = wintypes.HANDLE

WT_WINDOW_CLASS = "CASCADIA_HOSTING_WINDOW_CLASS"


class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]


def set_dpi_aware():
    # Per-monitor v2, so monitor rects and cursor positions are physical pixels.
    user32.SetProcessDpiAwarenessContext(wintypes.HANDLE(-4))


def single_instance(name):
    """Return a mutex handle if we are the only instance, else None. Keep the handle alive."""
    handle = kernel32.CreateMutexW(None, False, name)
    if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
        return None
    return handle


def monitors():
    """(left, top, right, bottom) of every monitor, in virtual-desktop coordinates."""
    rects = []

    def callback(_hmon, _hdc, rect, _lparam):
        r = rect.contents
        rects.append((r.left, r.top, r.right, r.bottom))
        return True

    user32.EnumDisplayMonitors(None, None, MONITORENUMPROC(callback), 0)
    return rects


def last_input_tick():
    info = LASTINPUTINFO(ctypes.sizeof(LASTINPUTINFO))
    user32.GetLastInputInfo(ctypes.byref(info))
    return info.dwTime


def cursor_pos():
    pt = wintypes.POINT()
    if not user32.GetCursorPos(ctypes.byref(pt)):
        return None
    return pt.x, pt.y


def park_cursor():
    # No API hides the pointer over another process's window, so tuck it into the
    # bottom-right corner of the primary monitor. Stay a few px inside: hard against
    # the edge, jitter gets clamped to "no movement" and would read as a keypress.
    x = user32.GetSystemMetrics(0) - 4  # SM_CXSCREEN
    y = user32.GetSystemMetrics(1) - 4  # SM_CYSCREEN
    user32.SetCursorPos(x, y)


def find_windows(class_name, title):
    found = []
    buf = ctypes.create_unicode_buffer(256)

    def callback(hwnd, _lparam):
        if user32.IsWindowVisible(hwnd):
            user32.GetClassNameW(hwnd, buf, 256)
            if buf.value == class_name:
                user32.GetWindowTextW(hwnd, buf, 256)
                if buf.value == title:
                    found.append(hwnd)
        return True

    user32.EnumWindows(WNDENUMPROC(callback), 0)
    return found


def make_topmost(hwnd):
    # HWND_TOPMOST, SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE
    user32.SetWindowPos(hwnd, wintypes.HWND(-1), 0, 0, 0, 0, 0x1 | 0x2 | 0x10)


def foreground(hwnd):
    # Only succeeds if Windows lets this process take the foreground; best effort.
    return bool(user32.SetForegroundWindow(hwnd))


class InputWatch:
    """Detects user activity from the global last-input tick.

    A tick change with the cursor in the same place is a key, click or wheel.
    A tick change with the cursor moved is mouse movement: it counts only once the
    cursor is more than `slack` px from where it was when the baseline was taken.
    """

    def __init__(self, grace=1.0, slack=20):
        self.ready = time.monotonic() + grace
        self.slack = slack
        self.tick = None

    def triggered(self):
        tick, pos = last_input_tick(), cursor_pos()
        if self.tick is None or time.monotonic() < self.ready:
            # Still in the grace period: keep moving the baseline.
            self.tick, self.pos, self.origin = tick, pos, pos
            return False
        if tick == self.tick:
            return False
        self.tick = tick
        if pos is None or self.origin is None:
            return True
        moved, self.pos = pos != self.pos, pos
        return not moved or math.dist(pos, self.origin) > self.slack
