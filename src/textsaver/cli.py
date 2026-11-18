"""textsaver: Omarchy's terminal screensaver, for Windows."""

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from textsaver import win32

DEFAULT_FONT = "delta_corps_priest_1"
# Omarchy's tte invocation.
TTE_ARGS = [
    "--frame-rate", "120", "--canvas-width", "0", "--canvas-height", "0", "--reuse-canvas",
    "--anchor-canvas", "c", "--anchor-text", "c", "--random-effect", "--no-eol", "--no-restore-cursor",
]


def state_dir():
    return Path(os.environ["LOCALAPPDATA"]) / "textsaver"


def render(text, font=DEFAULT_FONT):
    import pyfiglet

    art = pyfiglet.figlet_format(text, font=font, width=1000)
    return "\n".join(line.rstrip() for line in art.splitlines()).strip("\n") + "\n"


def art_file():
    path = state_dir() / "screensaver.txt"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render("textsaver"), encoding="utf-8")
    return path


def console_python():
    # Under the gui-script, sys.executable is pythonw.exe; the console needs python.exe.
    exe = Path(sys.executable)
    console = exe.with_name("python.exe")
    return console if exe.name.lower() == "pythonw.exe" and console.exists() else exe


def start():
    mutex = win32.single_instance("Local\\textsaver")
    if mutex is None:
        return 0
    win32.set_dpi_aware()
    win32.park_cursor()
    # Windows runs screensavers on a separate, empty desktop. Windows Terminal cannot show a
    # window there, but the classic console can, so host each monitor's loop in conhost.exe.
    conhost = Path(os.environ["SystemRoot"]) / "System32" / "conhost.exe"
    python = console_python()
    # Start hidden; each window shows itself once it is fullscreen on its monitor.
    hidden = subprocess.STARTUPINFO(dwFlags=subprocess.STARTF_USESHOWWINDOW, wShowWindow=subprocess.SW_HIDE)
    for index in range(len(win32.monitors())):
        subprocess.Popen(
            [str(conhost), str(python), "-m", "textsaver", "run", "--monitor", str(index)], startupinfo=hidden
        )

    # Windows counts the screensaver as running for as long as this process lives.
    watch = win32.InputWatch()
    while not watch.triggered():
        time.sleep(0.1)
    return 0


def wait_for_size(watch, settle=0.5, minimum=1.0, limit=5.0):
    """Wait for the window to finish going fullscreen. False if input arrived first."""
    begin = since = time.monotonic()
    size = None
    while (now := time.monotonic()) - begin < limit:
        if watch.triggered():
            return False
        current = shutil.get_terminal_size()
        if current != size:
            size, since = current, now
        elif now - since >= settle and now - begin >= minimum:
            break
        time.sleep(0.1)
    return True


def run(monitor=None):
    win32.set_dpi_aware()
    if monitor is not None:
        screens = win32.monitors()
        win32.fullscreen_console(screens[min(monitor, len(screens) - 1)])
    art = art_file()
    out = sys.stdout
    # Alternate screen, black background, hidden cursor, clear.
    out.write("\x1b[?1049h\x1b]11;rgb:00/00/00\x07\x1b[?25l\x1b[2J")
    out.flush()
    watch = win32.InputWatch()
    env = {**os.environ, "PYTHONUTF8": "1"}
    child = None
    try:
        if not wait_for_size(watch):
            return 0
        while not watch.triggered():
            # Start the next effect when the last one finished cleanly; on failure, stay black.
            if child is None or child.poll() == 0:
                child = subprocess.Popen(
                    [sys.executable, "-m", "terminaltexteffects", "-i", str(art), *TTE_ARGS], env=env
                )
            if monitor is not None:
                win32.hide_scrollbar()
            time.sleep(0.1)
    except KeyboardInterrupt:
        pass
    finally:
        if child is not None and child.poll() is None:
            child.kill()
            child.wait()
        out.write("\x1b[0m\x1b]111\x07\x1b[?25h\x1b[?1049l")
        out.flush()
    return 0


def text(words, font):
    import pyfiglet

    try:
        art = render(" ".join(words), font)
    except pyfiglet.FontNotFound:
        print(f"textsaver: unknown font {font!r}", file=sys.stderr)
        return 1
    path = state_dir() / "screensaver.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(art, encoding="utf-8")
    print(art, end="")
    print(f"Saved to {path}")
    return 0


def install():
    launcher = Path(sys.executable).with_name("textsaver-scr.exe")
    if not launcher.exists():
        print(f"textsaver: {launcher} not found; install with `uv tool install .`", file=sys.stderr)
        return 1
    scr = art_file().with_name("textsaver.scr")
    shutil.copy2(launcher, scr)
    print(f"Screensaver: {scr}")
    print("Pick a timeout in Screen Saver Settings and click OK.")
    subprocess.run(["rundll32.exe", "desk.cpl,InstallScreenSaver", str(scr)])
    return 0


def uninstall():
    (state_dir() / "textsaver.scr").unlink(missing_ok=True)
    print("Removed the textsaver screensaver.")
    print("Choose another screensaver in Screen Saver Settings (control desk.cpl,,@screensaver).")
    return 0


def main(argv=None):
    if sys.stdout is not None:
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(prog="textsaver", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("start", help="start the screensaver now, on every monitor")
    p = sub.add_parser("run", help="run the effect loop in the current terminal (used internally)")
    p.add_argument("--monitor", type=int, help="take over this console window and fill that monitor")
    p = sub.add_parser("text", help="set the screensaver text")
    p.add_argument("words", nargs="+")
    p.add_argument("--font", default=DEFAULT_FONT, help=f"figlet font (default: {DEFAULT_FONT})")
    sub.add_parser("install", help="install as a Windows screensaver")
    sub.add_parser("uninstall", help="remove the Windows screensaver")
    args = parser.parse_args(argv)
    if args.command == "text":
        return text(args.words, args.font)
    if args.command == "run":
        return run(args.monitor)
    return {"start": start, "install": install, "uninstall": uninstall}[args.command]()


def scr_main():
    """Windows screensaver protocol: /s run, /p <hwnd> preview, /c[:<hwnd>] configure."""
    mode = sys.argv[1].lstrip("/-").lower() if len(sys.argv) > 1 else "c"
    if mode.startswith("s"):
        return start()
    if mode.startswith("p"):
        return 0
    os.startfile(art_file())
    return 0
