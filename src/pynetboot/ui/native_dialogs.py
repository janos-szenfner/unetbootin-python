"""Native file and folder pickers.

Tk routes its choosers to the OS on Windows (win32) and macOS (aqua), so
those already look native. On X11 and Wayland it draws its own instead --
the dated, cramped dialog with no places sidebar, no thumbnails and no
recent files.

The desktop's own chooser is used there when one is present: zenity on
GTK desktops (GNOME, Cinnamon, XFCE, Zorin), kdialog on KDE, and qarma as
a Qt-built stand-in for zenity. Tk remains the fallback, so a desktop with
none of them behaves exactly as before.
"""

import logging
import subprocess
import sys
from typing import List, Optional

logger = logging.getLogger(__name__)

# A chooser stays open until the user acts, so this only exists to stop a
# wedged helper from hanging the application forever.
DIALOG_TIMEOUT = 3600

# Cancelling is an ordinary outcome, not a failure: zenity and qarma exit 1,
# kdialog exits 1 as well.
_CANCELLED = 1


def _tk_is_native() -> bool:
    """True where Tk hands its choosers to the operating system."""
    return sys.platform in ('win32', 'darwin')


def _available(command: str) -> Optional[str]:
    import shutil
    return shutil.which(command)


def _run_chooser(argv: List[str]) -> Optional[str]:
    """Run a chooser and return the chosen path, or None."""
    try:
        result = subprocess.run(
            argv, capture_output=True, text=True, timeout=DIALOG_TIMEOUT)
    except subprocess.TimeoutExpired:
        logger.warning(f"{argv[0]} did not return; falling back")
        return None
    except (subprocess.SubprocessError, OSError) as e:
        logger.warning(f"{argv[0]} could not be run ({e}); falling back")
        return None

    if result.returncode == _CANCELLED:
        logger.debug(f"{argv[0]}: cancelled by the user")
        return ''          # distinct from None: chosen nothing, do not fall back

    if result.returncode != 0:
        logger.warning(
            f"{argv[0]} failed (exit {result.returncode}): "
            f"{(result.stderr or '').strip()}")
        return None

    # kdialog and zenity both terminate the path with a newline.
    return (result.stdout or '').strip() or ''


def _linux_chooser(title: str, initial_dir: Optional[str],
                   directory: bool) -> Optional[str]:
    """Ask the desktop's own chooser. None means none was usable."""
    start = initial_dir or ''

    if _available('zenity'):
        argv = ['zenity', '--file-selection', f'--title={title}']
        if directory:
            argv.append('--directory')
        if start:
            # zenity treats a trailing slash as "start inside this folder".
            argv.append(f"--filename={start.rstrip('/')}/")
        return _run_chooser(argv)

    if _available('kdialog'):
        mode = '--getexistingdirectory' if directory else '--getopenfilename'
        return _run_chooser(
            ['kdialog', mode, start or '.', '--title', title])

    if _available('qarma'):
        argv = ['qarma', '--file-selection', f'--title={title}']
        if directory:
            argv.append('--directory')
        if start:
            argv.append(f"--filename={start.rstrip('/')}/")
        return _run_chooser(argv)

    logger.debug("No native chooser found (zenity/kdialog/qarma); using Tk")
    return None


def ask_directory(title: str, initial_dir: Optional[str] = None) -> Optional[str]:
    """Choose a folder. Returns None if the user cancelled."""
    if not _tk_is_native():
        chosen = _linux_chooser(title, initial_dir, directory=True)
        if chosen is not None:
            return chosen or None

    from tkinter import filedialog
    return filedialog.askdirectory(
        title=title, initialdir=initial_dir or None) or None


def ask_open_filename(title: str,
                      initial_dir: Optional[str] = None) -> Optional[str]:
    """Choose a file. Returns None if the user cancelled."""
    if not _tk_is_native():
        chosen = _linux_chooser(title, initial_dir, directory=False)
        if chosen is not None:
            return chosen or None

    from tkinter import filedialog
    return filedialog.askopenfilename(
        title=title, initialdir=initial_dir or None) or None
