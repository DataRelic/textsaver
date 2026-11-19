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
# Animation steps per second (the frame rate Omarchy gives tte).
TICKS_PER_SECOND = 120
# An effect holds the screen for at least MIN_SECONDS; after MAX_SECONDS it is hurried to its end.
MIN_SECONDS = 5
MAX_SECONDS = 15
# Settings for the effects that would otherwise run far past MAX_SECONDS: a shorter, faster rain; fewer swarms.
SHORTER = {"matrix": {"rain_time": 5, "rain_fall_delay_range": (2, 8)}, "swarm": {"swarm_size": 0.25}}


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


def play():
    """Play one random effect in the current terminal, from start to finish."""
    import random

    from terminaltexteffects.__main__ import build_parser

    name, (effect_class, _) = random.choice(list(build_parser()[1].items()))
    effect = effect_class(art_file().read_text(encoding="utf-8"))
    for setting, value in SHORTER.get(name, {}).items():
        setattr(effect.effect_config, setting, value)
    # Omarchy's tte settings, except the frame rate: the loop below does the pacing.
    config = effect.terminal_config
    config.frame_rate = 0
    config.canvas_width = config.canvas_height = 0
    config.anchor_canvas = config.anchor_text = "c"
    config.reuse_canvas = config.no_eol = config.no_restore_cursor = True
    try:
        with effect.terminal_output() as terminal:
            frames = iter(effect)
            frame = drawn = None
            ticks = 0
            catch_up = 0.05
            begin = time.monotonic()
            while True:
                # The classic console draws far fewer frames per second than the animation has
                # steps. Keep the animation on the clock: step it without drawing while it is
                # behind, but only for as long as a frame takes to draw (at least 50 ms), so that
                # slow effects still reach the screen. Past MAX_SECONDS it always counts as
                # behind, which hurries it to its end.
                now = time.monotonic()
                hurry = now - begin >= MAX_SECONDS
                try:
                    while True:
                        frame = next(frames)
                        ticks += 1
                        elapsed = time.monotonic() - begin
                        on_time = not hurry and ticks >= elapsed * TICKS_PER_SECOND
                        if on_time or elapsed - (now - begin) > catch_up:
                            break
                except StopIteration:
                    break
                before = time.monotonic()
                terminal.print(frame)
                drawn = frame
                catch_up = max(0.05, time.monotonic() - before)
                if not hurry:
                    time.sleep(max(0.0, begin + ticks / TICKS_PER_SECOND - time.monotonic()))
            if frame is not drawn:
                terminal.print(frame)  # The finished text, when the last steps were skipped.
    except KeyboardInterrupt:
        return 1
    return 0


def run(monitor=None):
    win32.set_dpi_aware()
    if monitor is not None:
        screens = win32.monitors()
        lines = art_file().read_text(encoding="utf-8").splitlines() or [""]
        columns = max(1, max(map(len, lines)))
        win32.fullscreen_console(screens[min(monitor, len(screens) - 1)], columns, len(lines))
    out = sys.stdout
    # Alternate screen, black background, hidden cursor, clear.
    out.write("\x1b[?1049h\x1b]11;rgb:00/00/00\x07\x1b[?25l\x1b[2J")
    out.flush()
    watch = win32.InputWatch()
    env = {**os.environ, "PYTHONUTF8": "1"}
    child, started = None, float("-inf")
    try:
        if not wait_for_size(watch):
            return 0
        while not watch.triggered():
            now = time.monotonic()
            if child is not None and child.poll() is None and now - started > MAX_SECONDS + 10:
                child.kill()  # Hung: no effect may hold the screen.
                child.wait()
            if child is not None and child.poll() is not None:
                if child.returncode != 0:
                    out.write("\x1b[0m\x1b[2J")  # Failed or killed: blank its half-drawn frame.
                    out.flush()
                child = None
            # A finished effect's text stays up until its MIN_SECONDS are over.
            if child is None and now - started >= MIN_SECONDS:
                child, started = subprocess.Popen([sys.executable, "-m", "textsaver", "play"], env=env), now
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
    sub.add_parser("play", help="play one random effect in the current terminal (used internally)")
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
    return {"start": start, "play": play, "install": install, "uninstall": uninstall}[args.command]()


def scr_main():
    """Windows screensaver protocol: /s run, /p <hwnd> preview, /c[:<hwnd>] configure."""
    mode = sys.argv[1].lstrip("/-").lower() if len(sys.argv) > 1 else "c"
    if mode.startswith("s"):
        return start()
    if mode.startswith("p"):
        return 0
    os.startfile(art_file())
    return 0
