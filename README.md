<img src="assets/icon.png" width="64" height="64" alt="">

# textsaver

A Windows port of the [Omarchy](https://github.com/basecamp/omarchy) screensaver: your text in block
letters, animated with random [terminaltexteffects](https://github.com/ChrisBuilds/terminaltexteffects)
effects in a fullscreen Windows Terminal window on every monitor. Any key, click or mouse movement ends it.

It installs as a regular Windows screensaver, so Windows handles the idle timer and the lock on resume.

## Requirements

- Windows 10 or 11
- [Windows Terminal](https://aka.ms/terminal)
- [uv](https://docs.astral.sh/uv/)

## Install

```powershell
uv tool install .
textsaver install
```

If `textsaver` is not recognised, uv's tool folder is not on your PATH. Run `uv tool update-shell` and
open a new terminal, or call `%USERPROFILE%\.local\bin\textsaver` directly.

`textsaver install` adds a `textsaver` profile to Windows Terminal (black background, no padding,
larger font) and opens Screen Saver Settings with textsaver selected. Pick a timeout and click OK,
then close all Windows Terminal windows so the new profile loads.

## Usage

```powershell
textsaver start                 # run the screensaver now
textsaver text Hello            # change the text
textsaver text Hi --font slant  # use another figlet font
```

The text is stored in `%LOCALAPPDATA%\textsaver\screensaver.txt`. Edit it by hand for multi-line or
custom art, or use the Settings button in Screen Saver Settings, which opens the same file. Short
words work best: text wider than the screen is clipped.

`uvx pyfiglet --list_fonts` lists the available fonts. The default, `delta_corps_priest_1`, is the
one Omarchy's logo uses.

While the screensaver runs, the mouse pointer is parked in the bottom-right corner of the primary
monitor.

## Update

```powershell
uv tool install . --reinstall
```

## Uninstall

```powershell
textsaver uninstall
uv tool uninstall textsaver
```

Then choose a different screensaver in Screen Saver Settings. Your text file is left in place.
