"""The few Win32 calls textsaver needs, via ctypes."""

import ctypes
import math
import time
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

MONITORENUMPROC = ctypes.WINFUNCTYPE(
    wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC, ctypes.POINTER(wintypes.RECT), wintypes.LPARAM
)


class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]


class COORD(ctypes.Structure):
    _fields_ = [("X", ctypes.c_short), ("Y", ctypes.c_short)]


class CONSOLE_FONT_INFOEX(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.ULONG),
        ("nFont", wintypes.DWORD),
        ("dwFontSize", COORD),
        ("FontFamily", wintypes.UINT),
        ("FontWeight", wintypes.UINT),
        ("FaceName", wintypes.WCHAR * 32),
    ]


user32.SetProcessDpiAwarenessContext.argtypes = [wintypes.HANDLE]
user32.EnumDisplayMonitors.argtypes = [wintypes.HDC, ctypes.c_void_p, MONITORENUMPROC, wintypes.LPARAM]
user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND] + [ctypes.c_int] * 4 + [wintypes.UINT]
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.ShowScrollBar.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.BOOL]
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.GetDpiForWindow.argtypes = [wintypes.HWND]
kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
kernel32.CreateMutexW.restype = wintypes.HANDLE
kernel32.GetStdHandle.restype = wintypes.HANDLE
kernel32.GetConsoleWindow.restype = wintypes.HWND
kernel32.GetConsoleMode.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
kernel32.SetConsoleMode.argtypes = [wintypes.HANDLE, wintypes.DWORD]
kernel32.SetCurrentConsoleFontEx.argtypes = [wintypes.HANDLE, wintypes.BOOL, ctypes.POINTER(CONSOLE_FONT_INFOEX)]
kernel32.GetCurrentConsoleFontEx.argtypes = [wintypes.HANDLE, wintypes.BOOL, ctypes.POINTER(CONSOLE_FONT_INFOEX)]
kernel32.SetConsoleDisplayMode.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(COORD)]


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


def fit_font(out, width, height, columns, rows, face, tallest, smallest):
    """Set the console font `tallest` px high, or smaller if `columns` x `rows` cells need that to fit.

    `width` and `height` are the screen's pixels. The font never goes below `smallest` px.
    """
    size = tallest
    while True:
        font = CONSOLE_FONT_INFOEX(ctypes.sizeof(CONSOLE_FONT_INFOEX), 0, COORD(0, size), 54, 400, face)
        kernel32.SetCurrentConsoleFontEx(out, False, ctypes.byref(font))
        kernel32.GetCurrentConsoleFontEx(out, False, ctypes.byref(font))  # The cell size it really got.
        cell = font.dwFontSize
        if size <= smallest or not cell.X or not cell.Y:
            return
        fit = min(width / (cell.X * columns), height / (cell.Y * rows))
        if fit >= 1:
            return
        size = max(smallest, min(size - 1, int(size * fit)))


def fullscreen_console(monitor, columns, rows, face="Consolas", points=36, smallest=18):
    """Turn this process's classic console window into a fullscreen terminal on `monitor`.

    The font is `points` high, or smaller (down to `smallest`) when text of `columns` x `rows`
    cells would not fit. Fewer, larger cells are what keep the full-screen effects fluid.
    """
    out = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
    mode = wintypes.DWORD()
    kernel32.GetConsoleMode(out, ctypes.byref(mode))
    kernel32.SetConsoleMode(out, mode.value | 0x4)  # ENABLE_VIRTUAL_TERMINAL_PROCESSING

    hwnd = kernel32.GetConsoleWindow()
    # Fullscreen happens on whichever monitor holds the window, so move it there first.
    # HWND_TOPMOST keeps it above the taskbar; SWP_NOSIZE.
    user32.SetWindowPos(hwnd, wintypes.HWND(-1), monitor[0] + 50, monitor[1] + 50, 0, 0, 0x1)
    # Consolas draws block characters edge to edge here; Cascadia leaves seams between cells.
    left, top, right, bottom = monitor
    scale = user32.GetDpiForWindow(hwnd) / 72
    fit_font(out, right - left, bottom - top, columns, rows, face, round(points * scale), round(smallest * scale))
    kernel32.SetConsoleDisplayMode(out, 1, None)  # CONSOLE_FULLSCREEN_MODE
    user32.ShowWindow(hwnd, 5)  # SW_SHOW: the window is started hidden
    user32.SetForegroundWindow(hwnd)


def hide_scrollbar():
    # The console brings its scrollbar back whenever the screen buffer changes.
    user32.ShowScrollBar(kernel32.GetConsoleWindow(), 3, False)  # SB_BOTH


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
