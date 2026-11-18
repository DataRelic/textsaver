"""textsaver: Omarchy's terminal screensaver, for Windows Terminal."""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from textsaver import win32

PROFILE = "textsaver"
PROFILE_GUID = "{29d4fd6b-b4c7-414e-bf5a-09bf301bbd2b}"
DEFAULT_FONT = "delta_corps_priest_1"
# Omarchy's tte invocation.
TTE_ARGS = [
    "--frame-rate", "120", "--canvas-width", "0", "--canvas-height", "0", "--reuse-canvas",
    "--anchor-canvas", "c", "--anchor-text", "c", "--random-effect", "--no-eol", "--no-restore-cursor",
]


def local_appdata():
    return Path(os.environ["LOCALAPPDATA"])


def state_dir():
    return local_appdata() / "textsaver"


def fragment_path():
    return local_appdata() / "Microsoft" / "Windows Terminal" / "Fragments" / "textsaver" / "textsaver.json"


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
    # Under the gui-script, sys.executable is pythonw.exe; terminals need python.exe.
    exe = Path(sys.executable)
    console = exe.with_name("python.exe")
    return console if exe.name.lower() == "pythonw.exe" and console.exists() else exe


def wt_argv(monitor, python):
    left, top = monitor[0], monitor[1]
    wt = shutil.which("wt") or str(local_appdata() / "Microsoft" / "WindowsApps" / "wt.exe")
    return [
        wt, "--window", "new", "--fullscreen", f"--pos={left + 50},{top + 50}",
        "new-tab", "-p", PROFILE, "--title", PROFILE, "--", str(python), "-m", "textsaver", "run",
    ]


def fragment(python):
    return {
        "profiles": [
            {
                "guid": PROFILE_GUID,
                "name": PROFILE,
                "commandline": f'"{python}" -m textsaver run',
                "tabTitle": PROFILE,
                "suppressApplicationTitle": True,
                "padding": "0",
                "scrollbarState": "hidden",
                "background": "#000000",
                "cursorColor": "#000000",
                "opacity": 100,
                "useAcrylic": False,
                "font": {"size": 18},
                "closeOnExit": "always",
                "bellStyle": "none",
            }
        ]
    }


def start():
    mutex = win32.single_instance("Local\\textsaver")
    if mutex is None:
        return 0
    win32.set_dpi_aware()
    screens = win32.monitors()
    win32.park_cursor()
    python = console_python()
    # Windows that already carry our title are not ours to raise.
    raised = set(win32.find_windows(win32.WT_WINDOW_CLASS, PROFILE))
    expected = len(raised) + len(screens)
    for screen in screens:
        subprocess.Popen(wt_argv(screen, python), creationflags=subprocess.CREATE_NO_WINDOW)

    # Windows counts the screensaver as running for as long as this process lives.
    watch = win32.InputWatch()
    focused, deadline = False, time.monotonic() + 10
    while not watch.triggered():
        if len(raised) < expected and time.monotonic() < deadline:
            for hwnd in win32.find_windows(win32.WT_WINDOW_CLASS, PROFILE):
                if hwnd not in raised:
                    win32.make_topmost(hwnd)
                    focused = focused or win32.foreground(hwnd)
                    raised.add(hwnd)
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


def run():
    win32.set_dpi_aware()
    art = art_file()
    out = sys.stdout
    # Alternate screen, title, black background, hidden cursor, clear.
    out.write("\x1b[?1049h\x1b]0;textsaver\x07\x1b]11;rgb:00/00/00\x07\x1b[?25l\x1b[2J")
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
    frag = fragment_path()
    frag.parent.mkdir(parents=True, exist_ok=True)
    frag.write_text(json.dumps(fragment(console_python()), indent=2), encoding="utf-8")
    scr = state_dir() / "textsaver.scr"
    art_file()
    shutil.copy2(launcher, scr)
    print(f"Windows Terminal profile: {frag}")
    print(f"Screensaver: {scr}")
    print("Restart Windows Terminal so it loads the profile, then pick a timeout in Screen Saver Settings.")
    subprocess.run(["rundll32.exe", "desk.cpl,InstallScreenSaver", str(scr)])
    return 0


def uninstall():
    frag = fragment_path()
    frag.unlink(missing_ok=True)
    if frag.parent.exists() and not any(frag.parent.iterdir()):
        frag.parent.rmdir()
    (state_dir() / "textsaver.scr").unlink(missing_ok=True)
    print("Removed the textsaver profile and screensaver.")
    print("Choose another screensaver in Screen Saver Settings (control desk.cpl,,@screensaver).")
    return 0


def main(argv=None):
    if sys.stdout is not None:
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(prog="textsaver", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("start", help="start the screensaver now, on every monitor")
    sub.add_parser("run", help="run the effect loop in the current terminal (used internally)")
    p = sub.add_parser("text", help="set the screensaver text")
    p.add_argument("words", nargs="+")
    p.add_argument("--font", default=DEFAULT_FONT, help=f"figlet font (default: {DEFAULT_FONT})")
    sub.add_parser("install", help="install the Windows Terminal profile and the screensaver")
    sub.add_parser("uninstall", help="remove the profile and the screensaver")
    args = parser.parse_args(argv)
    if args.command == "text":
        return text(args.words, args.font)
    return {"start": start, "run": run, "install": install, "uninstall": uninstall}[args.command]()


def scr_main():
    """Windows screensaver protocol: /s run, /p <hwnd> preview, /c[:<hwnd>] configure."""
    mode = sys.argv[1].lstrip("/-").lower() if len(sys.argv) > 1 else "c"
    if mode.startswith("s"):
        return start()
    if mode.startswith("p"):
        return 0
    os.startfile(art_file())
    return 0
